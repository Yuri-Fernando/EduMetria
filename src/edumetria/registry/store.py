"""Persistência transacional: SQLite (padrão, zero dependência) ou PostgreSQL + RLS.

Implementa as regras de controle das seções 13, 18, 19 e 24:
- revisão humana persistente (sobrevive a reinício), com ator, versão e motivo;
- aprovação sobre versão antiga → ``Conflict`` (controle otimista);
- isolamento por tenant e escola em TODA consulta (404 para objeto invisível);
- **PostgreSQL:** isolamento também no banco — Row Level Security por
  ``current_setting('app.tenant')``, definido por transação (``SET LOCAL``), e a
  aplicação conecta com papel SEM ``BYPASSRLS`` e sem ser dona das tabelas;
- fila de jobs com lease/heartbeat, retentativa só para erro transitório e
  idempotência por (tenant, Idempotency-Key, digest do corpo);
- outbox gravado na mesma transação da mudança de domínio; consumidor
  idempotente via ``processed_events`` (at-least-once + deduplicação);
- trilha de auditoria separada dos logs, com hash-chain por tenant (detecta
  alteração, mas não protege contra administrador com controle total);
- CRUD editorial: item → versões; versão usada em caderno fica travada
  (imutável); edição de item travado exige nova versão.

Backend: ``Store("caminho.db")`` → SQLite; ``Store("postgresql://...")`` → PostgreSQL.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from edumetria.domain.contracts import CASE_TRANSITIONS
from edumetria.domain.enums import CaseStatus, JobStatus, ReleaseStatus

TENANT_TABLES = ["calibrations", "jobs", "support_cases", "case_reviews", "audit_events", "outbox_events",
                 "followups", "items", "item_versions", "item_reviews", "forms", "form_items"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS calibrations (
    calibration_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, instrument_version_id TEXT NOT NULL,
    dataset_snapshot_id TEXT NOT NULL, model_family TEXT NOT NULL, run_id TEXT NOT NULL,
    manifest_hash TEXT NOT NULL, converged INTEGER NOT NULL, status TEXT NOT NULL,
    version INTEGER NOT NULL, created_at TEXT NOT NULL, released_by TEXT, released_at TEXT, rationale TEXT);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, idem_key TEXT, body_digest TEXT NOT NULL,
    job_type TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3, lease_owner TEXT, lease_until TEXT, heartbeat_at TEXT,
    error_code TEXT, error_detail TEXT, result TEXT, created_by TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (tenant, idem_key));
CREATE TABLE IF NOT EXISTS support_cases (
    case_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, school_id TEXT NOT NULL, subject_ref TEXT NOT NULL,
    reason TEXT NOT NULL, evidence_refs TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS case_reviews (
    review_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, tenant TEXT NOT NULL, reviewer TEXT NOT NULL,
    decision TEXT NOT NULL, rationale TEXT NOT NULL, case_version INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
    seq {SERIAL} PRIMARY KEY, ts TEXT NOT NULL, tenant TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL, purpose TEXT,
    detail TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, schema_version TEXT NOT NULL,
    occurred_at TEXT NOT NULL, tenant TEXT NOT NULL, aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL, traceparent TEXT, data TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS processed_events (
    consumer TEXT NOT NULL, event_id TEXT NOT NULL, processed_at TEXT NOT NULL, PRIMARY KEY (consumer, event_id));
CREATE TABLE IF NOT EXISTS followups (
    followup_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, case_id TEXT NOT NULL, source_event_id TEXT NOT NULL,
    due_in_days INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, instrument_id TEXT NOT NULL, code TEXT NOT NULL,
    created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (tenant, instrument_id, code));
CREATE TABLE IF NOT EXISTS item_versions (
    version_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, item_id TEXT NOT NULL, version INTEGER NOT NULL,
    content TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0,
    row_version INTEGER NOT NULL DEFAULT 1, parent_version_id TEXT, created_by TEXT NOT NULL,
    created_at TEXT NOT NULL, UNIQUE (item_id, version));
CREATE TABLE IF NOT EXISTS item_reviews (
    review_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, version_id TEXT NOT NULL, judge TEXT NOT NULL,
    ratings TEXT NOT NULL, comment TEXT, evidence_origin TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE (version_id, judge));
CREATE TABLE IF NOT EXISTS forms (
    form_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, instrument_id TEXT NOT NULL, label TEXT NOT NULL,
    content_hash TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS form_items (
    form_id TEXT NOT NULL, tenant TEXT NOT NULL, version_id TEXT NOT NULL, position INTEGER NOT NULL,
    PRIMARY KEY (form_id, position));
"""

