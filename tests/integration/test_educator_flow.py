"""Jornada do educador ponta a ponta: run S12 → educator_view.json → encaminhamento via API
→ revisão por outra pessoa. Mais um smoke test do painel (modo educador e pesquisador)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from edumetria.pipeline import run_analysis

ROOT = Path(__file__).resolve().parents[2]
SMALL = {"population": {"n_students": 800}}
COORD = {"Authorization": "Bearer demo-token-coord-sch01"}    # coord-bruno (SCH01, SCH02)
COORD2 = {"Authorization": "Bearer demo-token-coord2-sch01"}  # coord-clara (SCH01)
COORD5 = {"Authorization": "Bearer demo-token-coord-sch05"}   # coord-davi (SCH05)
TEACHER = {"Authorization": "Bearer demo-token-docente-sch01"}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("edu")
    res = run_analysis("s12", runs_dir=root / "runs", overrides=SMALL)
    app = create_app(db_path=str(root / "db.sqlite"), runs_root=str(root / "runs"))
    return {"dir": Path(res["run_dir"]), "client": TestClient(app), "store": app.state.store}


def test_run_writes_educator_view_in_manifest(run):
    view = json.loads((run["dir"] / "educator_view.json").read_text(encoding="utf-8"))
    manifest = json.loads((run["dir"] / "manifest.json").read_text(encoding="utf-8"))
    assert view["schema"] == "educator_view/1.0" and view["data_origin"] == "synthetic"
    assert "educator_view.json" in json.dumps(manifest["artifacts"])  # artefato com hash no manifesto


def test_card_forwarded_only_through_human_review(run):
    c = run["client"]
    view = json.loads((run["dir"] / "educator_view.json").read_text(encoding="utf-8"))
    card = next(s for s in view["schools"] if s["school_id"] == "SCH01")["cards"][0]
    body = {"school_id": "SCH01", "subject_ref": card["subject_ref"], "reason": card["title"],
            "evidence_refs": [f"run:{view['run_id']}", *card["evidence_refs"]]}
    assert c.post("/v1/support-cases", json=body, headers=TEACHER).status_code == 403   # docente não cria caso
    assert c.post("/v1/support-cases", json=body, headers=COORD5).status_code == 403    # escola fora do escopo
    assert c.post("/v1/support-cases", json={**body, "tenant_id": "x"}, headers=COORD).status_code == 422
    r = c.post("/v1/support-cases", json=body, headers=COORD)
    assert r.status_code == 201 and r.json()["status"] == "proposed"
    case = r.json()
    case = c.post(f"/v1/support-cases/{case['case_id']}/submit", json={"expected_version": 1}, headers=COORD).json()
    assert case["status"] == "under_review"
    review = {"decision": "approve", "rationale": "checklist completo, sinal além da incerteza [5/5]",
              "expected_version": case["version"]}
    assert c.post(f"/v1/support-cases/{case['case_id']}/reviews", json=review,
                  headers=COORD).status_code == 403                                     # não aprova o próprio caso
    r = c.post(f"/v1/support-cases/{case['case_id']}/reviews", json=review, headers=COORD2)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert run["store"].verify_audit_chain()


def test_dashboard_renders_both_modes_without_api():
    pytest.importorskip("streamlit.testing.v1")
    from streamlit.testing.v1 import AppTest
    runs = list((ROOT / "reports" / "demo_runs").glob("run-s12-*")) + list((ROOT / "runs").glob("run-s12-*"))
    if not runs:
        pytest.skip("nenhum run S12 disponível (rode `edumetria analyze --scenario s12`)")
    at = AppTest.from_file(str(ROOT / "apps" / "dashboard" / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any("DEMONSTRAÇÃO COM DADOS SINTÉTICOS" in e.value for e in at.error)
    at.sidebar.radio[0].set_value("Pesquisador — painel técnico").run()
    assert not at.exception
