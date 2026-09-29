"""T17 (fluxo completo), T24 (job malicioso), T28/T29/T32 (relatórios), S10/S11."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from edumetria.pipeline import PipelineBlocked, run_analysis
from edumetria.simulation.generator import _deep_merge, generate, load_scenario
from edumetria.worker import run_once

SMALL = {"population": {"n_students": 600}}
PSI = {"Authorization": "Bearer demo-token-psicometrista"}
COORD = {"Authorization": "Bearer demo-token-coord-sch01"}
COORD2 = {"Authorization": "Bearer demo-token-coord2-sch01"}
COORD5 = {"Authorization": "Bearer demo-token-coord-sch05"}
OTHER = {"Authorization": "Bearer demo-token-outro-tenant"}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("edm")
    snaps, runs = root / "snapshots", root / "runs"
    generate(_deep_merge(load_scenario("s2"), SMALL)).save(snaps / "synthetic-s2")
    app = create_app(db_path=str(root / "db.sqlite"), runs_root=str(runs))
    return {"client": TestClient(app), "store": app.state.store, "snaps": snaps, "runs": runs}


def test_auth_required(env):
    assert env["client"].get("/v1/calibrations").status_code == 401
    assert env["client"].get("/v1/calibrations", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_t17_import_calibrate_release_score_report(env):
    c = env["client"]
    body = {"instrument_version_id": "math6-v0.1", "dataset_snapshot_id": "synthetic-s2", "model_family": "2pl",
            "purpose": "simulation", "seed": 20260928}
    r = c.post("/v1/calibrations", json=body, headers={**PSI, "Idempotency-Key": "k-1"})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    r2 = c.post("/v1/calibrations", json=body, headers={**PSI, "Idempotency-Key": "k-1"})
    assert r2.status_code == 200 and r2.json()["job_id"] == job_id  # idempotente
    assert c.get(f"/v1/jobs/{job_id}", headers=PSI).json()["status"] == "queued"

    res = run_once(env["store"], runs_dir=env["runs"], snapshot_root=env["snaps"], overrides=SMALL)
    assert res["status"] == "succeeded", res
    job = c.get(f"/v1/jobs/{job_id}", headers=PSI).json()
    cid = job["result"]["calibration_id"]

    # escore antes da liberação humana → 409
    r = c.post("/v1/scores", json={"calibration_id": cid, "subject_refs": ["synthetic-student-00001"]}, headers=PSI)
    assert r.status_code == 409
    # coordenação não libera calibração
    r = c.post(f"/v1/calibrations/{cid}/release", json={"rationale": "tentativa sem papel", "expected_version": 1},
               headers=COORD)
    assert r.status_code == 403
    r = c.post(f"/v1/calibrations/{cid}/release",
               json={"rationale": "convergência e diagnósticos revisados", "expected_version": 1}, headers=PSI)
    assert r.status_code == 200 and r.json()["status"] == "released"
    r = c.post("/v1/scores", json={"calibration_id": cid, "subject_refs": ["synthetic-student-00001", "nao-existe"]},
               headers=PSI)
    assert r.status_code == 200
    s0, s1 = r.json()
    assert s0["status"] in ("computed", "insufficient_evidence") and s0["method"] == "EAP"
    assert (s0["estimate"] is None) == (s0["status"] != "computed")
    assert s1["status"] == "not_found"
    ev = c.get(f"/v1/evidence-reports/{cid}", headers=PSI).json()
    assert ev["data_origin"] == "synthetic" and ev["response_process"]["status"] == "not_assessed"
    # T28: relatório corresponde ao run da calibração, não ao último run global
    assert ev["lineage"]["report"] == job["result"]["run_id"]
    # outro tenant não enxerga
    assert c.get(f"/v1/calibrations/{cid}", headers=OTHER).status_code == 404
    audit = c.get("/v1/audit", headers=PSI).json()
    assert audit["chain_valid"] and any(e["action"] == "calibration.released" for e in audit["events"])


def test_t24_malicious_snapshot_rejected(env):
    c = env["client"]
    bad = {"instrument_version_id": "math6-v0.1", "dataset_snapshot_id": "../../../windows", "model_family": "2pl"}
    assert c.post("/v1/calibrations", json=bad, headers=PSI).status_code == 422
    bad2 = {**bad, "dataset_snapshot_id": "synthetic-s2", "model_family": "system"}
    assert c.post("/v1/calibrations", json=bad2, headers=PSI).status_code == 422
    body = {"instrument_version_id": "math6-v0.1", "dataset_snapshot_id": "nao-existe", "model_family": "2pl"}
    job_id = c.post("/v1/calibrations", json=body, headers=PSI).json()["job_id"]
    res = run_once(env["store"], runs_dir=env["runs"], snapshot_root=env["snaps"])
    assert res["status"] == "failed" and res["error_code"] == "invalid_input"
    assert c.get(f"/v1/jobs/{job_id}", headers=PSI).json()["status"] == "failed"


def test_t19_identity_in_body_rejected(env):
    body = {"school_id": "SCH01", "subject_ref": "synthetic-student-00002", "reason": "faltas em alta",
            "tenant_id": "other-tenant", "role": "psychometrician"}
    assert env["client"].post("/v1/support-cases", json=body, headers=COORD).status_code == 422


def test_case_flow_via_api_with_isolation(env):
    c = env["client"]
    r = c.post("/v1/support-cases", json={"school_id": "SCH01", "subject_ref": "synthetic-student-00003",
                                          "reason": "queda de frequência nas últimas semanas"}, headers=COORD)
    assert r.status_code == 201
    case = r.json()
    assert c.get(f"/v1/support-cases/{case['case_id']}", headers=COORD5).status_code == 404
    r = c.post(f"/v1/support-cases/{case['case_id']}/transition",
               json={"to_status": "in_progress", "note": "tentar sem aprovação", "expected_version": 1}, headers=COORD2)
    assert r.status_code == 409
    case = c.post(f"/v1/support-cases/{case['case_id']}/submit", json={"expected_version": 1}, headers=COORD).json()
    r = c.post(f"/v1/support-cases/{case['case_id']}/reviews",
               json={"decision": "approve", "rationale": "plano de apoio adequado", "expected_version": case["version"]},
               headers=COORD2)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert "edumetria_http_requests_total" in c.get("/metrics").text
    assert c.get("/health/ready").json()["llm"].startswith("disabled")


def test_s10_blocked_then_resolved(tmp_path):
    with pytest.raises(PipelineBlocked) as exc:
        run_analysis("s10", runs_dir=tmp_path, overrides=SMALL)
    st = json.loads((exc.value.run_dir / "run_status.json").read_text(encoding="utf-8"))
    assert st["status"] == "blocked_by_data_quality"
    assert not (exc.value.run_dir / "evidence_report.json").exists()  # nada verde num run bloqueado (T29)
    r = run_analysis("s10", runs_dir=tmp_path, overrides=SMALL, resolve_quarantine=True)
    assert r["status"] == "succeeded"


def test_s11_leakage_blocked_and_reports_marked_synthetic(tmp_path):
    r = run_analysis("s11", runs_dir=tmp_path, overrides=SMALL)
    out = Path(r["run_dir"])
    risk = json.loads((out / "risk_evaluation.json").read_text(encoding="utf-8"))
    assert risk["leakage_check"] == {"injected": True, "blocked": True, "message": risk["leakage_check"]["message"]}
    html = (out / "technical_report.html").read_text(encoding="utf-8")
    assert "DADOS SINTÉTICOS" in html and r["run_id"] in html  # T32
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_origin"] == "synthetic" and "technical_report.html" in manifest["artifacts"]


def test_pipeline_degrades_when_grm_cannot_be_fitted(tmp_path):
    """Regressão: com N=1000 em S2 a categoria 1 de B09 fica vazia → GRM falha explicitamente e o
    risco B2 usa só os escores de matemática (antes quebrava com KeyError)."""
    r = run_analysis("s2", runs_dir=tmp_path, overrides={"population": {"n_students": 1000}})
    out = Path(r["run_dir"])
    diag = json.loads((out / "fit_diagnostics.json").read_text(encoding="utf-8"))
    risk = json.loads((out / "risk_evaluation.json").read_text(encoding="utf-8"))
    assert diag["belong6"]["status"] == "failed" and "categoria vazia" in diag["belong6"]["error"]
    assert risk["b2_psycho_features"] == ["theta_math", "psd_math"]
