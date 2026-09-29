"""Estudo de linking longitudinal com duas ondas (P2, seção 10.5).

Desenho de itens comuns (NEAT): forma 1 (onda 1) e forma 2 (onda 2)
compartilham ``n_anchors`` itens; o resto é exclusivo de cada forma. Entre
as ondas a população aprende (média de θ sobe ``growth``) e uma âncora sofre
drift (fica mais fácil por exposição/ensino direcionado).

Cada onda é calibrada separadamente (θ~N(0,1) em cada uma) — portanto o
crescimento "some" sem linking. O estudo mede quanto de crescimento cada
método de linking recupera, com e sem remover a âncora instável.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from edumetria.irt.estimation import fit_2pl
from edumetria.irt.linking import link, transform_theta
from edumetria.irt.models import prob_2pl
from edumetria.irt.scoring import eap_2pl


def run_linking_study(n: int = 2000, n_unique: int = 12, n_anchors: int = 12, growth: float = 0.40,
                      drift_item: int = 0, drift_delta: float = -0.8, seed: int = 11,
                      methods=("mean_mean", "mean_sigma", "stocking_lord", "haebara")) -> dict:
    rng = np.random.default_rng(seed)
    n_items = n_anchors + 2 * n_unique
    a = rng.lognormal(0.1, 0.3, n_items)
    b = rng.normal(0, 1, n_items)
    anchors = list(range(n_anchors))
    form1 = anchors + list(range(n_anchors, n_anchors + n_unique))
    form2 = anchors + list(range(n_anchors + n_unique, n_items))
    names = [f"I{j:02d}" for j in range(n_items)]
    b2 = b.copy()
    b2[drift_item] += drift_delta  # âncora com drift na onda 2

    th1 = rng.normal(0, 1, n)
    th2 = rng.normal(growth, 1, n)
    X1 = (rng.random((n, len(form1))) < prob_2pl(th1, a[form1], b[form1])).astype(float)
    X2 = (rng.random((n, len(form2))) < prob_2pl(th2, a[form2], b2[form2])).astype(float)
    f1 = fit_2pl(X1, [names[j] for j in form1])
    f2 = fit_2pl(X2, [names[j] for j in form2])
    anchor_names = [names[j] for j in anchors]

    e2 = eap_2pl(X2, f2.params["a"].to_numpy(), f2.params["b"].to_numpy())
    e1 = eap_2pl(X1, f1.params["a"].to_numpy(), f1.params["b"].to_numpy())
    rows, details = [], {}
    for keep in ("todas as âncoras", "sem âncora instável"):
        anc = anchor_names
        if keep == "sem âncora instável":
            probe = link(f1.params, f2.params, anchor_names, "stocking_lord", n_boot=100, seed=seed)
            flagged = probe["drift"].loc[probe["drift"]["flag_unstable"], "item"].tolist()
            anc = [x for x in anchor_names if x not in flagged]
            details["flagged_anchors"] = flagged
        for m in methods:
            L = link(f1.params, f2.params, anc, m, n_boot=100, seed=seed)
            th2_linked = transform_theta(e2.theta, L["A"], L["B"])
            est_growth = float(np.mean(th2_linked) - np.mean(e1.theta))
            rows.append({"anchors": keep, "method": m, "A": L["A"], "B": L["B"], "B_se": L["B_se"],
                         "estimated_growth": est_growth, "true_growth": growth,
                         "error": est_growth - growth, "n_anchors": L["n_anchors"]})
    table = pd.DataFrame(rows)
    return {"design": {"n_per_wave": n, "n_anchors": n_anchors, "n_unique_per_form": n_unique, "growth": growth,
                       "drift_item": names[drift_item], "drift_delta_b": drift_delta, "seed": seed},
            "unlinked_growth": float(np.mean(e2.theta) - np.mean(e1.theta)),
            "table": table, **details,
            "note": "sem linking, cada onda fica centrada em 0 e o crescimento desaparece; a âncora com drift "
                    "puxa a transformação e é sinalizada para decisão humana"}
