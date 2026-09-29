"""Modelos multinível: estudantes aninhados em escolas.

ICC (correlação intraclasse) = variância entre escolas / variância total.
É o insumo central de (a) comparações entre escolas — que exigem incerteza
e encolhimento, nunca ranking cru — e (b) do cálculo de poder de estudos por
escola (efeito de desenho = 1 + (m − 1)·ICC).
Estimação: modelo linear misto com intercepto aleatório (statsmodels MixedLM,
REML). Escores "empirical Bayes" por escola são encolhidos para a média geral
proporcionalmente à confiabilidade da média da escola.
"""

from __future__ import annotations

import pandas as pd
import statsmodels.formula.api as smf


def school_icc(df: pd.DataFrame, value: str = "theta", group: str = "school_id") -> dict:
    import warnings
    d = df[[value, group]].dropna()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # bfgs → powell: o lbfgs do statsmodels fica preso na fronteira τ²=0 (verificado com ICC conhecido)
        m = smf.mixedlm(f"{value} ~ 1", d, groups=d[group]).fit(reml=True, method=["bfgs", "powell"])
    tau2 = max(float(m.cov_re.iloc[0, 0]), 0.0)
    sigma2 = float(m.scale)
    icc = tau2 / (tau2 + sigma2)
    sizes = d.groupby(group).size()
    m_bar = float(sizes.mean())
    boundary = tau2 < 1e-8  # variância entre escolas na fronteira (zero): efeitos EB = 0
    re = (pd.Series(0.0, index=sizes.index) if boundary else
          pd.Series({k: float(v.iloc[0]) for k, v in m.random_effects.items()}))
    raw = d.groupby(group)[value].mean() - float(m.fe_params.iloc[0])
    reliability = tau2 / (tau2 + sigma2 / sizes)
    g = d.groupby(group)[value]
    n0 = (len(d) - (sizes**2).sum() / len(d)) / (len(sizes) - 1)  # tamanho médio ajustado (grupos desbalanceados)
    ms_b = (sizes * (g.mean() - d[value].mean()) ** 2).sum() / (len(sizes) - 1)
    ms_w = ((d[value] - g.transform("mean")) ** 2).sum() / (len(d) - len(sizes))
    icc_anova = float(max((ms_b - ms_w) / (ms_b + (n0 - 1) * ms_w), 0.0))
    schools = pd.DataFrame({"n": sizes, "raw_deviation": raw, "eb_deviation": re, "reliability": reliability})
    return {"icc": icc, "tau2_between": tau2, "sigma2_within": sigma2, "n_groups": int(len(sizes)), "boundary": boundary, "icc_anova_crosscheck": icc_anova,
            "mean_group_size": m_bar, "design_effect": 1 + (m_bar - 1) * icc,
            "schools": schools.reset_index().rename(columns={"index": group}),
            "note": "desvios EB são encolhidos; comparação entre escolas exige incerteza e nunca ranking punitivo"}
