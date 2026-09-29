# ADR-003 — Aplicação modular com worker separado antes de microsserviços

**Status:** aceito. Uma API FastAPI + um worker de jobs (lease/heartbeat/idempotência) sobre um banco transacional. Kafka, Kubernetes e microsserviços numerosos não são necessários para 2.000 estudantes sintéticos.
