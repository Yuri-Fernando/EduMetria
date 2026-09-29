"""Teoria Clássica dos Testes (seção 9).

Política de missing: proporção de acerto usa só respostas válidas; omissão
é reportada separadamente. Alfa/KR-20 e ponto-bisserial usam casos completos
(listwise) — o ``n`` efetivo é sempre reportado. Estados explícitos
substituem valores inválidos (item constante ≠ discriminação zero).
Flags são gatilhos investigativos da PoC, não critérios de exclusão.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from edumetria.domain.enums import ItemStatState

MIN_N_STABLE = 200
FLAG_EASY, FLAG_HARD = 0.95, 0.05
FLAG_OMISSION = 0.10


def cronbach_alpha(X: np.ndarray) -> float | None:
    """α = k/(k−1) · [1 − Σ var(X_j) / var(Σ X_j)]. None se não estimável."""
    X = np.asarray(X, dtype=float)
    if X.ndim != 2 or X.shape[1] < 2 or X.shape[0] < 3:
        return None
    total = X.sum(axis=1)
    var_total = total.var(ddof=1)
    if var_total <= 0:
        return None
    k = X.shape[1]
    return float(k / (k - 1) * (1 - X.var(axis=0, ddof=1).sum() / var_total))


def alpha_with_ci(X: np.ndarray, n_boot: int = 500, seed: int = 7, level: float = 0.95) -> dict:
    X = np.asarray(X, dtype=float)
    Xc = X[~np.isnan(X).any(axis=1)]
    est = cronbach_alpha(Xc)
    if est is None:
        return {"alpha": None, "state": ItemStatState.NO_VARIANCE.value, "n_complete": int(len(Xc))}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        s = cronbach_alpha(Xc[rng.integers(0, len(Xc), len(Xc))])
        if s is not None:
            boots.append(s)
    lo, hi = np.quantile(boots, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {
        "alpha": est,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "ci_method": f"bootstrap percentil ({n_boot} réplicas, casos completos)",
        "n_complete": int(len(Xc)),
        "state": (ItemStatState.OK if len(Xc) >= MIN_N_STABLE else ItemStatState.SMALL_SAMPLE).value,
        "note": "alfa alto não prova validade nem unidimensionalidade",
    }


def item_statistics(X: np.ndarray, item_names: list[str], n_administered: np.ndarray | None = None) -> pd.DataFrame:
    """Estatísticas por item dicotômico (p, omissão, ponto-bisserial corrigida)."""
    X = np.asarray(X, dtype=float)
    n, J = X.shape
    n_adm = n_administered if n_administered is not None else np.full(J, n)
    complete = ~np.isnan(X).any(axis=1)
    Xc = X[complete]
    total_c = Xc.sum(axis=1)
    rows = []
    for j, name in enumerate(item_names):
        col = X[:, j]
        valid = ~np.isnan(col)
        n_valid = int(valid.sum())
        row = {"item": name, "n_administered": int(n_adm[j]), "n_valid": n_valid,
               "omission_rate": float(1 - n_valid / n_adm[j]) if n_adm[j] else None}
        if n_valid == 0:
            row.update(p_value=None, r_pbis_corrected=None, state=ItemStatState.NOT_ADMINISTERED.value)
            rows.append(row)
            continue
        p = float(col[valid].mean())
        row["p_value"] = p
        rest = total_c - Xc[:, j]
        if p in (0.0, 1.0):
            row.update(r_pbis_corrected=None, state=ItemStatState.CONSTANT_ITEM.value)
        elif len(Xc) < 3:
            row.update(r_pbis_corrected=None, state=ItemStatState.SMALL_SAMPLE.value)
        elif Xc[:, j].std() == 0:
            row.update(r_pbis_corrected=None, state=ItemStatState.CONSTANT_ITEM.value)
        elif rest.std() == 0:
            row.update(r_pbis_corrected=None, state=ItemStatState.NO_VARIANCE.value)
        else:
            r = float(np.corrcoef(Xc[:, j], rest)[0, 1])
            row.update(r_pbis_corrected=r,
                       state=(ItemStatState.OK if len(Xc) >= MIN_N_STABLE else ItemStatState.SMALL_SAMPLE).value)
        flags = []
        if p > FLAG_EASY:
            flags.append("muito_facil")
        if p < FLAG_HARD:
            flags.append("muito_dificil")
        if row.get("r_pbis_corrected") is not None and row["r_pbis_corrected"] < 0:
            flags.append("discriminacao_negativa")
        elif row.get("r_pbis_corrected") is not None and row["r_pbis_corrected"] < 0.15:
            flags.append("discriminacao_baixa")
        if row["omission_rate"] is not None and row["omission_rate"] > FLAG_OMISSION:
            flags.append("omissao_elevada")
        row["flags"] = ";".join(flags)
        row["n_complete_cases"] = int(len(Xc))
        rows.append(row)
    return pd.DataFrame(rows)


def distractor_analysis(raw: pd.DataFrame, keys: dict[str, str], ability_proxy: pd.Series) -> pd.DataFrame:
    """Distribuição por alternativa e média do proxy de habilidade de quem a
    escolheu. Distrator com média ≥ gabarito sugere ambiguidade/gabarito errado.

    ``raw``: long com colunas student_ref, item_version_id, raw_response (só answered).
    """
    df = raw.dropna(subset=["raw_response"]).copy()
    df["ability"] = df["student_ref"].map(ability_proxy)
    out = []
    for item, g in df.groupby("item_version_id"):
        key = keys.get(item)
        tot = len(g)
        stats_ = g.groupby("raw_response")["ability"].agg(["count", "mean"])
        key_mean = stats_.loc[key, "mean"] if key in stats_.index else np.nan
        for opt, r in stats_.iterrows():
            out.append({
                "item_version_id": item, "option": opt, "is_key": opt == key,
                "proportion": float(r["count"] / tot), "mean_ability": float(r["mean"]),
                "flag": ("distrator_atrai_alta_habilidade" if opt != key and r["mean"] >= key_mean
                         else "distrator_nao_funcional" if opt != key and r["count"] / tot < 0.02 else ""),
            })
    return pd.DataFrame(out)


def score_distribution(X: np.ndarray) -> dict:
    X = np.asarray(X, dtype=float)
    Xc = X[~np.isnan(X).any(axis=1)]
    total = Xc.sum(axis=1)
    return {
        "n_complete": int(len(Xc)),
        "mean": float(total.mean()) if len(total) else None,
        "sd": float(total.std(ddof=1)) if len(total) > 1 else None,
        "histogram": {int(k): int(v) for k, v in zip(*np.unique(total, return_counts=True))},
    }
