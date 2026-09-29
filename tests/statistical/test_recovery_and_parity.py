"""Recuperação estatística (H1), DIF (H2, T10) e paridade com R/mirt (T07 ext.).

Testes com seed fixa são testes de regressão do software, não validação do
instrumento. A paridade com mirt é pulada se Rscript + mirt não existirem.
"""

import numpy as np
import pytest

from edumetria.dif.analysis import run_dif
from edumetria.irt import r_engine
from edumetria.irt.estimation import fit_2pl, fit_grm
from edumetria.irt.models import grm_category_probs, prob_2pl
from edumetria.irt.scoring import eap_2pl


def _sim_2pl(n=2000, J=24, seed=11, missing=0.02):
    rng = np.random.default_rng(seed)
    a, b, th = rng.lognormal(0.1, 0.3, J), rng.normal(0, 1, J), rng.normal(0, 1, n)
    X = (rng.random((n, J)) < prob_2pl(th, a, b)).astype(float)
    X[rng.random((n, J)) < missing] = np.nan
    return X, a, b, th


def _sim_grm(n=2000, J=12, seed=12):
    rng = np.random.default_rng(seed)
    a = rng.lognormal(0.2, 0.25, J)
    B = np.sort(rng.normal(0, 0.8, (J, 3)), axis=1) + np.array([-1.0, 0.0, 1.0])
    th = rng.normal(0, 1, n)
    Y = np.zeros((n, J))
    for j in range(J):
        P = grm_category_probs(th, a[j], B[j])
        Y[:, j] = (rng.random(n)[:, None] > np.cumsum(P, axis=1)).sum(axis=1)
    return np.minimum(Y, 3), a, B


@pytest.mark.statistical
def test_h1_2pl_recovery_s0_targets():
    X, a, b, th = _sim_2pl()
    f = fit_2pl(X)
    assert f.converged
    assert np.sqrt(np.mean((f.params["a"] - a) ** 2)) <= 0.30
    assert np.sqrt(np.mean((f.params["b"] - b) ** 2)) <= 0.30
    e = eap_2pl(X, f.params["a"].to_numpy(), f.params["b"].to_numpy())
    assert np.corrcoef(e.theta, th)[0, 1] > 0.85


@pytest.mark.statistical
def test_h1_grm_recovery():
    Y, a, B = _sim_grm()
    f = fit_grm(Y, 4)
    assert f.converged
    assert np.sqrt(np.mean((f.params["a"] - a) ** 2)) <= 0.30
    assert np.sqrt(np.mean((f.params[["b1", "b2", "b3"]].to_numpy() - B) ** 2)) <= 0.30


@pytest.mark.statistical
def test_t10_dif_sensitivity_and_false_positive_control():
    """Não exige detectar todo item numa realização: exige ≥2 de 3 e FP ≤ 2 de 21."""
    rng = np.random.default_rng(21)
    n, J = 2000, 24
    a, b, th = rng.lognormal(0.1, 0.3, J), rng.normal(0, 1, J), rng.normal(0, 1, n)
    grp = np.where(rng.random(n) < 0.5, "B", "A")
    names = [f"A{j + 1:02d}" for j in range(J)]
    dif = {"A05": 0.6, "A13": 0.5, "A21": -0.55}
    Bm = np.tile(b, (n, 1))
    for it, d in dif.items():
        Bm[grp == "B", names.index(it)] += d
    X = (rng.random((n, J)) < 1 / (1 + np.exp(-a * (th[:, None] - Bm)))).astype(float)
    res = run_dif(X, names, grp).set_index("item")
    hits = sum(bool(res.loc[i, "flag_uniform"]) for i in dif)
    fps = int(res.drop(index=list(dif))["flagged"].sum())
    assert hits >= 2 and fps <= 2
    assert (res["review_state"].isin(["pending_human_review", "no_action"])).all()


def test_small_groups_are_insufficient_not_absent():
    X, *_ = _sim_2pl(n=250, J=8)
    grp = np.array(["A"] * 200 + ["B"] * 50)
    res = run_dif(X, [f"i{j}" for j in range(8)], grp)
    assert set(res["status"]) == {"insufficient_evidence"}


R_OK = r_engine.available()
r_available = pytest.mark.skipif(not R_OK, reason="Rscript + mirt indisponíveis")


@pytest.mark.r_parity
def test_r_required_when_flagged():
    """Com EDUMETRIA_REQUIRE_R=1 (job de paridade da CI), ausência de R/mirt é falha — nunca skip silencioso."""
    import os
    if os.environ.get("EDUMETRIA_REQUIRE_R") == "1":
        assert R_OK, "EDUMETRIA_REQUIRE_R=1 mas Rscript + mirt não estão disponíveis"


@pytest.mark.r_parity
@r_available
def test_parity_2pl_with_mirt():
    X, *_ = _sim_2pl(seed=3)
    names = [f"i{j + 1:02d}" for j in range(X.shape[1])]
    py = fit_2pl(X, names)
    r = r_engine.fit_mirt(X, names, "2pl")
    import pandas as pd
    ir = pd.DataFrame(r["irt_pars"])
    assert py.loglik == pytest.approx(r["loglik"], abs=0.05)
    assert np.max(np.abs(py.params["a"].to_numpy() - ir["a"].to_numpy())) < 5e-3
    assert np.max(np.abs(py.params["b"].to_numpy() - ir["b"].to_numpy())) < 5e-3
    e = eap_2pl(X, py.params["a"].to_numpy(), py.params["b"].to_numpy())
    assert np.nanmax(np.abs(e.theta - np.array(r["eap"]))) < 5e-3
    se = pd.DataFrame(r["se_table"])
    se_a = se[se["par"].str.endswith(".a1")]["se"].to_numpy()
    assert np.max(np.abs(py.params["se_a"].to_numpy() - se_a) / se_a) < 0.01


@pytest.mark.r_parity
@r_available
def test_parity_grm_with_mirt():
    Y, *_ = _sim_grm(seed=4)
    names = [f"b{j + 1:02d}" for j in range(Y.shape[1])]
    py = fit_grm(Y, 4, names)
    r = r_engine.fit_mirt(Y, names, "grm")
    import pandas as pd
    ir = pd.DataFrame(r["irt_pars"])
    assert py.loglik == pytest.approx(r["loglik"], abs=0.05)
    assert np.max(np.abs(py.params["a"].to_numpy() - ir["a"].to_numpy())) < 5e-3
    for k in ("b1", "b2", "b3"):
        assert np.max(np.abs(py.params[k].to_numpy() - ir[k].to_numpy())) < 5e-3


@pytest.mark.r_parity
@r_available
def test_r_engine_rejects_non_allowlisted_family():
    with pytest.raises(ValueError):
        r_engine.fit_mirt(np.zeros((3, 2)), ["a", "b"], "3pl; system('x')")
