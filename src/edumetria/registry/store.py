"""Persistência transacional da PoC (SQLite; PostgreSQL + RLS no roadmap).

Implementa as regras de controle das seções 13, 18, 19 e 24:
- revisão humana persistente (sobrevive a reinício), com ator, versão e motivo;
- aprovação sobre versão antiga → ``Conflict`` (controle otimista);
- isolamento por tenant e escola em TODA consulta (404 para objeto invisível);
- fila de jobs com lease/heartbeat, retentativa só para erro transitório e
  idempotência por (tenant, Idempotency-Key, digest do corpo);
- outbox gravado na mesma transação da mudança de domínio; consumidor
  idempotente via ``processed_events`` (at-least-once + deduplicação);
- trilha de auditoria separada dos logs, com hash-chain (detecta alteração,
  mas não protege contra administrador com controle total do banco).
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
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, tenant TEXT NOT NULL, actor TEXT NOT NULL,
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
"""


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
    role: str  # psychometrician | coordinator | teacher | auditor
    schools: frozenset[str] = field(default_factory=frozenset)  # vazio = todas do tenant (só psicometrista/auditor)

    def can_see_school(self, school_id: str) -> bool:
        if self.role in ("psychometrician", "auditor"):
            return True
        return school_id in self.schools


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def body_digest(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def tx(self):
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------ auditoria
    def _audit(self, c, actor: Actor, action: str, otype: str, oid: str, purpose: str = "", detail: dict | None = None):
        row = c.execute("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "0" * 64
        ts = _now()
        d = json.dumps(detail or {}, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256(f"{prev}|{ts}|{actor.tenant}|{actor.user_id}|{action}|{otype}|{oid}|{d}".encode()).hexdigest()
        c.execute("INSERT INTO audit_events (ts, tenant, actor, action, object_type, object_id, purpose, detail, "
                  "prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (ts, actor.tenant, actor.user_id, action, otype, oid, purpose, d, prev, h))

    def verify_audit_chain(self) -> bool:
        with self._conn() as c:
            prev = "0" * 64
            for r in c.execute("SELECT * FROM audit_events ORDER BY seq"):
                h = hashlib.sha256(f"{prev}|{r['ts']}|{r['tenant']}|{r['actor']}|{r['action']}|"
                                   f"{r['object_type']}|{r['object_id']}|{r['detail']}".encode()).hexdigest()
                if r["prev_hash"] != prev or r["hash"] != h:
                    return False
                prev = h
        return True

    def list_audit(self, actor: Actor, limit: int = 200) -> list[dict]:
        if actor.role not in ("auditor", "psychometrician"):
            raise PermissionDenied("consulta de auditoria restrita")
        with self._conn() as c:
            rows = c.execute("SELECT seq, ts, actor, action, object_type, object_id, purpose FROM audit_events "
                             "WHERE tenant=? ORDER BY seq DESC LIMIT ?", (actor.tenant, limit)).fetchall()
        return [dict(r) for r in rows]

    def _outbox(self, c, tenant: str, etype: str, agg_id: str, agg_ver: int, data: dict, traceparent: str | None):
        eid = str(uuid.uuid4())
        c.execute("INSERT INTO outbox_events VALUES (?,?,?,?,?,?,?,?,?,0)",
                  (eid, etype, "1.0.0", _now(), tenant, agg_id, agg_ver, traceparent,
                   json.dumps(data, ensure_ascii=False)))
        return eid

    # ------------------------------------------------------------ jobs
    def enqueue_job(self, actor: Actor, job_type: str, payload: dict, idem_key: str | None) -> tuple[dict, bool]:
        """Retorna (job, criado). Mesma chave + mesmo corpo → mesmo job;
        mesma chave + corpo diferente → Conflict."""
        if actor.role != "psychometrician":
            raise PermissionDenied("apenas psicometrista enfileira calibrações")
        digest = body_digest(payload)
        with self.tx() as c:
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
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE job_id=? AND tenant=?", (job_id, actor.tenant)).fetchone()
        if not row:
            raise NotFound(job_id)
        return dict(row)

    def claim_job(self, worker_id: str, lease_seconds: int = 120) -> dict | None:
        """Reivindica o próximo job queued, ou running com lease expirado (worker morto)."""
        now = datetime.now(timezone.utc)
        with self.tx() as c:
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
        with self.tx() as c:
            c.execute("UPDATE jobs SET heartbeat_at=?, lease_until=? WHERE job_id=? AND lease_owner=?",
                      (now.isoformat(), (now + timedelta(seconds=lease_seconds)).isoformat(), job_id, worker_id))

    def finish_job(self, job_id: str, worker_id: str, ok: bool, result: dict | None = None,
                   error_code: str | None = None, error_detail: str | None = None, retryable: bool = False) -> None:
        with self.tx() as c:
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

    # ------------------------------------------------------------ calibrações
    def register_calibration(self, tenant: str, instrument_version_id: str, dataset_snapshot_id: str,
                             model_family: str, run_id: str, manifest_hash: str, converged: bool,
                             created_by: str = "worker") -> str:
        cid = f"cal-{uuid.uuid4().hex[:12]}"
        with self.tx() as c:
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
        with self._conn() as c:
            row = c.execute("SELECT * FROM calibrations WHERE calibration_id=? AND tenant=?",
                            (calibration_id, actor.tenant)).fetchone()
        if not row:
            raise NotFound(calibration_id)
        return dict(row)

    def list_calibrations(self, actor: Actor) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM calibrations WHERE tenant=? ORDER BY created_at DESC",
                             (actor.tenant,)).fetchall()
        return [dict(r) for r in rows]

    def release_calibration(self, actor: Actor, calibration_id: str, rationale: str, expected_version: int,
                            traceparent: str | None = None) -> dict:
        if actor.role != "psychometrician":
            raise PermissionDenied("liberação de calibração exige papel de psicometrista")
        with self.tx() as c:
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
        with self.tx() as c:
            c.execute("INSERT INTO support_cases VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
        with self._conn() as c:
            return dict(self._visible_case(c, actor, case_id))

    def list_cases(self, actor: Actor) -> list[dict]:
        with self._conn() as c:
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
        with self.tx() as c:
            row = self._visible_case(c, actor, case_id)
            if actor.role not in ("coordinator", "psychometrician"):
                raise PermissionDenied("sem permissão")
            self._transition(c, actor, row, CaseStatus.UNDER_REVIEW, expected_version, "enviado para revisão")
            return dict(c.execute("SELECT * FROM support_cases WHERE case_id=?", (case_id,)).fetchone())

    def review_case(self, actor: Actor, case_id: str, decision: str, rationale: str, expected_version: int,
                    traceparent: str | None = None) -> dict:
        if actor.role != "coordinator":
            raise PermissionDenied("deliberação de caso exige coordenação escolar")
        with self.tx() as c:
            row = self._visible_case(c, actor, case_id)
            if row["created_by"] == actor.user_id:
                raise PermissionDenied("revisor não pode aprovar o próprio caso (segregação de funções)")
            to = {"approve": CaseStatus.APPROVED, "decline": CaseStatus.DECLINED,
                  "request_changes": CaseStatus.PROPOSED}[decision]
            new_v = self._transition(c, actor, row, to, expected_version, rationale)
            c.execute("INSERT INTO case_reviews VALUES (?,?,?,?,?,?,?,?)",
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
        with self.tx() as c:
            row = self._visible_case(c, actor, case_id)
            self._transition(c, actor, row, CaseStatus(to_status), expected_version, note)
            return dict(c.execute("SELECT * FROM support_cases WHERE case_id=?", (case_id,)).fetchone())

    # ------------------------------------------------------------ outbox / consumidor
    def pending_events(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM outbox_events WHERE published=0 ORDER BY occurred_at LIMIT ?", (limit,))]

    def all_events(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM outbox_events ORDER BY occurred_at")]

    def mark_published(self, event_id: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE outbox_events SET published=1 WHERE event_id=?", (event_id,))

    def consume_followup(self, event: dict, consumer: str = "followup-scheduler") -> bool:
        """Consumidor idempotente: cria acompanhamento para intervenção aprovada.
        Replay do mesmo evento não duplica o efeito. Retorna True se aplicou."""
        if event["event_type"] != "intervention.approved":
            return False
        with self.tx() as c:
            done = c.execute("SELECT 1 FROM processed_events WHERE consumer=? AND event_id=?",
                             (consumer, event["event_id"])).fetchone()
            if done:
                return False
            c.execute("INSERT INTO followups VALUES (?,?,?,?,?,?)",
                      (f"fu-{uuid.uuid4().hex[:10]}", event["tenant"], event["aggregate_id"], event["event_id"],
                       14, _now()))
            c.execute("INSERT INTO processed_events VALUES (?,?,?)", (consumer, event["event_id"], _now()))
            return True

    def count_followups(self, case_id: str) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM followups WHERE case_id=?", (case_id,)).fetchone()[0]
