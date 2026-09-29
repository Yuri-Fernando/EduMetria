# ADR-001 — Núcleo EduMetria independente, integração por contratos

**Status:** aceito (2026-09-28)

**Contexto.** Medição educacional tem entidades próprias (construto, matriz, item, versão, parecer, calibração, escala, evidência) ausentes dos modelos comerciais do ecossistema (Argus, RetentIQ, Churn_intelligence).

**Decisão.** Repositório próprio com núcleo psicométrico independente e ciclo de releases próprio. Argus, ThemisAI e AegisLLM são integrados por adapters pequenos (`src/edumetria/integrations/`), sempre com estado declarado (`unverified`/`disabled`).

**Consequências.** Sem acoplamento ao vocabulário comercial; integração real exige teste ponta a ponta antes de ser marcada como verificada.
