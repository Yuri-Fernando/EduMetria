"""P1 — OIDC, tracing OTel, CRUD editorial, copiloto e integrações verificadas."""

import importlib.util
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from apps.api.main import create_app
from edumetria.integrations.verify import repo_path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("dev_oidc", ROOT / "scripts" / "dev_oidc.py")
dev_oidc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev_oidc)

H = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
AUTH, JUDGES = H("demo-token-autora"), [H(f"demo-token-juiz-{i}") for i in (1, 2, 3)]
PSI, COORD = H("demo-token-psicometrista"), H("demo-token-coord-sch01")
RATINGS = {"relevancia": 4, "clareza": 3, "alinhamento": 4, "adequacao_etaria": 4, "acessibilidade": 3}
CONTENT = {"stem": "Quanto é 7 × 6?", "options": {"A": "42", "B": "36", "C": "48", "D": "13"}, "key": "A",
           "axis": "numeros_operacoes", "demand": "aplicacao"}


@pytest.fixture
def client(tmp_path):
    exp = InMemorySpanExporter()
    app = create_app(db_path=str(tmp_path / "db.sqlite"), runs_root=str(tmp_path / "runs"), span_exporter=exp)
    return TestClient(app), exp


# ------------------------------------------------------------------ OIDC
@pytest.fixture
def oidc(tmp_path, monkeypatch):
    d = tmp_path / "oidc"
    dev_oidc.init(d)
    monkeypatch.setenv("EDUMETRIA_AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", dev_oidc.ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", dev_oidc.AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_FILE", str(d / "jwks.json"))
    return d


def test_oidc_valid_token_maps_claims(client, oidc):
    c, _ = client
    tok = dev_oidc.mint(oidc, "psi-oidc", "psychometrician", "demo-tenant")
    assert c.get("/v1/calibrations", headers=H(tok)).status_code == 200


@pytest.mark.parametrize("case", ["expired", "wrong_audience", "wrong_issuer", "bad_role", "alg_none", "other_key"])
def test_oidc_rejections(client, oidc, tmp_path, case):
    c, _ = client
    if case == "expired":
        tok = dev_oidc.mint(oidc, "u", "psychometrician", "demo-tenant", ttl=-120)
    elif case == "wrong_audience":
        tok = dev_oidc.mint(oidc, "u", "psychometrician", "demo-tenant", audience="outra-api")
    elif case == "wrong_issuer":
        tok = dev_oidc.mint(oidc, "u", "psychometrician", "demo-tenant", issuer="https://idp.malicioso")
    elif case == "bad_role":
        tok = dev_oidc.mint(oidc, "u", "superadmin", "demo-tenant")
    elif case == "alg_none":
        import jwt
        tok = jwt.encode({"sub": "u", "iss": dev_oidc.ISSUER, "aud": dev_oidc.AUDIENCE, "exp": int(time.time()) + 60,
                          "iat": int(time.time()), "edumetria_role": "psychometrician",
                          "edumetria_tenant": "demo-tenant"}, key=None, algorithm="none")
    else:  # assinado com outra chave, mesmo kid
        other = tmp_path / "other"
        dev_oidc.init(other)
        tok = dev_oidc.mint(other, "u", "psychometrician", "demo-tenant")
    assert c.get("/v1/calibrations", headers=H(tok)).status_code == 401


def test_demo_tokens_rejected_in_oidc_mode(client, oidc):
    c, _ = client
    assert c.get("/v1/calibrations", headers=PSI).status_code == 401


# ------------------------------------------------------------------ tracing
def test_tracing_continues_traceparent_without_pii(client):
    c, exp = client
    parent = "00-" + "ab" * 16 + "-" + "cd" * 8 + "-01"
    r = c.get("/health/live", headers={"traceparent": parent})
    assert r.headers["traceparent"].startswith("00-" + "ab" * 16)  # mesmo trace_id
    spans = exp.get_finished_spans()
    assert spans and spans[-1].name == "GET /health/live"
    assert format(spans[-1].context.trace_id, "032x") == "ab" * 16
    attrs = dict(spans[-1].attributes)
    assert set(attrs) <= {"http.request.method", "http.route", "http.response.status_code"}


