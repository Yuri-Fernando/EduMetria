"""T18, T20–T23 — isolamento, conflito de versão, persistência, outbox, replay."""

import os
import sqlite3

import pytest

from edumetria.registry.store import TENANT_TABLES, Actor, Conflict, NotFound, PermissionDenied, Store

PG_ADMIN = os.environ.get("EDUMETRIA_PG_ADMIN_DSN", "postgresql://edumetria_admin:admin_local_only@localhost:15432/edumetria")
PG_APP = os.environ.get("EDUMETRIA_PG_DSN", "postgresql://edumetria_app:app_local_only@localhost:15432/edumetria")


def _pg_up() -> bool:
    try:
        import psycopg2
        psycopg2.connect(PG_ADMIN, connect_timeout=2).close()
        return True
    except Exception:
        return False


PG_UP = _pg_up()


def test_postgres_required_when_flagged():
    """Na CI (EDUMETRIA_REQUIRE_PG=1), ausência do PostgreSQL é falha — não skip silencioso."""
    if os.environ.get("EDUMETRIA_REQUIRE_PG") == "1":
        assert PG_UP, "EDUMETRIA_REQUIRE_PG=1 mas o PostgreSQL não respondeu"
BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(not PG_UP, reason="PostgreSQL local indisponível"))]


def _pg_reset():
    import psycopg2
    conn = psycopg2.connect(PG_ADMIN)
    with conn, conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(TENANT_TABLES + ["processed_events"]) + " RESTART IDENTITY")
    conn.close()


def _tamper(store, sql):
    if store.is_pg:
        import psycopg2
        conn = psycopg2.connect(PG_ADMIN)
        with conn, conn.cursor() as cur:
            cur.execute(sql)
        conn.close()
    else:
        with sqlite3.connect(store.path) as c:
            c.execute(sql)

PSI = Actor("psi-ana", "t1", "psychometrician")
COORD_A = Actor("coord-a", "t1", "coordinator", frozenset({"SCH01"}))
COORD_A2 = Actor("coord-a2", "t1", "coordinator", frozenset({"SCH01"}))
COORD_B = Actor("coord-b", "t1", "coordinator", frozenset({"SCH05"}))
OTHER_TENANT = Actor("psi-x", "t2", "psychometrician")


@pytest.fixture(params=BACKENDS)
def store(request, tmp_path):
    if request.param == "postgres":
        st = Store(PG_APP, admin_dsn=PG_ADMIN)
        _pg_reset()
        return st
    return Store(tmp_path / "db.sqlite")


def _case(store):
    return store.create_case(COORD_A, "SCH01", "synthetic-student-00001", "faltas recentes em alta", ["run-x"])


def test_t18_school_isolation(store):
    c = _case(store)
    with pytest.raises(NotFound):
        store.get_case(COORD_B, c["case_id"])  # escola B não vê caso da escola A
    with pytest.raises(NotFound):
        store.get_case(OTHER_TENANT, c["case_id"])
    assert store.list_cases(COORD_B) == []
    store.submit_case(COORD_A, c["case_id"], 1)
    with pytest.raises(NotFound):
        store.review_case(COORD_B, c["case_id"], "approve", "tentativa de aprovar fora do escopo", 2)
    with pytest.raises(PermissionDenied):
        store.create_case(COORD_B, "SCH01", "s1", "fora do escopo", [])


def test_segregation_of_duties_and_state_machine(store):
    c = _case(store)
    with pytest.raises(Conflict):  # não pode executar sem aprovação persistida
        store.transition_case(COORD_A2, c["case_id"], "in_progress", "iniciar", 1)
    c = store.submit_case(COORD_A, c["case_id"], 1)
    with pytest.raises(PermissionDenied):  # autor não aprova o próprio caso
        store.review_case(COORD_A, c["case_id"], "approve", "aprovando o meu próprio caso", c["version"])
    c = store.review_case(COORD_A2, c["case_id"], "approve", "plano coerente com a evidência", c["version"])
    assert c["status"] == "approved"
    c = store.transition_case(COORD_A2, c["case_id"], "in_progress", "conversa agendada", c["version"])
    c = store.transition_case(COORD_A2, c["case_id"], "completed", "concluído; resultado a acompanhar", c["version"])
    assert c["status"] == "completed"


def test_t20_approval_on_stale_version_conflicts(store):
    c = store.submit_case(COORD_A, _case(store)["case_id"], 1)
    with pytest.raises(Conflict):
        store.review_case(COORD_A2, c["case_id"], "approve", "aprovação baseada em versão antiga", 1)
    cid = store.register_calibration("t1", "math6-v0.1", "synthetic-s0", "2pl", "run-1", "h", True)
    store.release_calibration(PSI, cid, "diagnósticos revisados e aceitos", 1)
    with pytest.raises(Conflict):
        store.release_calibration(PSI, cid, "segunda liberação indevida", 1)


def test_nonconverged_calibration_cannot_be_released(store):
    cid = store.register_calibration("t1", "math6-v0.1", "synthetic-s0", "2pl", "run-2", "h", False)
    with pytest.raises(Conflict, match="não convergiu"):
        store.release_calibration(PSI, cid, "tentando publicar sem convergência", 1)
    with pytest.raises(PermissionDenied):
        store.release_calibration(COORD_A, cid, "papel sem autoridade", 1)


