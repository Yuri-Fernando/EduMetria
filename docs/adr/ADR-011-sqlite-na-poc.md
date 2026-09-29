# ADR-011 — SQLite transacional na PoC; PostgreSQL + RLS no piloto

**Status:** aceito (2026-09-28). O plano previa PostgreSQL. Para rodar em checkout limpo sem Docker, a PoC usa SQLite com transações `BEGIN IMMEDIATE`, isolamento por tenant/escola na camada de repositório, outbox na mesma transação e auditoria com hash-chain. **Limite conhecido:** sem RLS no banco e sem concorrência multi-processo robusta. Migração para PostgreSQL + RLS + Alembic está no ROADMAP (P1).