# ------------------------------------------------------------------ CRUD editorial
def test_item_lifecycle_and_immutability(client):
    c, _ = client
    r = c.post("/v1/items", json={"instrument_id": "math6", "code": "X01", "content": CONTENT}, headers=AUTH)
    assert r.status_code == 201
    vid = r.json()["version_id"]
    assert c.post("/v1/items", json={"instrument_id": "math6", "code": "X01", "content": CONTENT},
                  headers=AUTH).status_code == 409  # código duplicado
    e = c.patch(f"/v1/item-versions/{vid}", json={"content": {**CONTENT, "stem": "Quanto é 6 × 7?"},
                                                   "expected_row_version": 1}, headers=AUTH)
    assert e.status_code == 200
    assert c.patch(f"/v1/item-versions/{vid}", json={"content": CONTENT, "expected_row_version": 1},
                   headers=AUTH).status_code == 409  # edição concorrente
    assert c.post(f"/v1/item-versions/{vid}/submit", headers=AUTH).status_code == 200
    assert c.post(f"/v1/item-versions/{vid}/approve", json={"rationale": "cedo demais"}, headers=PSI).status_code == 409
    for j in JUDGES:
        assert c.post(f"/v1/item-versions/{vid}/reviews", json={"ratings": RATINGS, "comment": "ok"},
                      headers=j).status_code == 201
    assert c.post(f"/v1/item-versions/{vid}/reviews", json={"ratings": RATINGS}, headers=JUDGES[0]).status_code == 409
    assert c.post(f"/v1/item-versions/{vid}/reviews", json={"ratings": {"relevancia": 9}},
                  headers=H("demo-token-juiz-3")).status_code in (409, 422)
    assert c.post(f"/v1/item-versions/{vid}/approve", json={"rationale": "três pareceres favoráveis"},
                  headers=PSI).json()["status"] == "approved"
    f = c.post("/v1/forms", json={"instrument_id": "math6", "label": "F1", "version_ids": [vid]}, headers=PSI)
    assert f.status_code == 201
    v = c.get(f"/v1/item-versions/{vid}", headers=PSI).json()
    assert v["locked"] == 1 and len(v["reviews"]) == 3 and all(r["evidence_origin"] == "human_review" for r in v["reviews"])
    assert c.patch(f"/v1/item-versions/{vid}", json={"content": CONTENT, "expected_row_version": v["row_version"]},
                   headers=AUTH).status_code == 409  # travada após uso em caderno
    nv = c.post(f"/v1/item-versions/{vid}/new-version", json={"content": {**CONTENT, "stem": "Quanto é 8 × 6?"}},
                headers=AUTH).json()
    assert nv["version"] == 2 and nv["parent_version_id"] == vid
    assert "key" not in c.get(f"/v1/item-versions/{vid}", headers=COORD).json()["content"]  # gabarito oculto
    assert c.post("/v1/items", json={"instrument_id": "math6", "code": "X02", "content": CONTENT, "role": "admin"},
                  headers=AUTH).status_code == 422


def test_author_cannot_judge_own_item(client):
    c, _ = client
    vid = c.post("/v1/items", json={"instrument_id": "math6", "code": "X03", "content": CONTENT},
                 headers=PSI).json()["version_id"]
    c.post(f"/v1/item-versions/{vid}/submit", headers=PSI)
    assert c.post(f"/v1/item-versions/{vid}/reviews", json={"ratings": RATINGS}, headers=AUTH).status_code == 403


# ------------------------------------------------------------------ integrações reais (repositórios locais)
@pytest.mark.skipif(repo_path("themis") is None or repo_path("aegis") is None, reason="repositórios irmãos ausentes")
def test_integrations_status_real(client):
    c, _ = client
    r = c.get("/v1/integrations/status", headers=PSI).json()
    assert r["themis"]["integration_status"] == "verified_local" and len(r["themis"]["commit"]) == 40
    assert r["aegis"]["integration_status"] == "verified_local" and r["aegis"]["probe"]["allowed"] is False
    assert c.get("/v1/integrations/status", headers=COORD).status_code == 403
