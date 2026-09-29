"""Validação de importação, quarentena e snapshot (seções 15, 22.2 e alertas A2/A4).

Todo dado recusado gera *finding* com contagem e caminho de correção.
"Zero erro técnico" não significa dado confiável: o relatório também mede
omissão por motivo, cobertura e atraso.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from edumetria.domain.enums import ResponseStatus

REQUIRED_COLUMNS = [
    "response_id", "student_ref", "school_id", "instrument_id", "item_version_id",
    "raw_response", "scored_value", "response_status", "scoring_rule_version",
    "form_id", "attempt", "event_time", "ingested_at", "available_at",
]
VALID_STATUS = {s.value for s in ResponseStatus}
LATE_THRESHOLD = pd.Timedelta(days=14)


class DataQualityError(ValueError):
    """Lote não utilizável (ex.: versão de item desconhecida bloqueia score)."""


@dataclass
class DQReport:
    n_received: int
    n_accepted: int
    n_quarantined: int
    findings: list[dict] = field(default_factory=list)
    omission_by_reason: dict = field(default_factory=dict)
    coverage_by_school: dict = field(default_factory=dict)
    blocking: bool = False

    def to_dict(self) -> dict:
        return {
            "n_received": self.n_received,
            "n_accepted": self.n_accepted,
            "n_quarantined": self.n_quarantined,
            "blocking": self.blocking,
            "findings": self.findings,
            "omission_by_reason": self.omission_by_reason,
            "coverage_by_school": self.coverage_by_school,
        }


@dataclass
class ValidatedBatch:
    accepted: pd.DataFrame
    quarantine: pd.DataFrame
    report: DQReport
    snapshot_id: str
    dataset_hash: str


def dataset_hash(df: pd.DataFrame) -> str:
    """Hash determinístico do conteúdo (ordem canônica de linhas e colunas)."""
    cols = sorted(df.columns)
    canon = df[cols].sort_values(cols[:3] if len(cols) >= 3 else cols).astype(str)
    h = hashlib.sha256()
    h.update(",".join(cols).encode())
    h.update(pd.util.hash_pandas_object(canon, index=False).values.tobytes())
    return h.hexdigest()


def validate_responses(
    df: pd.DataFrame,
    items: pd.DataFrame,
    snapshot_prefix: str = "snapshot",
) -> ValidatedBatch:
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise DataQualityError(f"schema incompatível — colunas ausentes: {missing_cols}")

    df = df.copy()
    df["event_time"] = pd.to_datetime(df["event_time"])
    df["ingested_at"] = pd.to_datetime(df["ingested_at"])
    df["available_at"] = pd.to_datetime(df["available_at"])
    reasons = pd.Series("", index=df.index)
    findings = []

    def flag(mask: pd.Series, code: str, action: str):
        cnt = int(mask.sum())
        if cnt:
            reasons.loc[mask & (reasons == "")] = code
            findings.append({"code": code, "count": cnt, "action": action})

    known_versions = set(items["item_version_id"])
    flag(~df["item_version_id"].isin(known_versions), "unknown_item_version",
         "quarentena; impedir score e acionar responsável pelo instrumento (alerta A2)")
    flag(~df["response_status"].isin(VALID_STATUS), "invalid_response_status",
         "quarentena; corrigir codificação na origem")

    ncat = items.set_index("item_version_id")["n_categories"].to_dict()
    cat_max = df["item_version_id"].map(ncat)
    answered = df["response_status"] == ResponseStatus.ANSWERED.value
    sv = pd.to_numeric(df["scored_value"], errors="coerce")
    bad_cat = answered & cat_max.notna() & ((sv < 0) | (sv >= cat_max) | sv.isna())
    flag(bad_cat, "invalid_category", "quarentena; categoria fora da escala — nunca imputar")
    flag(~answered & sv.notna(), "value_without_answer", "quarentena; status e valor inconsistentes")

    key = ["student_ref", "item_version_id", "attempt"]
    dup = df.duplicated(subset=key, keep="first")
    flag(dup, "duplicate_response", "descartar duplicata; manter primeira ocorrência")

    late = (df["ingested_at"] - df["event_time"]) > LATE_THRESHOLD
    flag(late, "late_arrival", "quarentena para revisão; não entra em snapshot já fechado")

    multi_attempt = df.duplicated(subset=["student_ref", "item_version_id"], keep=False) & ~dup
    flag(multi_attempt & (df["attempt"] > 1) & (reasons == ""), "extra_attempt",
         "quarentena; política de tentativas não prevê múltiplas respostas")

    quarantine = df[reasons != ""].assign(dq_reason=reasons[reasons != ""])
    accepted = df[reasons == ""].copy()

    omission = (accepted["response_status"].value_counts(normalize=True).round(4).to_dict())
    coverage = (accepted.groupby("school_id")["student_ref"].nunique().to_dict())
    blocking = any(f["code"] == "unknown_item_version" for f in findings)

    h = dataset_hash(accepted.drop(columns=["response_id"]))
    report = DQReport(
        n_received=int(len(df)),
        n_accepted=int(len(accepted)),
        n_quarantined=int(len(quarantine)),
        findings=findings,
        omission_by_reason=omission,
        coverage_by_school={k: int(v) for k, v in coverage.items()},
        blocking=blocking,
    )
    return ValidatedBatch(accepted, quarantine, report, f"{snapshot_prefix}-{h[:12]}", h)


def to_wide(accepted: pd.DataFrame, instrument_id: str, items: pd.DataFrame) -> tuple[np.ndarray, list[str], list[str]]:
    """Matriz pessoa × item (NaN = não observado). Omissões, não alcançados e
    não aplicáveis viram NaN: missing nunca vira zero por conveniência."""
    sub = accepted[accepted["instrument_id"] == instrument_id]
    order = items.loc[items["instrument_id"] == instrument_id, "item_version_id"].tolist()
    # set_index/unstack preserva estudantes sem nenhuma resposta válida
    # (pivot_table os descartaria) — eles recebem insufficient_evidence no score.
    wide = (sub.drop_duplicates(["student_ref", "item_version_id"])
            .set_index(["student_ref", "item_version_id"])["scored_value"]
            .astype(float).unstack())
    wide = wide.reindex(columns=order)
    persons = wide.index.tolist()
    return wide.to_numpy(dtype=float), persons, order


def summarize_json(report: DQReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
