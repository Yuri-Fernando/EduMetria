"""T05, T06 — TCT com referência independente; validade de conteúdo."""

import numpy as np
import pandas as pd
import pytest

from edumetria.ctt.analysis import alpha_with_ci, cronbach_alpha, item_statistics
from edumetria.validity.content import aiken_v, content_validity


def kr20(X):
    k = X.shape[1]
    p = X.mean(axis=0)
    return k / (k - 1) * (1 - (p * (1 - p)).sum() / X.sum(axis=1).var(ddof=0))


def test_t05_alpha_matches_kr20_and_hand_fixture():
    # fixture pequena calculada à mão: α = 0,75 (3 itens)
    X = np.array([[1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0], [1, 1, 1], [0, 0, 0]], dtype=float)
    k = 3
    item_var = X.var(axis=0, ddof=1).sum()
    tot_var = X.sum(axis=1).var(ddof=1)
    hand = k / (k - 1) * (1 - item_var / tot_var)
    assert cronbach_alpha(X) == pytest.approx(hand)
    # KR-20 (variâncias populacionais) coincide com α para itens dicotômicos
    rng = np.random.default_rng(1)
    Y = (rng.random((500, 10)) < rng.uniform(0.3, 0.8, 10)).astype(float)
    Y[:250] = np.maximum(Y[:250], (rng.random((250, 10)) < 0.3))
    assert cronbach_alpha(Y) == pytest.approx(kr20(Y), rel=1e-9)


def test_point_biserial_corrected_matches_numpy():
    rng = np.random.default_rng(2)
    X = (rng.random((400, 6)) < 0.6).astype(float)
    st = item_statistics(X, [f"i{j}" for j in range(6)])
    rest = X.sum(axis=1) - X[:, 0]
    assert st.loc[0, "r_pbis_corrected"] == pytest.approx(np.corrcoef(X[:, 0], rest)[0, 1])


def test_t06_constant_item_and_structural_missing_states():
    X = np.array([[1, 1, np.nan], [1, 0, np.nan], [1, 1, np.nan], [1, 0, np.nan]], dtype=float)
    st = item_statistics(X, ["const", "ok", "never"], n_administered=np.array([4, 4, 0]))
    assert st.loc[0, "state"] == "constant_item" and pd.isna(st.loc[0, "r_pbis_corrected"])
    assert st.loc[2, "state"] == "not_administered" and pd.isna(st.loc[2, "p_value"])


def test_alpha_not_estimable_without_variance():
    X = np.ones((50, 4))
    assert cronbach_alpha(X) is None
    assert alpha_with_ci(X)["alpha"] is None


def test_aiken_v_known_values():
    assert aiken_v(np.array([4, 4, 4, 4]))["aiken_v"] == pytest.approx(1.0)
    assert aiken_v(np.array([1, 1, 1]))["aiken_v"] == pytest.approx(0.0)
    r = aiken_v(np.array([3, 4, 3, 4, 2, 4]))
    assert r["aiken_v"] == pytest.approx((2 + 3 + 2 + 3 + 1 + 3) / (6 * 3))
    assert r["ci_low"] < r["aiken_v"] < r["ci_high"]


def test_icvi_and_simulated_evidence_not_human():
    rows = []
    for item, ratings in {"X1": [4, 4, 3, 3, 4, 3], "X2": [2, 1, 3, 2, 2, 4]}.items():
        for j, r in enumerate(ratings):
            for crit in ("relevancia", "alinhamento"):
                rows.append({"item_id": item, "judge_ref": f"j{j}", "criterion": crit, "rating": r,
                             "evidence_origin": "simulated_review", "comment": ""})
    cv = content_validity(pd.DataFrame(rows))
    by = {p["item_id"]: p for p in cv["items"]}
    assert by["X1"]["i_cvi_relevance"] == pytest.approx(1.0)
    assert by["X2"]["i_cvi_relevance"] == pytest.approx(2 / 6)
    assert cv["s_cvi_ave"] == pytest.approx((1 + 2 / 6) / 2)
    assert "X2" in cv["items_needing_review"]
    assert cv["counts_as_human_evidence"] is False