MIN_REVIEWS_TO_APPROVE = 3
RATING_CRITERIA = ("relevancia", "clareza", "alinhamento", "adequacao_etaria", "acessibilidade")


class NotFound(LookupError):
    pass


class PermissionDenied(PermissionError):
    pass


class Conflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Actor:
    """Identidade derivada da autenticação — nunca do corpo da requisição."""

    user_id: str
    tenant: str
    role: str  # psychometrician | coordinator | teacher | auditor | author | judge | system
    schools: frozenset[str] = field(default_factory=frozenset)  # vazio = todas do tenant (só psicometrista/auditor)

    def can_see_school(self, school_id: str) -> bool:
        if self.role in ("psychometrician", "auditor", "system"):
            return True
        return school_id in self.schools


SYSTEM = Actor("system", "*", "system")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def body_digest(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- dialetos
class _PgCursorAdapter:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())


class _PgConn:
    """Adapta psycopg2 à interface usada pelo Store (placeholders ``?``, linhas como dict)."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, params: tuple = ()):
        from psycopg2.extras import RealDictCursor
        cur = self.raw.cursor(cursor_factory=RealDictCursor)
        # sem parâmetros → None: o psycopg2 só interpreta "%" quando há parâmetros (ex.: LIKE 'x-%')
        cur.execute(sql.replace("?", "%s"), params or None)
        return _PgCursorAdapter(cur)


class Store:
    def __init__(self, path_or_dsn: str | Path, admin_dsn: str | None = None):
        self.dsn = str(path_or_dsn)
        self.is_pg = self.dsn.startswith(("postgresql://", "postgres://"))
        if self.is_pg:
            self._migrate_pg(admin_dsn or self.dsn)
        else:
            self.path = self.dsn
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with self._sqlite() as c:
                c.executescript(SCHEMA.replace("{SERIAL}", "INTEGER") .replace(
                    "seq INTEGER PRIMARY KEY", "seq INTEGER PRIMARY KEY AUTOINCREMENT"))

    # ------------------------------------------------------------ conexões
    @contextmanager
    def _sqlite(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def _migrate_pg(self, admin_dsn: str) -> None:
        import psycopg2
        conn = psycopg2.connect(admin_dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(SCHEMA.replace("{SERIAL}", "BIGSERIAL"))
                for t in TENANT_TABLES:
                    cur.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
                    cur.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
                    cur.execute(
                        f"CREATE POLICY tenant_isolation ON {t} USING ("
                        "tenant = current_setting('app.tenant', true) OR current_setting('app.role', true) = 'system'"
                        ") WITH CHECK ("
                        "tenant = current_setting('app.tenant', true) OR current_setting('app.role', true) = 'system')")
                cur.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edumetria_app') THEN "
                            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO edumetria_app; "
                            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO edumetria_app; END IF; END $$;")
        finally:
            conn.close()

    @contextmanager
    def session(self, tenant: str | None = None, write: bool = False):
        """Transação com contexto de tenant (usado pelo RLS no PostgreSQL)."""
        if self.is_pg:
            import psycopg2
            raw = psycopg2.connect(self.dsn)
            try:
                c = _PgConn(raw)
                c.execute("SELECT set_config('app.tenant', ?, true), set_config('app.role', ?, true)",
                          ("" if tenant in (None, "*") else tenant, "system" if tenant == "*" else "app"))
                yield c
                raw.commit()
            except Exception:
                raw.rollback()
                raise
            finally:
                raw.close()
        else:
            with self._sqlite() as c:
                if write:
                    c.execute("BEGIN IMMEDIATE")
                    try:
                        yield c
                        c.execute("COMMIT")
                    except Exception:
                        c.execute("ROLLBACK")
                        raise
                else:
                    yield c

    def tx(self, tenant: str | None = "*"):
        return self.session(tenant, write=True)

    def raw_query(self, sql: str, tenant: str | None) -> list[dict]:
        """Consulta crua SEM filtro de tenant na aplicação — usada para provar o RLS."""
        with self.session(tenant) as c:
            return [dict(r) for r in c.execute(sql).fetchall()]

    # ------------------------------------------------------------ auditoria
    def _audit(self, c, actor: Actor, action: str, otype: str, oid: str, purpose: str = "", detail: dict | None = None,
               tenant: str | None = None):
        tenant = tenant or actor.tenant
        row = c.execute("SELECT hash FROM audit_events WHERE tenant=? ORDER BY seq DESC LIMIT 1", (tenant,)).fetchone()
        prev = row["hash"] if row else "0" * 64
        ts = _now()
        d = json.dumps(detail or {}, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(f"{prev}|{ts}|{tenant}|{actor.user_id}|{action}|{otype}|{oid}|{d}".encode()).hexdigest()
        c.execute("INSERT INTO audit_events (ts, tenant, actor, action, object_type, object_id, purpose, detail, "
                  "prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (ts, tenant, actor.user_id, action, otype, oid, purpose, d, prev, h))

    def verify_audit_chain(self, tenant: str | None = None) -> bool:
        with self.session("*") as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM audit_events ORDER BY seq").fetchall()]
        by_tenant: dict[str, list[dict]] = {}
        for r in rows:
            if tenant is None or r["tenant"] == tenant:
                by_tenant.setdefault(r["tenant"], []).append(r)
        for t, rs in by_tenant.items():
            prev = "0" * 64
            for r in rs:
                h = hashlib.sha256(f"{prev}|{r['ts']}|{r['tenant']}|{r['actor']}|{r['action']}|"
                                   f"{r['object_type']}|{r['object_id']}|{r['detail']}".encode()).hexdigest()
                if r["prev_hash"] != prev or r["hash"] != h:
                    return False
                prev = h
        return True

    def list_audit(self, actor: Actor, limit: int = 200) -> list[dict]:
        if actor.role not in ("auditor", "psychometrician"):
            raise PermissionDenied("consulta de auditoria restrita")
        with self.session(actor.tenant) as c:
            rows = c.execute("SELECT seq, ts, actor, action, object_type, object_id, purpose FROM audit_events "
                             "WHERE tenant=? ORDER BY seq DESC LIMIT ?", (actor.tenant, limit)).fetchall()
        return [dict(r) for r in rows]

    def _outbox(self, c, tenant: str, etype: str, agg_id: str, agg_ver: int, data: dict, traceparent: str | None):
        eid = str(uuid.uuid4())
        c.execute("INSERT INTO outbox_events (event_id, event_type, schema_version, occurred_at, tenant, aggregate_id, "
                  "aggregate_version, traceparent, data, published) VALUES (?,?,?,?,?,?,?,?,?,0)",
                  (eid, etype, "1.0.0", _now(), tenant, agg_id, agg_ver, traceparent,
                   json.dumps(data, ensure_ascii=False)))
        return eid

    # ------------------------------------------------------------ jobs
    def enqueue_job(self, actor: Actor, job_type: str, payload: dict, idem_key: str | None) -> tuple[dict, bool]:
        """Mesma chave + mesmo corpo → mesmo job; mesma chave + corpo diferente → Conflict."""
        if actor.role != "psychometrician":
            raise PermissionDenied("apenas psicometrista enfileira calibrações")
        digest = body_digest(payload)
        with self.tx(actor.tenant) as c:
            if idem_key:
                row = c.execute("SELECT * FROM jobs WHERE tenant=? AND idem_key=?", (actor.tenant, idem_key)).fetchone()
                if row:
                    if row["body_digest"] != digest:
                        raise Conflict("Idempotency-Key reutilizada com corpo diferente")
                    return dict(row), False
            jid = f"job-{uuid.uuid4().hex[:12]}"
            now = _now()
            c.execute("INSERT INTO jobs (job_id, tenant, idem_key, body_digest, job_type, payload, status, "
                      "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (jid, actor.tenant, idem_key, digest, job_type, json.dumps(payload), JobStatus.QUEUED.value,
                       actor.user_id, now, now))
            self._audit(c, actor, "job.enqueued", "job", jid, "calibration", {"job_type": job_type})
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (jid,)).fetchone()
        return dict(row), True

    def get_job(self, actor: Actor, job_id: str) -> dict:
        with self.session(actor.tenant) as c:
            row = c.execute("SELECT * FROM jobs WHERE job_id=? AND tenant=?", (job_id, actor.tenant)).fetchone()
        if not row:
            raise NotFound(job_id)
        return dict(row)

    def claim_job(self, worker_id: str, lease_seconds: int = 120) -> dict | None:
        """Reivindica o próximo job queued, ou running com lease expirado (worker morto)."""
        now = datetime.now(timezone.utc)
        with self.tx("*") as c:
            row = c.execute(
                "SELECT * FROM jobs WHERE (status=? OR (status=? AND lease_until < ?)) AND attempts < max_attempts "
                "ORDER BY created_at LIMIT 1",
                (JobStatus.QUEUED.value, JobStatus.RUNNING.value, now.isoformat())).fetchone()
            if not row:
                return None
            c.execute("UPDATE jobs SET status=?, lease_owner=?, lease_until=?, heartbeat_at=?, attempts=attempts+1, "
                      "updated_at=? WHERE job_id=?",
                      (JobStatus.RUNNING.value, worker_id, (now + timedelta(seconds=lease_seconds)).isoformat(),
                       now.isoformat(), now.isoformat(), row["job_id"]))
            return dict(c.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone())

    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: int = 120) -> None:
        now = datetime.now(timezone.utc)
        with self.tx("*") as c:
            c.execute("UPDATE jobs SET heartbeat_at=?, lease_until=? WHERE job_id=? AND lease_owner=?",
                      (now.isoformat(), (now + timedelta(seconds=lease_seconds)).isoformat(), job_id, worker_id))

    def expire_lease(self, job_id: str) -> None:
        """Ferramenta de teste/operação: simula worker morto."""
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self.tx("*") as c:
            c.execute("UPDATE jobs SET lease_until=? WHERE job_id=?", (past, job_id))

    def finish_job(self, job_id: str, worker_id: str, ok: bool, result: dict | None = None,
                   error_code: str | None = None, error_detail: str | None = None, retryable: bool = False) -> None:
        with self.tx("*") as c:
            row = c.execute("SELECT attempts, max_attempts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if ok:
                status = JobStatus.SUCCEEDED.value
            elif retryable and row["attempts"] < row["max_attempts"]:
                status = JobStatus.QUEUED.value
            else:
                status = JobStatus.FAILED.value
            c.execute("UPDATE jobs SET status=?, result=?, error_code=?, error_detail=?, lease_owner=NULL, "
                      "lease_until=NULL, updated_at=? WHERE job_id=? AND lease_owner=?",
                      (status, json.dumps(result) if result else None, error_code, error_detail, _now(),
                       job_id, worker_id))

    def job_stats(self) -> dict:
        """Contagem de jobs por status e duração média (fim − criação) dos concluídos com sucesso.
        Lida do banco para que métricas de jobs executados por OUTRO processo (worker) apareçam no /metrics."""
        with self.session("*") as c:
            rows = [dict(r) for r in c.execute("SELECT job_type, status, created_at, updated_at FROM jobs").fetchall()]
        counts: dict[tuple[str, str], int] = {}
        durs = []
        for r in rows:
            counts[(r["job_type"], r["status"])] = counts.get((r["job_type"], r["status"]), 0) + 1
            if r["status"] == JobStatus.SUCCEEDED.value:
                durs.append((datetime.fromisoformat(r["updated_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds())
        return {"counts": counts, "mean_duration_seconds": (sum(durs) / len(durs)) if durs else None,
                "n_succeeded": len(durs)}

    # ------------------------------------------------------------ calibrações
    def register_calibration(self, tenant: str, instrument_version_id: str, dataset_snapshot_id: str,
                             model_family: str, run_id: str, manifest_hash: str, converged: bool,
                             created_by: str = "worker") -> str:
        cid = f"cal-{uuid.uuid4().hex[:12]}"
        with self.tx(tenant) as c:
            c.execute("INSERT INTO calibrations (calibration_id, tenant, instrument_version_id, dataset_snapshot_id, "
                      "model_family, run_id, manifest_hash, converged, status, version, created_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (cid, tenant, instrument_version_id, dataset_snapshot_id, model_family, run_id, manifest_hash,
                       int(converged), ReleaseStatus.CANDIDATE.value, 1, _now()))
            self._audit(c, Actor(created_by, tenant, "system"), "calibration.candidate_created", "calibration", cid,
                        "calibration", {"run_id": run_id, "converged": converged})
            self._outbox(c, tenant, "calibration.completed", cid, 1, {"run_id": run_id}, None)
        return cid

    def get_calibration(self, actor: Actor, calibration_id: str) -> dict:
        with self.session(actor.tenant) as c:
            row = c.execute("SELECT * FROM calibrations WHERE calibration_id=? AND tenant=?",
                            (calibration_id, actor.tenant)).fetchone()
        if not row:
            raise NotFound(calibration_id)
        return dict(row)

    def list_calibrations(self, actor: Actor) -> list[dict]:
        with self.session(actor.tenant) as c:
            rows = c.execute("SELECT * FROM calibrations WHERE tenant=? ORDER BY created_at DESC",
                             (actor.tenant,)).fetchall()
        return [dict(r) for r in rows]

    def release_calibration(self, actor: Actor, calibration_id: str, rationale: str, expected_version: int,
                            traceparent: str | None = None) -> dict:
        if actor.role != "psychometrician":
            raise PermissionDenied("liberação de calibração exige papel de psicometrista")
        with self.tx(actor.tenant) as c:
            row = c.execute("SELECT * FROM calibrations WHERE calibration_id=? AND tenant=?",
                            (calibration_id, actor.tenant)).fetchone()
            if not row:
                raise NotFound(calibration_id)
            if row["version"] != expected_version:
                raise Conflict(f"versão esperada {expected_version}, atual {row['version']}")
            if row["status"] != ReleaseStatus.CANDIDATE.value:
                raise Conflict(f"calibração em estado {row['status']} não pode ser liberada")
            if not row["converged"]:
                raise Conflict("calibração não convergiu — publicação bloqueada (alerta A3)")
            new_v = row["version"] + 1
            c.execute("UPDATE calibrations SET status=?, version=?, released_by=?, released_at=?, rationale=? "
                      "WHERE calibration_id=?",
                      (ReleaseStatus.RELEASED.value, new_v, actor.user_id, _now(), rationale, calibration_id))
            self._audit(c, actor, "calibration.released", "calibration", calibration_id, "publication",
                        {"rationale": rationale, "version": new_v})
            self._outbox(c, actor.tenant, "calibration.released", calibration_id, new_v,
                         {"instrument_version_id": row["instrument_version_id"]}, traceparent)
            return dict(c.execute("SELECT * FROM calibrations WHERE calibration_id=?", (calibration_id,)).fetchone())

    # ------------------------------------------------------------ casos de apoio
    def create_case(self, actor: Actor, school_id: str, subject_ref: str, reason: str,
                    evidence_refs: list[str]) -> dict:
        if actor.role not in ("coordinator", "psychometrician"):
            raise PermissionDenied("criação de caso restrita a profissionais autorizados")
        if not actor.can_see_school(school_id):
            raise PermissionDenied("escola fora do escopo do usuário")
        cid = f"case-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.tx(actor.tenant) as c:
            c.execute("INSERT INTO support_cases (case_id, tenant, school_id, subject_ref, reason, evidence_refs, "
                      "status, version, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (cid, actor.tenant, school_id, subject_ref, reason, json.dumps(evidence_refs),
                       CaseStatus.PROPOSED.value, 1, actor.user_id, now, now))
            self._audit(c, actor, "case.created", "support_case", cid, "student_support")
            self._outbox(c, actor.tenant, "intervention.proposed", cid, 1, {"school_id": school_id}, None)
            return dict(c.execute("SELECT * FROM support_cases WHERE case_id=?", (cid,)).fetchone())

    def _visible_case(self, c, actor: Actor, case_id: str):
        row = c.execute("SELECT * FROM support_cases WHERE case_id=? AND tenant=?", (case_id, actor.tenant)).fetchone()
        if not row or not actor.can_see_school(row["school_id"]):
            raise NotFound(case_id)  # invisível ≡ inexistente (não vaza existência)
        return row

    def get_case(self, actor: Actor, case_id: str) -> dict:
        with self.session(actor.tenant) as c:
            return dict(self._visible_case(c, actor, case_id))

    def list_cases(self, actor: Actor) -> list[dict]:
        with self.session(actor.tenant) as c:
            rows = c.execute("SELECT * FROM support_cases WHERE tenant=? ORDER BY created_at", (actor.tenant,)).fetchall()
        return [dict(r) for r in rows if actor.can_see_school(r["school_id"])]

    def _transition(self, c, actor: Actor, row, to: CaseStatus, expected_version: int, note: str):
        if row["version"] != expected_version:
            raise Conflict(f"versão esperada {expected_version}, atual {row['version']} — revisar estado atual")
        cur = CaseStatus(row["status"])
        if to not in CASE_TRANSITIONS[cur]:
            raise Conflict(f"transição {cur.value} → {to.value} não permitida")
        new_v = row["version"] + 1
        c.execute("UPDATE support_cases SET status=?, version=?, updated_at=? WHERE case_id=?",
                  (to.value, new_v, _now(), row["case_id"]))
        self._audit(c, actor, f"case.{to.value}", "support_case", row["case_id"], "student_support", {"note": note})
        return new_v

    def submit_case(self, actor: Actor, case_id: str, expected_version: int) -> dict:
        with self.tx(actor.tenant) as c:
            row = self._visible_case(c, actor, case_id)
            if actor.role not in ("coordinator", "psychometrician"):
                raise PermissionDenied("sem permissão")
            self._transition(c, actor, row, CaseStatus.UNDER_REVIEW, expected_version, "enviado para revisão")
            return dict(c.execute("SELECT * FROM support_cases WHERE case_id=?", (case_id,)).fetchone())

    def review_case(self, actor: Actor, case_id: str, decision: str, rationale: str, expected_version: int,
                    traceparent: str | None = None) -> dict:
        if actor.role != "coordinator":
            raise PermissionDenied("deliberação de caso exige coordenação escolar")
        with self.tx(actor.tenant) as c:
            row = self._visible_case(c, actor, case_id)
            if row["created_by"] == actor.user_id:
                raise PermissionDenied("revisor não pode aprovar o próprio caso (segregação de funções)")
            to = {"approve": CaseStatus.APPROVED, "decline": CaseStatus.DECLINED,
                  "request_changes": CaseStatus.PROPOSED}[decision]
            new_v = self._transition(c, actor, row, to, expected_version, rationale)
            c.execute("INSERT INTO case_reviews (review_id, case_id, tenant, reviewer, decision, rationale, "
                      "case_version, created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (f"rev-{uuid.uuid4().hex[:10]}", case_id, actor.tenant, actor.user_id, decision, rationale,
                       expected_version, _now()))
            if to == CaseStatus.APPROVED:
                self._outbox(c, actor.tenant, "intervention.approved", case_id, new_v,
                             {"school_id": row["school_id"]}, traceparent)
            return dict(c.execute("SELECT * FROM support_cases WHERE case_id=?", (case_id,)).fetchone())

    def transition_case(self, actor: Actor, case_id: str, to_status: str, note: str, expected_version: int) -> dict:
        """Execução/conclusão só depois de aprovação persistida (máquina de estados)."""
        if actor.role != "coordinator":
            raise PermissionDenied("sem permissão")
        with self.tx(actor.tenant) as c:
            row = self._visible_case(c, actor, case_id)
            self._transition(c, actor, row, CaseStatus(to_status), expected_version, note)
            return dict(c.execute("SELECT * FROM support_cases WHERE case_id=?", (case_id,)).fetchone())

    # ------------------------------------------------------------ outbox / consumidor
    def pending_events(self, limit: int = 100) -> list[dict]:
        with self.session("*") as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM outbox_events WHERE published=0 ORDER BY occurred_at LIMIT ?", (limit,)).fetchall()]

    def all_events(self) -> list[dict]:
        with self.session("*") as c:
            return [dict(r) for r in c.execute("SELECT * FROM outbox_events ORDER BY occurred_at").fetchall()]

    def mark_published(self, event_id: str) -> None:
        with self.tx("*") as c:
            c.execute("UPDATE outbox_events SET published=1 WHERE event_id=?", (event_id,))

    def consume_followup(self, event: dict, consumer: str = "followup-scheduler") -> bool:
        """Consumidor idempotente: replay do mesmo evento não duplica o efeito."""
        if event["event_type"] != "intervention.approved":
            return False
        with self.tx("*") as c:
            done = c.execute("SELECT 1 AS x FROM processed_events WHERE consumer=? AND event_id=?",
                             (consumer, event["event_id"])).fetchone()
            if done:
                return False
            c.execute("INSERT INTO followups (followup_id, tenant, case_id, source_event_id, due_in_days, created_at) "
                      "VALUES (?,?,?,?,?,?)",
                      (f"fu-{uuid.uuid4().hex[:10]}", event["tenant"], event["aggregate_id"], event["event_id"],
                       14, _now()))
            c.execute("INSERT INTO processed_events (consumer, event_id, processed_at) VALUES (?,?,?)",
                      (consumer, event["event_id"], _now()))
            return True

    def count_followups(self, case_id: str) -> int:
        with self.session("*") as c:
            return int(c.execute("SELECT COUNT(*) AS n FROM followups WHERE case_id=?", (case_id,)).fetchone()["n"])

    # ------------------------------------------------------------ CRUD editorial
    @staticmethod
    def _content_hash(content: dict) -> str:
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def create_item(self, actor: Actor, instrument_id: str, code: str, content: dict) -> dict:
        if actor.role not in ("author", "psychometrician"):
            raise PermissionDenied("criação de item restrita a autores")
        iid, vid, now = f"item-{uuid.uuid4().hex[:10]}", f"iv-{uuid.uuid4().hex[:10]}", _now()
        with self.tx(actor.tenant) as c:
            if c.execute("SELECT 1 AS x FROM items WHERE tenant=? AND instrument_id=? AND code=?",
                         (actor.tenant, instrument_id, code)).fetchone():
                raise Conflict(f"código {code} já existe no instrumento {instrument_id}")
            c.execute("INSERT INTO items (item_id, tenant, instrument_id, code, created_by, created_at) "
                      "VALUES (?,?,?,?,?,?)", (iid, actor.tenant, instrument_id, code, actor.user_id, now))
            c.execute("INSERT INTO item_versions (version_id, tenant, item_id, version, content, content_hash, status, "
                      "created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                      (vid, actor.tenant, iid, 1, json.dumps(content, ensure_ascii=False), self._content_hash(content),
                       "draft", actor.user_id, now))
            self._audit(c, actor, "item.created", "item", iid, "item_bank", {"version_id": vid})
        return {"item_id": iid, "version_id": vid, "version": 1, "status": "draft"}

    def _version(self, c, actor: Actor, version_id: str):
        row = c.execute("SELECT * FROM item_versions WHERE version_id=? AND tenant=?", (version_id, actor.tenant)).fetchone()
        if not row:
            raise NotFound(version_id)
        return row

    def get_item_version(self, actor: Actor, version_id: str) -> dict:
        with self.session(actor.tenant) as c:
            r = dict(self._version(c, actor, version_id))
            r["reviews"] = [dict(x) for x in c.execute(
                "SELECT judge, ratings, comment, evidence_origin, created_at FROM item_reviews WHERE version_id=?",
                (version_id,)).fetchall()]
        r["content"] = json.loads(r["content"])
        return r

    def update_item_version(self, actor: Actor, version_id: str, content: dict, expected_row_version: int) -> dict:
        if actor.role not in ("author", "psychometrician"):
            raise PermissionDenied("edição restrita a autores")
        with self.tx(actor.tenant) as c:
            row = self._version(c, actor, version_id)
            if row["locked"]:
                raise Conflict("versão já usada em caderno aplicado é imutável — crie nova versão")
            if row["status"] != "draft":
                raise Conflict(f"só rascunho é editável (estado atual: {row['status']})")
            if row["row_version"] != expected_row_version:
                raise Conflict("edição concorrente — recarregue a versão")
            c.execute("UPDATE item_versions SET content=?, content_hash=?, row_version=row_version+1 WHERE version_id=?",
                      (json.dumps(content, ensure_ascii=False), self._content_hash(content), version_id))
            self._audit(c, actor, "item_version.edited", "item_version", version_id, "item_bank")
        return self.get_item_version(actor, version_id)

    def new_item_version(self, actor: Actor, version_id: str, content: dict) -> dict:
        if actor.role not in ("author", "psychometrician"):
            raise PermissionDenied("restrito a autores")
        with self.tx(actor.tenant) as c:
            base = self._version(c, actor, version_id)
            last = c.execute("SELECT MAX(version) AS v FROM item_versions WHERE item_id=?", (base["item_id"],)).fetchone()["v"]
            vid = f"iv-{uuid.uuid4().hex[:10]}"
            c.execute("INSERT INTO item_versions (version_id, tenant, item_id, version, content, content_hash, status, "
                      "parent_version_id, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (vid, actor.tenant, base["item_id"], last + 1, json.dumps(content, ensure_ascii=False),
                       self._content_hash(content), "draft", version_id, actor.user_id, _now()))
            self._audit(c, actor, "item_version.created", "item_version", vid, "item_bank", {"parent": version_id})
        return {"version_id": vid, "version": last + 1, "status": "draft", "parent_version_id": version_id}

    def submit_item_version(self, actor: Actor, version_id: str) -> dict:
        with self.tx(actor.tenant) as c:
            row = self._version(c, actor, version_id)
            if row["status"] != "draft":
                raise Conflict("só rascunho pode ir para revisão")
            c.execute("UPDATE item_versions SET status='in_review', row_version=row_version+1 WHERE version_id=?",
                      (version_id,))
            self._audit(c, actor, "item_version.submitted", "item_version", version_id, "item_bank")
        return self.get_item_version(actor, version_id)

    def review_item_version(self, actor: Actor, version_id: str, ratings: dict, comment: str) -> dict:
        if actor.role != "judge":
            raise PermissionDenied("parecer restrito a juízes")
        if set(ratings) != set(RATING_CRITERIA) or not all(isinstance(v, int) and 1 <= v <= 4 for v in ratings.values()):
            raise ValueError(f"ratings deve ter {RATING_CRITERIA} com notas inteiras 1–4")
        with self.tx(actor.tenant) as c:
            row = self._version(c, actor, version_id)
            if row["status"] != "in_review":
                raise Conflict("versão não está em revisão")
            if row["created_by"] == actor.user_id:
                raise PermissionDenied("autor não emite parecer sobre o próprio item")
            if c.execute("SELECT 1 AS x FROM item_reviews WHERE version_id=? AND judge=?",
                         (version_id, actor.user_id)).fetchone():
                raise Conflict("juiz já emitiu parecer para esta versão")
            c.execute("INSERT INTO item_reviews (review_id, tenant, version_id, judge, ratings, comment, evidence_origin, "
                      "created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (f"ir-{uuid.uuid4().hex[:10]}", actor.tenant, version_id, actor.user_id, json.dumps(ratings),
                       comment, "human_review", _now()))
            self._audit(c, actor, "item_version.reviewed", "item_version", version_id, "content_validity")
        return self.get_item_version(actor, version_id)

    def approve_item_version(self, actor: Actor, version_id: str, rationale: str) -> dict:
        if actor.role != "psychometrician":
            raise PermissionDenied("aprovação editorial exige psicometrista")
        with self.tx(actor.tenant) as c:
            row = self._version(c, actor, version_id)
            if row["status"] != "in_review":
                raise Conflict("versão não está em revisão")
            n = c.execute("SELECT COUNT(*) AS n FROM item_reviews WHERE version_id=?", (version_id,)).fetchone()["n"]
            if n < MIN_REVIEWS_TO_APPROVE:
                raise Conflict(f"aprovação exige ≥ {MIN_REVIEWS_TO_APPROVE} pareceres independentes (há {n})")
            c.execute("UPDATE item_versions SET status='approved', row_version=row_version+1 WHERE version_id=?",
                      (version_id,))
            self._audit(c, actor, "item_version.approved", "item_version", version_id, "item_bank",
                        {"rationale": rationale, "n_reviews": n})
        return self.get_item_version(actor, version_id)

    def create_form(self, actor: Actor, instrument_id: str, label: str, version_ids: list[str]) -> dict:
        """Monta caderno com versões aprovadas e as TRAVA (imutáveis a partir daqui)."""
        if actor.role != "psychometrician":
            raise PermissionDenied("montagem de caderno exige psicometrista")
        if len(set(version_ids)) != len(version_ids) or not version_ids:
            raise ValueError("lista de versões vazia ou com repetição")
        fid = f"form-{uuid.uuid4().hex[:10]}"
        with self.tx(actor.tenant) as c:
            hashes = []
            for v in version_ids:
                row = self._version(c, actor, v)
                if row["status"] != "approved":
                    raise Conflict(f"{v} não está aprovada")
                hashes.append(row["content_hash"])
            content_hash = hashlib.sha256("|".join(hashes).encode()).hexdigest()
            c.execute("INSERT INTO forms (form_id, tenant, instrument_id, label, content_hash, created_by, created_at) "
                      "VALUES (?,?,?,?,?,?,?)", (fid, actor.tenant, instrument_id, label, content_hash, actor.user_id, _now()))
            for pos, v in enumerate(version_ids, start=1):
                c.execute("INSERT INTO form_items (form_id, tenant, version_id, position) VALUES (?,?,?,?)",
                          (fid, actor.tenant, v, pos))
                c.execute("UPDATE item_versions SET locked=1 WHERE version_id=?", (v,))
            self._audit(c, actor, "form.created", "form", fid, "item_bank", {"n_items": len(version_ids)})
        return {"form_id": fid, "content_hash": content_hash, "n_items": len(version_ids)}
