"""Visão do Educador (EduMetria Social): agregados, privacidade, missing ≠ zero e controle humano."""

import json

import numpy as np
import pandas as pd
import pytest

from edumetria.data_quality.validate import to_wide, validate_responses
from edumetria.irt.estimation import fit_2pl
from edumetria.irt.scoring import eap_2pl
from edumetria.reporting.educator import (SYNTHETIC_LABEL, axis_expected_observed, build_educator_view,
                                          display_count, load_config, render_school_summary_html)
from edumetria.simulation.generator import _deep_merge, generate, load_scenario

RISK = {"models": {"B1": {"roc_auc": 0.87}, "B2": {"roc_auc": 0.875}},
        "bootstrap": {"B2_minus_B1_auc": {"mean": 0.003, "ci95": [-0.03, 0.04]}},
        "target_definition": "proxy sintético"}

# Hash do conjunto S0 registrado no run de demonstração da v0.3.0
# (reports/demo_runs/run-s0-20260929T152744-6b9ca7/manifest.json).
S0_DATASET_HASH_V030 = "c46e9c4e78c04f5cee4c42b9afd719fd2042e8666ebe049899184b5a3685f338"


def test_display_count_suppresses_small_cells():
    assert display_count(0, 5) == "0"
    assert display_count(3, 5) == "menos de 5"
    assert display_count(5, 5) == "5"


def test_missing_never_becomes_zero_in_axis_signal():
    a, b = np.array([1.0, 1.2, 0.8, 1.0]), np.array([0.0, 0.5, -0.5, 0.2])
    X = np.array([[1, 0, np.nan, np.nan],      # eixo (itens 2 e 3) totalmente ausente
                  [1, 1, 1, np.nan],
                  [0, 0, 0, 0]], dtype=float)
    mask = np.array([False, False, True, True])
    df = axis_expected_observed(X, a, b, mask)
    assert df.loc[0, "n_responses"] == 0 and df.loc[0, "expected"] == pytest.approx(0.0)
    assert df.loc[1, "n_responses"] == 1   # só o item respondido entra no observado e no esperado
    assert (df["variance"] >= 0).all()


def test_generator_unchanged_for_existing_scenarios():
    ds = generate(load_scenario("s0"))
    batch = validate_responses(ds.responses, ds.items, snapshot_prefix="synthetic-s0")
    assert batch.dataset_hash == S0_DATASET_HASH_V030
    assert ds.truth["school_axis_effects"] == [] and ds.truth["school_theta_effects"] == {}


@pytest.fixture(scope="module")
def small_view():
    cfg = _deep_merge(load_scenario("s12"), {"population": {"n_students": 800}})
    ds = generate(cfg)
    batch = validate_responses(ds.responses, ds.items, snapshot_prefix="t-s12")
    X, persons, cols = to_wide(batch.accepted, "math6", ds.items)
    fit = fit_2pl(X, [c.split("-")[1] for c in cols])
    a, b = fit.params["a"].to_numpy(), fit.params["b"].to_numpy()
    sc = eap_2pl(X, a, b).to_frame(persons).rename(columns={
        "theta_eap": "theta_math", "posterior_sd": "psd_math", "q05": "q05_math", "q95": "q95_math",
        "n_answered": "n_answered_math", "status": "status_math"})
    sc["school_id"] = ds.students.set_index("student_ref").loc[sc["subject_ref"], "school_id"].to_numpy()
    view = build_educator_view(run_id="run-test", scenario=cfg, X=X, persons=persons, item_cols=cols,
                               items=ds.items, a=a, b=b, scores=sc, attendance=ds.attendance, risk=RISK,
                               converged=fit.converged)
    return view, ds


def test_view_is_aggregate_only_and_labelled_synthetic(small_view):
    view, ds = small_view
    blob = json.dumps(view, ensure_ascii=False, default=str)
    assert "synthetic-student" not in blob          # nenhum identificador de estudante
    assert view["data_origin"] == "synthetic" and view["label"] == SYNTHETIC_LABEL
    assert {s["school_id"] for s in view["schools"]} == set(ds.students["school_id"])
    for s in view["schools"]:
        m = s["measure"]
        assert m["n_clearly_below"] + m["n_uncertain"] + m["n_clearly_above"] == m["n_computed"]
        assert m["n_computed"] + m["n_insufficient"] == m["n_students"]


def test_cards_are_consultive_and_require_human_review(small_view):
    view, _ = small_view
    cards = [c for s in view["schools"] for c in s["cards"]]
    assert cards
    for c in cards:
        assert c["requires_human_review"] is True and c["decided_by_model"] is False
        assert c["could_be_wrong"] and c["suggested_discussion"]["id"].startswith("PB-")
        assert len(c["subject_ref"]) <= 64 and c["subject_ref"].startswith("turma-")


def test_risk_never_drives_prioritization(small_view):
    view, _ = small_view
    assert view["risk_model"]["used_for_prioritization"] is False
    assert "NÃO gera prioridades" in view["risk_model"]["message"]
    assert not any("risco" in c["kind"] for s in view["schools"] for c in s["cards"])


def test_export_summary_has_banner_and_no_student_ids(small_view):
    view, _ = small_view
    html_doc = render_school_summary_html(view, "SCH01", {"code_commit": "abc123", "seed": 1})
    assert SYNTHETIC_LABEL in html_doc and "synthetic-student" not in html_doc
    assert "não é prescrição" in html_doc and "Não decide sozinho" in html_doc


def test_display_config_is_documented():
    cfg = load_config()
    assert "ilustrativo" in cfg["proficiency"]["reference_cut_label"]
    assert cfg["privacy"]["small_cell"] >= 5
