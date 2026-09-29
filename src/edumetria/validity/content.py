"""Evidências de conteúdo a partir de pareceres de juízes (seção 8).

- I-CVI = proporção de juízes com nota 3 ou 4 em relevância, por item.
- S-CVI/Ave = média dos I-CVIs (apresentada junto da distribuição).
- Aiken V = Σ(r − lo) / [n (c − 1)], com IC por escore (Penfield & Giacobbi, 2004).
- Limiar de revisão é configurável; nenhum item é marcado "validado" por
  ultrapassar número. Pareceres simulados nunca contam como evidência humana.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

REVIEW_THRESHOLD_ICVI = 0.78  # ilustrativo (Lynn, 1986, para ≥6 juízes) — configurável


def aiken_v(ratings: np.ndarray, lo: int = 1, hi: int = 4, level: float = 0.95) -> dict:
    r = np.asarray(ratings, dtype=float)
    n, c = len(r), hi - lo + 1
    if n == 0:
        return {"aiken_v": None}
    v = float(np.sum(r - lo) / (n * (c - 1)))
    z = stats.norm.ppf(1 - (1 - level) / 2)
    k = n * (c - 1)
    center = 2 * k * v + z**2
    rad = z * np.sqrt(4 * k * v * (1 - v) + z**2)
    denom = 2 * (k + z**2)
    return {"aiken_v": v, "ci_low": float((center - rad) / denom), "ci_high": float((center + rad) / denom)}


def content_validity(reviews: pd.DataFrame, threshold: float = REVIEW_THRESHOLD_ICVI) -> dict:
    """``reviews``: item_id, judge_ref, criterion, rating (1–4), evidence_origin, comment."""
    rel = reviews[reviews["criterion"] == "relevancia"]
    per_item = []
    for item, g in reviews.groupby("item_id"):
        r = rel[rel["item_id"] == item]["rating"].to_numpy()
        icvi = float(np.mean(r >= 3)) if len(r) else None
        crit_means = g.groupby("criterion")["rating"].mean().round(2).to_dict()
        av = aiken_v(g[g["criterion"] == "alinhamento"]["rating"].to_numpy())
        comments = [c for c in g["comment"].fillna("") if c]
        per_item.append({
            "item_id": item,
            "n_judges": int(g["judge_ref"].nunique()),
            "i_cvi_relevance": icvi,
            "aiken_v_alignment": av["aiken_v"],
            "aiken_v_ci": [av.get("ci_low"), av.get("ci_high")],
            "criterion_means": crit_means,
            "comments": comments,
            "needs_review": bool(icvi is not None and icvi < threshold) or any(
                m < 2.75 for m in crit_means.values()),
            "evidence_origin": ",".join(sorted(g["evidence_origin"].unique())),
        })
    icvis = np.array([p["i_cvi_relevance"] for p in per_item if p["i_cvi_relevance"] is not None])
    origins = set(reviews["evidence_origin"].unique())
    return {
        "items": per_item,
        "s_cvi_ave": float(icvis.mean()) if len(icvis) else None,
        "i_cvi_distribution": {"min": float(icvis.min()), "q25": float(np.quantile(icvis, 0.25)),
                               "median": float(np.median(icvis)), "max": float(icvis.max())} if len(icvis) else {},
        "threshold_used": threshold,
        "items_needing_review": [p["item_id"] for p in per_item if p["needs_review"]],
        "evidence_origin": sorted(origins),
        "counts_as_human_evidence": origins == {"human_review"},
        "note": "concordância entre juízes não garante cobertura curricular nem ausência de viés",
    }
