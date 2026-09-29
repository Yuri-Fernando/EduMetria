"""Contratos versionados (Pydantic) consumidos por API, worker e relatórios.

Regra da seção 18: contexto de tenant/usuário vem da autenticação — nenhum
contrato de entrada aceita tenant_id, role ou confirmed no corpo
(``extra="forbid"`` faz esses campos falharem na validação).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from edumetria import SCHEMA_VERSION
from edumetria.domain.enums import CaseStatus, EvidenceStatus, ScoreStatus

# Allowlist de famílias e configurações de calibração (seção 18): o cliente
# escolhe um nome, nunca um comando R, caminho ou código.
ALLOWED_MODEL_FAMILIES = ("2pl", "grm", "1pl")
ALLOWED_CONFIG_VERSIONS = ("calibration-v1",)
ALLOWED_PURPOSES = ("simulation", "research", "pilot")


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CalibrationRequest(StrictInput):
    instrument_version_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    dataset_snapshot_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,63}$")
    model_family: Literal["2pl", "grm", "1pl"]
    config_version: Literal["calibration-v1"] = "calibration-v1"
    purpose: Literal["simulation", "research", "pilot"] = "simulation"
    seed: int = Field(default=20260928, ge=0, le=2**31 - 1)


class ReleaseRequest(StrictInput):
    rationale: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)


class SupportCaseCreate(StrictInput):
    school_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    subject_ref: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    reason: str = Field(min_length=5, max_length=1000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class CaseReview(StrictInput):
    decision: Literal["approve", "decline", "request_changes"]
    rationale: str = Field(min_length=10, max_length=2000)
    expected_version: int = Field(ge=1)


class CaseTransition(StrictInput):
    to_status: Literal["in_progress", "completed", "cancelled"]
    note: str = Field(min_length=3, max_length=2000)
    expected_version: int = Field(ge=1)


class ScoreRecord(BaseModel):
    """Contrato de escore (seção 18). ``estimate`` é None quando não há evidência."""

    schema_version: str = SCHEMA_VERSION
    score_id: str
    subject_ref: str
    instrument_version_id: str
    calibration_id: str
    scale_id: str
    method: Literal["EAP"] = "EAP"
    estimate: float | None
    posterior_sd: float | None
    interval_90: tuple[float, float] | None = None
    n_items_answered: int
    status: ScoreStatus
    data_origin: str = "synthetic"
    warnings: list[str] = Field(default_factory=list)
    trace_id: str | None = None



class EvidenceSection(BaseModel):
    status: EvidenceStatus
    summary: str
    run_id: str | None = None
    details: dict = Field(default_factory=dict)


class PsychometricEvidenceReport(BaseModel):
    """Relatório de evidências (seção 18). Cada seção tem status próprio;
    nunca há um 'score de validade' agregado."""

    schema_version: str = SCHEMA_VERSION
    report_id: str
    instrument_version_id: str
    population_and_purpose: str
    data_origin: str
    content_review: EvidenceSection
    response_process: EvidenceSection
    dimensionality: EvidenceSection
    ctt: EvidenceSection
    irt: EvidenceSection
    precision: EvidenceSection
    dif: EvidenceSection
    external_relations: EvidenceSection
    structure_invariance: EvidenceSection | None = None  # 1.1.0: CFA ordinal + invariância (R/lavaan)
    limitations: list[str]
    prohibited_uses: list[str]
    approval_state: str
    artifacts: list[str]
    lineage: dict


CASE_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.PROPOSED: {CaseStatus.UNDER_REVIEW, CaseStatus.CANCELLED},
    CaseStatus.UNDER_REVIEW: {CaseStatus.APPROVED, CaseStatus.DECLINED, CaseStatus.PROPOSED},
    CaseStatus.APPROVED: {CaseStatus.IN_PROGRESS, CaseStatus.CANCELLED},
    CaseStatus.IN_PROGRESS: {CaseStatus.COMPLETED, CaseStatus.CANCELLED},
    CaseStatus.COMPLETED: set(),
    CaseStatus.DECLINED: set(),
    CaseStatus.CANCELLED: set(),
}
