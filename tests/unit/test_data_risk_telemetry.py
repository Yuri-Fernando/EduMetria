"""T11–T16 (dados e temporalidade), T25 (logs sem PII), DIF/BH e contratos (T19)."""

import io
import json
import logging

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from edumetria.data_quality.validate import DataQualityError, to_wide, validate_responses
from edumetria.dif.analysis import benjamini_hochberg, mantel_haenszel
from edumetria.domain.contracts import CalibrationRequest, SupportCaseCreate
from edumetria.observability.telemetry import METRICS, get_logger, log_event, parse_traceparent
from edumetria.risk.features import LeakageError, build_snapshot
from edumetria.simulation.generator import generate, load_scenario

SMALL = {"population": {"n_students": 300, "n_schools": 6}}


@pytest.fixture(scope="module")
def ds():
    from edumetria.simulation.generator import _deep_merge
    return generate(_deep_merge(load_scenario("s0"), SMALL))


@pytest.fixture(scope="module")
def ds_admin():
    from edumetria.simulation.generator import _deep_merge
    return generate(_deep_merge(load_scenario("s10"), SMALL))


def test_t11_duplicate_not_counted_twice(ds):
    dup = pd.concat([ds.responses, ds.responses.iloc[:5]], ignore_index=True)
    batch = validate_responses(dup, ds.items)
    codes = {f["code"]: f["count"] for f in batch.report.findings}
    assert codes["duplicate_response"] == 5
    assert len(batch.accepted) == len(ds.responses)


def test_t12_unknown_version_blocks_batch(ds_admin):
    batch = validate_responses(ds_admin.responses, ds_admin.items)
    codes = {f["code"] for f in batch.report.findings}
    assert batch.report.blocking is True
    assert {"unknown_item_version", "invalid_category", "late_arrival", "duplicate_response"} <= codes
    assert not batch.accepted["item_version_id"].str.contains("-v9").any()


def test_schema_incompatible_raises(ds):
    with pytest.raises(DataQualityError):
        validate_responses(ds.responses.drop(columns=["attempt"]), ds.items)


def test_t16_structural_missing_not_zero(ds):
    r = ds.responses.copy()
    first = r["student_ref"].iloc[0]
    m = (r["student_ref"] == first) & (r["instrument_id"] == "math6")
    idx = r[m].index[:3]
    r.loc[idx, ["response_status", "scored_value", "raw_response"]] = ["not_administered", np.nan, None]
    batch = validate_responses(r, ds.items)
    X, persons, cols = to_wide(batch.accepted, "math6", ds.items)
    row = X[persons.index(first)]
    assert np.isnan(row[:3]).all()


def test_student_without_answers_is_kept(ds):
    r = ds.responses.copy()
    first = r["student_ref"].iloc[0]
    m = (r["student_ref"] == first) & (r["instrument_id"] == "math6")
    r.loc[m, ["response_status", "scored_value", "raw_response"]] = ["omitted", np.nan, None]
    batch = validate_responses(r, ds.items)
    X, persons, _ = to_wide(batch.accepted, "math6", ds.items)
    assert first in persons and np.isnan(X[persons.index(first)]).all()


def test_t13_future_feature_is_refused(ds):
    with pytest.raises(LeakageError):
        build_snapshot(ds.attendance, 30, inject_future_feature=True)


def test_scores_not_yet_available_are_refused(ds):
    scores = pd.DataFrame({"student_ref": ds.students["student_ref"], "theta_math": 0.0, "psd_math": 0.3,
                           "theta_belong": 0.0, "psd_belong": 0.3,
                           "available_at": pd.Timestamp("2026-03-02") + pd.Timedelta(days=12)})
    with pytest.raises(LeakageError):
        build_snapshot(ds.attendance, 10, scores)  # escores só existem no dia 12


def test_t14_incomplete_followup_is_censored_not_negative(ds):
    snap = build_snapshot(ds.attendance, 45)
    assert snap["target"].isna().all() and set(snap["target_status"]) == {"censored"}
    snap2 = build_snapshot(ds.attendance, 30)
    assert set(snap2["target"].unique()) <= {0.0, 1.0} and set(snap2["target_status"]) == {"observed"}


def test_t15_school_is_consistent_in_snapshot(ds):
    snap = build_snapshot(ds.attendance, 30)
    ref = ds.students.set_index("student_ref")["school_id"]
    assert (snap.set_index("student_ref")["school_id"] == ref.loc[snap["student_ref"]].to_numpy()).all()


def test_benjamini_hochberg_reference():
    p = np.array([0.01, 0.04, 0.03, 0.005, np.nan])
    # referência: statsmodels multipletests(fdr_bh)
    from statsmodels.stats.multitest import multipletests
    ref = multipletests(p[:4], method="fdr_bh")[1]
    np.testing.assert_allclose(benjamini_hochberg(p)[:4], ref)
    assert np.isnan(benjamini_hochberg(p)[4])


def test_mantel_haenszel_null_is_small():
    rng = np.random.default_rng(4)
    n = 4000
    th = rng.normal(size=n)
    g = rng.integers(0, 2, n)
    X = (rng.random((n, 10)) < 1 / (1 + np.exp(-(th[:, None] - np.linspace(-1, 1, 10))))).astype(float)
    r = mantel_haenszel(X[:, 3], g, X.sum(axis=1))
    assert abs(r["delta_mh"]) < 0.5


def test_t19_body_cannot_carry_identity_or_privilege():
    with pytest.raises(ValidationError):
        CalibrationRequest(instrument_version_id="math6-v0.1", dataset_snapshot_id="synthetic-s0",
                           model_family="2pl", tenant_id="other")
    with pytest.raises(ValidationError):
        SupportCaseCreate(school_id="SCH01", subject_ref="x1", reason="motivo ok", role="admin", confirmed=True)


def test_t24_contract_rejects_arbitrary_family_and_paths():
    with pytest.raises(ValidationError):
        CalibrationRequest(instrument_version_id="math6-v0.1", dataset_snapshot_id="../../etc/passwd",
                           model_family="2pl")
    with pytest.raises(ValidationError):
        CalibrationRequest(instrument_version_id="math6-v0.1", dataset_snapshot_id="synthetic-s0",
                           model_family="system('rm -rf /')")


def test_t25_log_scanner_finds_no_planted_sensitive_markers():
    buf = io.StringIO()
    logger = get_logger("edumetria.test-redaction", stream=buf)
    log_event(logger, "import.row", student_ref="synthetic-student-00001", raw_response="C",
              cpf_note="cpf 123.456.789-09", email_note="aluno@escola.br", authorization="Bearer abc.def",
              job_id="job-1", nested={"answer_key": "B", "ok": 1})
    line = buf.getvalue()
    for marker in ("synthetic-student-00001", "123.456.789-09", "aluno@escola.br", "abc.def", '"B"'):
        assert marker not in line
    payload = json.loads(line)
    assert payload["job_id"] == "job-1" and payload["nested"]["ok"] == 1


def test_metric_labels_are_bounded():
    with pytest.raises(ValueError):
        METRICS.inc("edumetria_x_total", student_id="synthetic-student-1")
    METRICS.inc("edumetria_http_requests_total", route="/v1/unknown/xyz", method="GET", status_class="2xx")
    assert 'route="other"' in METRICS.render()


def test_traceparent_parsing():
    assert parse_traceparent("00-" + "a" * 32 + "-" + "b" * 16 + "-01") == ("a" * 32, "b" * 16)
    assert parse_traceparent("garbage") is None
