"""API EduMetria (FastAPI) — casos de uso são a autoridade de escrita (seção 16).

- Identidade: ``Authorization: Bearer <token>`` → Actor. Modo demo (configs/demo_users.yaml) ou
  OIDC (``EDUMETRIA_AUTH_MODE=oidc``: JWT RS256 validado contra JWKS — ver apps/api/auth.py).
- Tracing OpenTelemetry por requisição (apps/api/tracing.py); OTLP se configurado.
  tenant/role/confirmed no corpo são rejeitados pelo contrato (422).
- Cálculo nunca roda dentro da requisição: POST /v1/calibrations → 202 + job.
- Objeto de outra escola/tenant → 404 (não vaza existência).
Rodar: ``uvicorn apps.api.main:app --reload`` (com ``PYTHONPATH=src``).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from edumetria import SCHEMA_VERSION, __version__
from edumetria.domain.contracts import (CalibrationRequest, CaseReview, CaseTransition, ReleaseRequest,
                                        ScoreRecord, SupportCaseCreate)
from edumetria.domain.enums import ReleaseStatus, ScoreStatus
from edumetria.irt import r_engine
from edumetria.observability.telemetry import (METRICS, child_traceparent, get_logger, log_event,
                                               parse_traceparent)
from edumetria.registry.store import Actor, Conflict, NotFound, PermissionDenied, Store
from edumetria.copilot.copilot import Copilot
from edumetria.integrations.verify import status_report

from apps.api.auth import AuthError, authenticate
from apps.api.tracing import build_provider, start_server_span, traceparent_of

ROOT = Path(__file__).resolve().parents[2]
USERS_FILE = ROOT / "configs" / "demo_users.yaml"


def create_app(db_path: str | None = None, runs_root: str | None = None, span_exporter=None) -> FastAPI:
    app = FastAPI(title="EduMetria API", version=__version__,
                  description="PoC autoral — dados sintéticos. Não é produto oficial de nenhuma instituição.")
    store = Store(db_path or os.environ.get("EDUMETRIA_DB", str(ROOT / "runs" / "edumetria.db")))
    logger = get_logger("edumetria.api")
    app.state.store = store
    provider = build_provider(span_exporter)
    tracer = provider.get_tracer("edumetria.api")
    app.state.tracer_provider = provider

    def actor(authorization: str | None = Header(default=None)) -> Actor:
        try:
            return authenticate(authorization)
        except AuthError as exc:
            raise HTTPException(401, str(exc)) from exc

    @app.middleware("http")
    async def telemetry(request: Request, call_next):
        t0 = time.perf_counter()
        with start_server_span(tracer, request.method, request.url.path, request.headers) as span:
            tp = traceparent_of(span)
            request.state.traceparent = tp
            response = await call_next(request)
            route = request.scope.get("route")
            path = getattr(route, "path", "other")
            span.update_name(f"{request.method} {path}")
            span.set_attribute("http.route", path)
            span.set_attribute("http.response.status_code", response.status_code)
        status_class = f"{response.status_code // 100}xx"
        METRICS.inc("edumetria_http_requests_total", route=path, method=request.method, status_class=status_class)
        METRICS.observe("edumetria_http_request_duration_seconds", time.perf_counter() - t0, route=path,
                        method=request.method)
        response.headers["traceparent"] = tp
        log_event(logger, "http.request", route=path, method=request.method, status=response.status_code,
                  trace_id=parse_traceparent(tp)[0], duration_ms=round((time.perf_counter() - t0) * 1000, 1))
        return response

    @app.exception_handler(NotFound)
    async def _nf(_, exc):
        return JSONResponse({"error": "not_found"}, status_code=404)

    @app.exception_handler(PermissionDenied)
    async def _pd(_, exc):
        return JSONResponse({"error": "forbidden", "detail": str(exc)}, status_code=403)

    @app.exception_handler(Conflict)
    async def _cf(_, exc):
        return JSONResponse({"error": "conflict", "detail": str(exc)}, status_code=409)

    # ------------------------------------------------------------ saúde
    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        store.list_calibrations(Actor("health", "health", "psychometrician"))
        return {"status": "ready", "db": "ok", "schema_version": SCHEMA_VERSION,
                "r_engine": "available" if r_engine.rscript_path() else "unavailable (engine python-native ativo)",
                "llm": "disabled (feature flag desligada — ADR-009)"}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics():
        return METRICS.render()

    # ------------------------------------------------------------ calibração
    @app.post("/v1/calibrations", status_code=202)
    def enqueue(req: CalibrationRequest, response: Response, a: Actor = Depends(actor),
                idempotency_key: str | None = Header(default=None)):
        job, created = store.enqueue_job(a, "calibration", req.model_dump(), idempotency_key)
        if not created:
            response.status_code = 200
        return {"job_id": job["job_id"], "status": job["status"], "created": created}

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str, a: Actor = Depends(actor)):
        j = store.get_job(a, job_id)
        return {k: j[k] for k in ("job_id", "status", "attempts", "error_code", "created_at", "updated_at")} | {
            "result": json.loads(j["result"]) if j["result"] else None}

    @app.get("/v1/calibrations")
    def list_cal(a: Actor = Depends(actor)):
        return store.list_calibrations(a)

    @app.get("/v1/calibrations/{cid}")
    def get_cal(cid: str, a: Actor = Depends(actor)):
        return store.get_calibration(a, cid)

    def _run_dir(cal: dict) -> Path:
        root = Path(runs_root or os.environ.get("EDUMETRIA_RUNS", str(ROOT / "runs")))
        p = (root / cal["run_id"]).resolve()
        if root.resolve() not in p.parents or not p.exists():
            raise HTTPException(503, "artefatos do run indisponíveis")
        return p

    @app.get("/v1/calibrations/{cid}/diagnostics")
    def diagnostics(cid: str, a: Actor = Depends(actor)):
        cal = store.get_calibration(a, cid)
        d = json.loads((_run_dir(cal) / "fit_diagnostics.json").read_text(encoding="utf-8"))
        return {"calibration_id": cid, "status": cal["status"], "diagnostics": d}

    @app.post("/v1/calibrations/{cid}/release")
    def release(cid: str, req: ReleaseRequest, request: Request, a: Actor = Depends(actor)):
        return store.release_calibration(a, cid, req.rationale, req.expected_version,
                                         traceparent=request.state.traceparent)

    @app.get("/v1/evidence-reports/{cid}")
    def evidence(cid: str, a: Actor = Depends(actor)):
        cal = store.get_calibration(a, cid)
        return json.loads((_run_dir(cal) / "evidence_report.json").read_text(encoding="utf-8"))

    @app.post("/v1/scores")
    def scores(body: dict, request: Request, a: Actor = Depends(actor)):
        allowed = {"calibration_id", "subject_refs"}
        if set(body) - allowed:
            raise HTTPException(422, f"campos não permitidos: {sorted(set(body) - allowed)}")
        cal = store.get_calibration(a, str(body.get("calibration_id")))
        if cal["status"] != ReleaseStatus.RELEASED.value:
            raise HTTPException(409, "pontuação exige calibração liberada por revisão humana")
        if a.role not in ("psychometrician", "coordinator", "teacher"):
            raise HTTPException(403, "sem permissão")
        refs = list(body.get("subject_refs") or [])[:200]
        sc = pd.read_csv(_run_dir(cal) / "restricted" / "scores.csv").set_index("subject_ref")
        trace_id = parse_traceparent(request.state.traceparent)[0]
        out = []
        for ref in refs:
            if ref not in sc.index or not a.can_see_school(str(sc.loc[ref, "school_id"])):
                out.append({"subject_ref": ref, "status": "not_found"})  # invisível ≡ inexistente
                continue
            r = sc.loc[ref]
            ok = r["status_math"] == "computed"
            out.append(ScoreRecord(
                score_id=f"{cid_short(cal)}-{ref}", subject_ref=ref,
                instrument_version_id=cal["instrument_version_id"], calibration_id=cal["calibration_id"],
                scale_id="math6-internal-v1",
                estimate=float(r["theta_math"]) if ok else None,
                posterior_sd=float(r["psd_math"]) if ok else None,
                interval_90=(float(r["q05_math"]), float(r["q95_math"])) if ok else None,
                n_items_answered=int(r["n_answered_math"]), status=ScoreStatus(r["status_math"]),
                warnings=[] if ok else ["sem respostas informativas — θ não reportado"],
                trace_id=trace_id).model_dump())
        return out

    # ------------------------------------------------------------ casos de apoio
    @app.post("/v1/support-cases", status_code=201)
    def create_case(req: SupportCaseCreate, a: Actor = Depends(actor)):
        return store.create_case(a, req.school_id, req.subject_ref, req.reason, req.evidence_refs)

    @app.get("/v1/support-cases")
    def list_cases(a: Actor = Depends(actor)):
        return store.list_cases(a)

    @app.get("/v1/support-cases/{case_id}")
    def get_case(case_id: str, a: Actor = Depends(actor)):
        return store.get_case(a, case_id)

    @app.post("/v1/support-cases/{case_id}/submit")
    def submit_case(case_id: str, body: dict, a: Actor = Depends(actor)):
        return store.submit_case(a, case_id, int(body.get("expected_version", 0)))

    @app.post("/v1/support-cases/{case_id}/reviews")
    def review_case(case_id: str, req: CaseReview, request: Request, a: Actor = Depends(actor)):
        return store.review_case(a, case_id, req.decision, req.rationale, req.expected_version,
                                 traceparent=request.state.traceparent)

    @app.post("/v1/support-cases/{case_id}/transition")
    def transition(case_id: str, req: CaseTransition, a: Actor = Depends(actor)):
        return store.transition_case(a, case_id, req.to_status, req.note, req.expected_version)

    # ------------------------------------------------------------ CRUD editorial
    @app.post("/v1/items", status_code=201)
    def create_item(body: dict, a: Actor = Depends(actor)):
        _only(body, {"instrument_id", "code", "content"})
        return store.create_item(a, str(body["instrument_id"]), str(body["code"]), dict(body["content"]))

    @app.get("/v1/item-versions/{vid}")
    def get_version(vid: str, a: Actor = Depends(actor)):
        v = store.get_item_version(a, vid)
        if a.role not in ("psychometrician", "author", "judge"):
            v["content"].pop("key", None)  # gabarito só para perfis editoriais
        return v

    @app.patch("/v1/item-versions/{vid}")
    def edit_version(vid: str, body: dict, a: Actor = Depends(actor)):
        _only(body, {"content", "expected_row_version"})
        return store.update_item_version(a, vid, dict(body["content"]), int(body["expected_row_version"]))

    @app.post("/v1/item-versions/{vid}/new-version", status_code=201)
    def new_version(vid: str, body: dict, a: Actor = Depends(actor)):
        _only(body, {"content"})
        return store.new_item_version(a, vid, dict(body["content"]))

    @app.post("/v1/item-versions/{vid}/submit")
    def submit_version(vid: str, a: Actor = Depends(actor)):
        return store.submit_item_version(a, vid)

    @app.post("/v1/item-versions/{vid}/reviews", status_code=201)
    def review_version(vid: str, body: dict, a: Actor = Depends(actor)):
        _only(body, {"ratings", "comment"})
        try:
            return store.review_item_version(a, vid, dict(body["ratings"]), str(body.get("comment", ""))[:2000])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/v1/item-versions/{vid}/approve")
    def approve_version(vid: str, body: dict, a: Actor = Depends(actor)):
        _only(body, {"rationale"})
        return store.approve_item_version(a, vid, str(body["rationale"]))

    @app.post("/v1/forms", status_code=201)
    def create_form(body: dict, a: Actor = Depends(actor)):
        _only(body, {"instrument_id", "label", "version_ids"})
        try:
            return store.create_form(a, str(body["instrument_id"]), str(body["label"]), list(body["version_ids"]))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    # ------------------------------------------------------------ copiloto e integrações
    @app.post("/v1/copilot/ask")
    def copilot_ask(body: dict, a: Actor = Depends(actor)):
        _only(body, {"calibration_id", "question"})
        cal = store.get_calibration(a, str(body.get("calibration_id")))
        ans = Copilot(_run_dir(cal)).ask(str(body.get("question", ""))[:1000], a)
        return {"status": ans.status, "answer": ans.text, "tool": ans.tool, "citations": ans.citations,
                "llm": "disabled" if not os.environ.get("EDUMETRIA_COPILOT_LLM") else "local-optional"}

    @app.get("/v1/integrations/status")
    def integrations(a: Actor = Depends(actor)):
        if a.role not in ("psychometrician", "auditor"):
            raise HTTPException(403, "restrito")
        return status_report()

    @app.get("/v1/audit")
    def audit(a: Actor = Depends(actor)):
        return {"chain_valid": store.verify_audit_chain(), "events": store.list_audit(a)}

    return app


def _only(body: dict, allowed: set[str]) -> None:
    """Corpo com campos fora do contrato → 422 (inclui tenant/role/confirmed)."""
    extra = set(body) - allowed
    if extra:
        raise HTTPException(422, f"campos não permitidos: {sorted(extra)}")
    missing = {k for k in allowed if k not in body and k != "comment"}
    if missing:
        raise HTTPException(422, f"campos obrigatórios ausentes: {sorted(missing)}")


def cid_short(cal: dict) -> str:
    return cal["calibration_id"].replace("cal-", "s")


app = create_app()
