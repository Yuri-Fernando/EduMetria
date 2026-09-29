# ADR-012 — PostgreSQL com Row Level Security como segunda barreira de isolamento

**Status:** aceito (2026-09-29) — substitui a limitação registrada no ADR-011.

**Decisão.** O `Store` aceita SQLite (padrão, zero dependência) ou PostgreSQL (`postgresql://...`). No PostgreSQL:
- toda tabela com `tenant` tem política `tenant_isolation` (`USING` e `WITH CHECK`) baseada em `current_setting('app.tenant')`,
  definido por transação com `set_config(..., true)`;
- a aplicação conecta como `edumetria_app` (sem superuser, sem `BYPASSRLS`, não é dona das tabelas);
- operações de sistema (worker, outbox) usam `app.role = 'system'`.

**Evidência.** `tests/integration/test_store.py`: a mesma suíte roda nos dois backends; `SELECT` sem filtro de tenant só retorna o
tenant da sessão; `INSERT` em outro tenant falha com `InsufficientPrivilege`; o papel não tem `BYPASSRLS`. Na CI o PostgreSQL é
obrigatório (`EDUMETRIA_REQUIRE_PG=1`).

**Consequências.** A auditoria passou a ter hash-chain **por tenant** (compatível com RLS). Migrations versionadas (Alembic) seguem no ROADMAP.
