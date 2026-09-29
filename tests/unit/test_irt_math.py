"""T01–T04, T07, T08 — matemática da TRI e escores."""

import numpy as np
import pytest

from edumetria.irt.estimation import fit_2pl, fit_grm
from edumetria.irt.models import (b_from_d, d_from_b, grm_category_probs, grm_information, info_2pl, prob_2pl,
                                  total_information)
from edumetria.irt.scoring import eap_2pl, mle_2pl


def test_t01_2pl_half_at_location():
    assert prob_2pl(np.array([0.0]), np.array([1.0]), np.array([0.0]))[0, 0] == pytest.approx(0.5)


def test_t02_monotone_and_bounded():
    th = np.linspace(-6, 6, 101)
    P = prob_2pl(th, np.array([0.3, 1.2, 2.5]), np.array([-1.0, 0.0, 2.0]))
    assert np.all((P >= 0) & (P <= 1))
    assert np.all(np.diff(P, axis=0) > 0)


def test_t03_grm_categories_sum_to_one():
    th = np.linspace(-4, 4, 50)
    P = grm_category_probs(th, 1.4, np.array([-1.0, 0.2, 1.5]))
    assert np.all(P >= 0)
    np.testing.assert_allclose(P.sum(axis=1), 1.0, atol=1e-12)


def test_t03b_grm_rejects_unordered_thresholds():
    with pytest.raises(ValueError):
        grm_category_probs(np.array([0.0]), 1.0, np.array([0.5, 0.2, 1.0]))


def test_t04_d_b_conversion_roundtrip():
    a, b = np.array([0.8, 1.7]), np.array([-0.4, 1.3])
    np.testing.assert_allclose(b_from_d(a, d_from_b(a, b)), b)
    with pytest.raises(ValueError):
        b_from_d(np.array([0.0]), np.array([1.0]))


def test_information_matches_numeric_definition():
    th, a, b = np.array([0.3]), np.array([1.5]), np.array([0.1])
    p = prob_2pl(th, a, b)[0, 0]
    assert info_2pl(th, a, b)[0, 0] == pytest.approx(1.5**2 * p * (1 - p))
    assert total_information(np.array([0.0]), np.array([1.0, 1.0]), np.array([0.0, 0.0]))[0] == pytest.approx(0.5)


def test_grm_information_positive():
    assert np.all(grm_information(np.linspace(-3, 3, 20), 1.2, np.array([-1, 0, 1])) > 0)


def test_t07_eap_matches_bruteforce_integration():
    """EAP concorda com integração numérica independente (grade densa, mesmo prior)."""
    a, b = np.array([1.2, 0.8, 1.6, 1.0]), np.array([-0.5, 0.3, 1.0, -1.2])
    x = np.array([[1, 0, 1, np.nan]])
    res = eap_2pl(x, a, b, n_quad=61)
    grid = np.linspace(-8, 8, 20001)
    prior = np.exp(-grid**2 / 2)
    P = 1 / (1 + np.exp(-a[None, :3] * (grid[:, None] - b[None, :3])))
    lik = P[:, 0] * (1 - P[:, 1]) * P[:, 2]
    post = lik * prior
    post /= np.trapezoid(post, grid)
    mean = np.trapezoid(grid * post, grid)
    sd = np.sqrt(np.trapezoid((grid - mean) ** 2 * post, grid))
    assert res.theta[0] == pytest.approx(mean, abs=2e-3)
    assert res.posterior_sd[0] == pytest.approx(sd, abs=2e-3)


def test_t08_extremes_and_no_information():
    a, b = np.ones(5), np.linspace(-1, 1, 5)
    X = np.array([[1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [np.nan] * 5])
    r = eap_2pl(X, a, b)
    assert np.isfinite(r.theta[0]) and np.isfinite(r.theta[1])  # EAP finito (encolhimento ao prior)
    assert r.theta[0] > 0 > r.theta[1]
    assert np.isnan(r.theta[2]) and r.status[2] == "insufficient_evidence"
    assert mle_2pl(X[0], a, b)["diverged"] is True  # MLE diverge em padrão extremo
    assert mle_2pl(X[2], a, b)["status"] == "insufficient_evidence"


def test_constant_item_is_not_estimable():
    rng = np.random.default_rng(0)
    X = (rng.random((300, 5)) < 0.6).astype(float)
    X[:, 2] = 1.0
    with pytest.raises(ValueError, match="constantes"):
        fit_2pl(X)


def test_grm_empty_category_raises():
    rng = np.random.default_rng(0)
    Y = rng.integers(0, 3, size=(300, 4)).astype(float)  # categoria 3 nunca ocorre
    with pytest.raises(ValueError, match="categoria vazia"):
        fit_grm(Y, n_categories=4)


def test_missing_is_not_scored_as_zero():
    """Missing (NaN) não entra na verossimilhança: remover a coluna ≡ deixá-la NaN."""
    a, b = np.array([1.0, 1.3, 0.7]), np.array([0.0, 0.5, -0.5])
    with_nan = eap_2pl(np.array([[1, np.nan, 0]]), a, b)
    without = eap_2pl(np.array([[1, 0]]), a[[0, 2]], b[[0, 2]])
    as_zero = eap_2pl(np.array([[1, 0, 0]]), a, b)
    assert with_nan.theta[0] == pytest.approx(without.theta[0])
    assert with_nan.theta[0] != pytest.approx(as_zero.theta[0])