def test_t21_restart_preserves_reviews(tmp_path):
    s1 = Store(tmp_path / "db.sqlite")
    c = s1.submit_case(COORD_A, _case(s1)["case_id"], 1)
    s1.review_case(COORD_A2, c["case_id"], "approve", "aprovado antes do reinício", c["version"])
    del s1
    s2 = Store(tmp_path / "db.sqlite")  # "reinício" do processo
    assert s2.get_case(COORD_A, c["case_id"])["status"] == "approved"
    assert s2.verify_audit_chain()


def test_t22_outbox_atomic_with_domain_change(store, monkeypatch):
    c = store.submit_case(COORD_A, _case(store)["case_id"], 1)
    before = len(store.all_events())

    def boom(*a, **k):
        raise RuntimeError("crash antes do commit")

    monkeypatch.setattr(store, "_outbox", boom)
    with pytest.raises(RuntimeError):
        store.review_case(COORD_A2, c["case_id"], "approve", "aprovação que vai falhar", c["version"])
    monkeypatch.undo()
    assert store.get_case(COORD_A, c["case_id"])["status"] == "under_review"  # rollback do domínio
    assert len(store.all_events()) == before  # e do outbox
    store.review_case(COORD_A2, c["case_id"], "approve", "aprovação que confirma", c["version"])
    assert any(e["event_type"] == "intervention.approved" for e in store.all_events())


def test_t23_replay_does_not_duplicate_followup(store):
    c = store.submit_case(COORD_A, _case(store)["case_id"], 1)
    store.review_case(COORD_A2, c["case_id"], "approve", "aprovado para acompanhamento", c["version"])
    ev = next(e for e in store.all_events() if e["event_type"] == "intervention.approved")
    assert store.consume_followup(ev) is True
    assert store.consume_followup(ev) is False  # replay
    assert store.count_followups(c["case_id"]) == 1


def test_idempotency_key_semantics(store):
    body = {"instrument_version_id": "math6-v0.1", "model_family": "2pl"}
    j1, created1 = store.enqueue_job(PSI, "calibration", body, "key-1")
    j2, created2 = store.enqueue_job(PSI, "calibration", body, "key-1")
    assert created1 and not created2 and j1["job_id"] == j2["job_id"]
    with pytest.raises(Conflict):
        store.enqueue_job(PSI, "calibration", {**body, "model_family": "grm"}, "key-1")
    with pytest.raises(PermissionDenied):
        store.enqueue_job(COORD_A, "calibration", body, "key-2")


def test_expired_lease_is_reclaimed(store):
    j, _ = store.enqueue_job(PSI, "calibration", {"x": 1}, None)
    claimed = store.claim_job("w1")
    assert claimed["job_id"] == j["job_id"] and store.claim_job("w2") is None
    store.expire_lease(j["job_id"])
    again = store.claim_job("w2")  # worker 1 "morreu"
    assert again["job_id"] == j["job_id"] and again["attempts"] == 2


def test_audit_chain_detects_tampering(store):
    _case(store)
    assert store.verify_audit_chain()
    _tamper(store, "UPDATE audit_events SET actor='intruso' WHERE seq=1")
    assert store.verify_audit_chain() is False


@pytest.mark.skipif(not PG_UP, reason="PostgreSQL local indisponível")
def test_postgres_rls_blocks_cross_tenant_even_without_where():
    """Prova de RLS: a aplicação (papel sem BYPASSRLS) faz SELECT sem filtro de tenant."""
    st = Store(PG_APP, admin_dsn=PG_ADMIN)
    _pg_reset()
    st.create_case(COORD_A, "SCH01", "s-1", "caso do tenant t1", [])
    st.create_case(Actor("coord-z", "t2", "coordinator", frozenset({"SCH09"})), "SCH09", "s-2", "caso do tenant t2", [])
    rows_t1 = st.raw_query("SELECT tenant, subject_ref FROM support_cases", tenant="t1")
    rows_t2 = st.raw_query("SELECT tenant, subject_ref FROM support_cases", tenant="t2")
    rows_none = st.raw_query("SELECT tenant FROM support_cases", tenant=None)
    assert {r["tenant"] for r in rows_t1} == {"t1"} and len(rows_t1) == 1
    assert {r["tenant"] for r in rows_t2} == {"t2"} and len(rows_t2) == 1
    assert rows_none == []  # sem contexto de tenant, nada é visível
    import psycopg2
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):  # WITH CHECK impede gravar em outro tenant
        with st.session("t1", write=True) as c:
            c.execute("INSERT INTO followups (followup_id, tenant, case_id, source_event_id, due_in_days, created_at) "
                      "VALUES ('x','t2','c','e',1,'now')")


@pytest.mark.skipif(not PG_UP, reason="PostgreSQL local indisponível")
def test_postgres_app_role_has_no_bypassrls():
    import psycopg2
    conn = psycopg2.connect(PG_APP)
    with conn.cursor() as cur:
        cur.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cur.fetchone() == (False, False)
    conn.close()


@pytest.mark.skipif(not PG_UP, reason="PostgreSQL local indisponível")
def test_postgres_query_with_literal_percent():
    st = Store(PG_APP, admin_dsn=PG_ADMIN)
    _pg_reset()
    st.create_case(COORD_A, "SCH01", "s-9", "caso com LIKE", [])
    assert len(st.raw_query("SELECT case_id FROM support_cases WHERE case_id LIKE 'case-%'", tenant="t1")) == 1
