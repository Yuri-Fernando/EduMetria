"""P2 — linking, CAT, multinível, desenho de impacto e S6 (verificação com verdade conhecida)."""

import numpy as np
import pandas as pd
import pytest

from edumetria.data_quality.validate import to_wide, validate_responses
from edumetria.impact.design import clusters_needed, es_to_risk_difference, mdes_cluster_rct
from edumetria.irt.cat import fixed_form, simulate_cat, summarize
from edumetria.irt.linking import METHODS, link, transform
from edumetria.irt.scoring import dimensionality_screen
from edumetria.risk.multilevel import school_icc
from edumetria.simulation.generator import generate


@pytest.mark.parametrize("method", list(METHODS))
def test_linking_recovers_known_transformation(method):
    """Parâmetros 'novos' = transformação exata dos de referência ⇒ A, B recuperados."""
    rng = np.random.default_rng(0)
    a, b = rng.lognormal(0, 0.3, 15), rng.normal(0, 1, 15)
    A, B = 1.3, -0.4  # θ_ref = A·θ_new + B  ⇒  b_new = (b_ref − B)/A, a_new = a_ref·A
    ref = pd.DataFrame({"item": [f"I{i}" for i in range(15)], "a": a, "b": b})
    new = pd.DataFrame({"item": ref["item"], "a": a * A, "b": (b - B) / A})
    r = link(ref, new, list(ref["item"]), method, n_boot=20)
    assert r["A"] == pytest.approx(A, abs=1e-3) and r["B"] == pytest.approx(B, abs=1e-3)
    back = transform(new, r["A"], r["B"])
    np.testing.assert_allclose(back["b"], b, atol=1e-3)


def test_linking_flags_drifted_anchor():
    rng = np.random.default_rng(1)
    a, b = rng.lognormal(0, 0.3, 12), rng.normal(0, 1, 12)
    ref = pd.DataFrame({"item": [f"I{i}" for i in range(12)], "a": a, "b": b})
    b_new = b.copy()
    b_new[3] += 1.5
    new = pd.DataFrame({"item": ref["item"], "a": a, "b": b_new})
    r = link(ref, new, list(ref["item"]), "mean_sigma", n_boot=20)
    assert r["drift"].loc[r["drift"]["flag_unstable"], "item"].tolist() == ["I3"]


@pytest.mark.statistical
def test_cat_uses_fewer_items_with_comparable_precision():
    rng = np.random.default_rng(2)
    a, b = rng.lognormal(0.2, 0.3, 100), rng.normal(0, 1.2, 100)
    th = rng.normal(0, 1, 200)
    cat = summarize(simulate_cat(a, b, th, se_target=0.35, max_items=24, seed=3))
    fix = summarize(fixed_form(a, b, th, np.argsort(-a)[:24], seed=3))
    assert cat["mean_items"] < 20
    assert cat["rmse"] < fix["rmse"] + 0.08


def test_icc_recovery_and_boundary():
    rng = np.random.default_rng(3)
    s = np.repeat(np.arange(50), 40)
    u = rng.normal(0, np.sqrt(0.2), 50)
    y = u[s] + rng.normal(0, np.sqrt(0.8), len(s))
    realized = np.var(u, ddof=1) / (np.var(u, ddof=1) + 0.8)
    r = school_icc(pd.DataFrame({"theta": y, "school_id": s.astype(str)}))
    assert r["icc"] == pytest.approx(realized, abs=0.05)
    assert r["icc"] == pytest.approx(r["icc_anova_crosscheck"], abs=0.02)
    z = school_icc(pd.DataFrame({"theta": rng.normal(size=2000), "school_id": s.astype(str)}))
    assert z["icc"] < 0.02


def test_mdes_formula_reference_values():
    # sem ICC e com P=0,5: MDES = M·√(4/(J·n)); J=40, n=50 ⇒ √(4/2000)
    from scipy import stats
    M = stats.t.ppf(0.975, 38) + stats.t.ppf(0.8, 38)
    assert mdes_cluster_rct(40, 50, 0.0) == pytest.approx(M * np.sqrt(4 / 2000))
    assert mdes_cluster_rct(20, 100, 0.2) > mdes_cluster_rct(40, 100, 0.2) > mdes_cluster_rct(40, 100, 0.05)
    J = clusters_needed(0.25, 100, 0.1)
    assert mdes_cluster_rct(J, 100, 0.1) <= 0.25 < mdes_cluster_rct(J - 2, 100, 0.1)
    assert es_to_risk_difference(0.2, 0.5) == pytest.approx(0.1)


def test_s6_multidimensionality_is_detectable():
    ratios = {}
    for sc in ("s0", "s6"):
        ds = generate(sc)
        X, _, _ = to_wide(validate_responses(ds.responses, ds.items).accepted, "math6", ds.items)
        ratios[sc] = dimensionality_screen(X)["ratio_first_second"]
    assert ratios["s6"] < 0.6 * ratios["s0"]
