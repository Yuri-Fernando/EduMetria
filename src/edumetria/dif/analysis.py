"""Funcionamento Diferencial do Item (seção 11.2).

DIF = diferença na função de resposta condicionada ao traço — diferença de
média bruta entre grupos NÃO é DIF. Dois métodos complementares:

1. Mantel-Haenszel (uniforme), estratificado pelo escore das âncoras + item
   estudado; tamanho de efeito ETS Δ_MH = −2,35·ln(α_MH), classes A/B/C.
2. Regressão logística (Swaminathan & Rogers; Zumbo): testes de razão de
   verossimilhança para DIF uniforme (grupo) e não uniforme (grupo × escore).

Multiplicidade: Benjamini-Hochberg sobre todas as comparações registradas.
Grupo pequeno → ``insufficient_evidence`` (ausência de significância não é
ausência de DIF). Resultado nunca remove item automaticamente: todo achado
nasce com ``review_state = pending_human_review``.
O motor de referência mirt::DIF (Wald/LR em multipleGroup) está em r/dif.R.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

MIN_N_PER_GROUP = 200


def benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    ok = ~np.isnan(p)
    out = np.full_like(p, np.nan)
    pv = p[ok]
    m = len(pv)
    if m == 0:
        return out
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.empty(m)
    adj[order] = np.clip(ranked, 0, 1)
    out[ok] = adj
    return out


def mantel_haenszel(item: np.ndarray, group_focal: np.ndarray, matching: np.ndarray) -> dict:
    """MH para um item dicotômico. ``group_focal``: 1 = focal (B), 0 = referência."""
    ok = ~np.isnan(item) & ~np.isnan(matching)
    y, g, s = item[ok], group_focal[ok], matching[ok]
    num = den = a_sum = e_sum = var_sum = 0.0
    for level in np.unique(s):
        m = s == level
        yr, yf = y[m & (g == 0)], y[m & (g == 1)]
        nr, nf = len(yr), len(yf)
        T = nr + nf
        if nr == 0 or nf == 0 or T < 2:
            continue
        A, B = yr.sum(), nr - yr.sum()  # referência: acerto, erro
        C, D = yf.sum(), nf - yf.sum()  # focal
        m1, m0 = A + C, B + D
        if m1 == 0 or m0 == 0:
            continue
        num += A * D / T
        den += B * C / T
        a_sum += A
        e_sum += nr * m1 / T
        var_sum += nr * nf * m1 * m0 / (T**2 * (T - 1))
    if den == 0 or num == 0 or var_sum == 0:
        return {"alpha_mh": None, "delta_mh": None, "chi2_mh": None, "p_mh": None}
    alpha = num / den
    chi2 = (abs(a_sum - e_sum) - 0.5) ** 2 / var_sum
    return {
        "alpha_mh": float(alpha),
        "delta_mh": float(-2.35 * np.log(alpha)),
        "chi2_mh": float(chi2),
        "p_mh": float(stats.chi2.sf(chi2, 1)),
    }


def ets_class(delta: float | None, p_adj: float | None) -> str:
    """Classificação ETS (Zieky, 1993), usada aqui como triagem."""
    if delta is None or p_adj is None or np.isnan(p_adj):
        return "undetermined"
    ad = abs(delta)
    if ad < 1.0 or p_adj >= 0.05:
        return "A"
    if ad >= 1.5:
        return "C"
    return "B"


def logistic_dif(item: np.ndarray, group_focal: np.ndarray, matching: np.ndarray) -> dict:
    ok = ~np.isnan(item) & ~np.isnan(matching)
    y, g, s = item[ok], group_focal[ok].astype(float), matching[ok]
    s = (s - s.mean()) / (s.std() or 1.0)
    X0 = sm.add_constant(np.column_stack([s]))
    X1 = sm.add_constant(np.column_stack([s, g]))
    X2 = sm.add_constant(np.column_stack([s, g, s * g]))
    try:
        m0 = sm.Logit(y, X0).fit(disp=0)
        m1 = sm.Logit(y, X1).fit(disp=0)
        m2 = sm.Logit(y, X2).fit(disp=0)
    except Exception as exc:  # separação perfeita etc.
        return {"p_uniform": None, "p_nonuniform": None, "error": type(exc).__name__}
    lr_u = 2 * (m1.llf - m0.llf)
    lr_nu = 2 * (m2.llf - m1.llf)
    # Nagelkerke ΔR² entre M0 e M2 (magnitude; Jodoin & Gierl)
    n = len(y)
    def r2n(m):
        null = sm.Logit(y, np.ones((n, 1))).fit(disp=0).llf
        cs = 1 - np.exp(2 * (null - m.llf) / n)
        return cs / (1 - np.exp(2 * null / n))
    return {
        "lr_uniform": float(lr_u),
        "p_uniform": float(stats.chi2.sf(lr_u, 1)),
        "lr_nonuniform": float(lr_nu),
        "p_nonuniform": float(stats.chi2.sf(lr_nu, 1)),
        "coef_group": float(m1.params[2]),
        "delta_r2_nagelkerke": float(r2n(m2) - r2n(m0)),
    }


def run_dif(
    X: np.ndarray,
    item_names: list[str],
    group: np.ndarray,
    anchors: list[str] | None = None,
    focal_label: str = "B",
    min_n_per_group: int = MIN_N_PER_GROUP,
) -> pd.DataFrame:
    """Executa MH + LR para cada item. Âncoras: se ``None``, usa todos os
    outros itens (sem purificação) e registra isso em ``anchor_strategy``."""
    X = np.asarray(X, dtype=float)
    g = (np.asarray(group) == focal_label).astype(int)
    n_ref, n_foc = int((g == 0).sum()), int((g == 1).sum())
    anchor_idx = [item_names.index(a) for a in anchors] if anchors else None
    rows = []
    for j, name in enumerate(item_names):
        match_cols = [k for k in (anchor_idx if anchor_idx is not None else range(len(item_names))) if k != j]
        # escore de pareamento: âncoras + item estudado (recomendação para MH)
        M = X[:, match_cols + [j]]
        matching = np.where(np.isnan(M).any(axis=1), np.nan, np.nansum(M, axis=1))
        row = {"item": name, "n_reference": n_ref, "n_focal": n_foc,
               "anchor_strategy": "known_anchors" if anchors else "all_other_items",
               "is_anchor": bool(anchors and name in anchors)}
        if min(n_ref, n_foc) < min_n_per_group:
            row.update(status="insufficient_evidence", review_state="not_applicable")
            rows.append(row)
            continue
        row.update(mantel_haenszel(X[:, j], g, matching))
        row.update(logistic_dif(X[:, j], g, matching))
        row["status"] = "computed"
        rows.append(row)
    df = pd.DataFrame(rows)
    if "p_mh" in df:
        df["p_mh_bh"] = benjamini_hochberg(df["p_mh"].to_numpy(dtype=float))
        df["p_uniform_bh"] = benjamini_hochberg(df["p_uniform"].to_numpy(dtype=float))
        df["p_nonuniform_bh"] = benjamini_hochberg(df["p_nonuniform"].to_numpy(dtype=float))
        df["ets_class"] = [ets_class(d, p) for d, p in zip(df["delta_mh"], df["p_mh_bh"])]
        df["flag_uniform"] = (df["p_uniform_bh"] < 0.05) & (df["ets_class"].isin(["B", "C"]))
        df["flag_nonuniform"] = df["p_nonuniform_bh"] < 0.05
        df["flagged"] = df["flag_uniform"] | df["flag_nonuniform"]
        df["review_state"] = np.where(df["flagged"], "pending_human_review", "no_action")
    return df
