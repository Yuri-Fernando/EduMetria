"""Desenho de estudo de impacto (seção 13): poder e MDES para ensaio por escolas.

O estudo real depende de parceria institucional (fora do escopo). O que é
feito aqui é o que se faz ANTES de qualquer piloto:
1. MDES analítico para ensaio randomizado por clusters (Bloom, 2005):
   MDES = M_{J−2} · √[ ICC(1−R²₂)/(P(1−P)J) + (1−ICC)(1−R²₁)/(P(1−P)J·n) ]
   com M = t_{1−α/2} + t_{power} (gl = J − 2).
2. Número de escolas necessário para um efeito-alvo.
3. Poder por simulação usando a população sintética (efeito plantado
   conhecido), com análise no nível da escola (médias de cluster, gl = J − 2)
   — válida para randomização por escola, sem fingir independência entre alunos.
Nada aqui estima efeito real; o efeito simulado é premissa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def mdes_cluster_rct(n_clusters: int, m_per_cluster: float, icc: float, alpha: float = 0.05, power: float = 0.80,
                     p_treat: float = 0.5, r2_level2: float = 0.0, r2_level1: float = 0.0) -> float:
    df = n_clusters - 2
    M = stats.t.ppf(1 - alpha / 2, df) + stats.t.ppf(power, df)
    pq = p_treat * (1 - p_treat)
    var = icc * (1 - r2_level2) / (pq * n_clusters) + (1 - icc) * (1 - r2_level1) / (pq * n_clusters * m_per_cluster)
    return float(M * np.sqrt(var))


def clusters_needed(target_es: float, m_per_cluster: float, icc: float, **kw) -> int:
    for J in range(6, 2000, 2):
        if mdes_cluster_rct(J, m_per_cluster, icc, **kw) <= target_es:
            return J
    return -1


def es_to_risk_difference(es: float, p0: float) -> float:
    """Converte efeito padronizado em diferença absoluta de proporção (aprox. normal)."""
    return float(es * np.sqrt(p0 * (1 - p0)))


def simulate_power(outcome_by_student: pd.DataFrame, effect_rd: float, n_reps: int = 300, alpha: float = 0.05,
                   seed: int = 0) -> dict:
    """``outcome_by_student``: colunas school_id, y (0/1). Sorteia metade das
    escolas para tratamento, reduz a probabilidade do evento em ``effect_rd``
    (absoluto) nos tratados e testa diferença de médias de escola (t, gl=J−2)."""
    rng = np.random.default_rng(seed)
    schools = outcome_by_student["school_id"].unique()
    J = len(schools)
    rejections, estimates = 0, []
    for _ in range(n_reps):
        treated = set(rng.choice(schools, J // 2, replace=False))
        d = outcome_by_student.copy()
        is_t = d["school_id"].isin(treated).to_numpy()
        # remove eventos em tratados com probabilidade calibrada para reduzir a taxa em effect_rd
        p0 = d.loc[is_t, "y"].mean()
        drop_p = min(effect_rd / p0, 1.0) if p0 > 0 else 0.0
        flip = is_t & (d["y"].to_numpy() == 1) & (rng.random(len(d)) < drop_p)
        d.loc[flip, "y"] = 0
        means = d.assign(t=is_t).groupby("school_id").agg(y=("y", "mean"), t=("t", "first"))
        a, b = means.loc[means["t"], "y"], means.loc[~means["t"], "y"]
        tstat, p = stats.ttest_ind(b, a, equal_var=True)
        estimates.append(float(b.mean() - a.mean()))
        rejections += p < alpha
    return {"n_schools": int(J), "n_students": int(len(outcome_by_student)), "effect_rd_planted": effect_rd,
            "power": rejections / n_reps, "mean_estimate": float(np.mean(estimates)),
            "sd_estimate": float(np.std(estimates, ddof=1)), "n_reps": n_reps,
            "analysis": "médias por escola, t de Student com gl = J − 2"}
