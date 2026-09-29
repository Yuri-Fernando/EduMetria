# ROADMAP — EduMetria

Documento mestre de escopo. Tudo que está no plano mestre (`docs/plano/`) aparece aqui —
nada foi descartado, apenas sequenciado. "Não feito" ≠ "fora do projeto".

Legenda: ✅ implementado e testado · 🟡 parcial · ⏳ planejado · 🧪 depende de parceria/piloto real

## P0 — demonstração técnica principal (v0.1.0) ✅

Matriz, itens e versões · fluxo de juízes (sintético) · gerador · TCT · 2PL/GRM + 1PL · EAP com incerteza ·
DIF com revisão · registro de calibração com liberação manual · API · painel · auditoria · telemetria · testes.

## P1 — PoC completa de produto (v0.2.0)

| Item | Estado | Onde |
|---|---|---|
| CFA ordinal no pipeline | ✅ | `r/cfa_ordinal.R`, `pipeline._structure_block` |
| Estudo de invariância | ✅ configural → limiares → cargas | `r/invariance.R` |
| Previsão com validação temporal e espacial | ✅ | `risk/` |
| Revisão humana persistente e acompanhamento | ✅ | `registry/store.py` |
| Adapters Themis / Argus / Aegis | ✅ `verified_local` (código real, commit registrado) | `integrations/verify.py` |
| Copiloto restrito | ✅ determinístico; LLM local opcional | `copilot/` |
| PostgreSQL + RLS | ✅ | `registry/store.py`, `infra/postgres/` |
| Migrations versionadas (Alembic) | ⏳ | hoje: DDL idempotente no `Store` |
| Autenticação OIDC | ✅ emissor local; IdP institucional = configuração | `apps/api/auth.py` |
| Perfil de observabilidade | ✅ Collector + Jaeger + Prometheus + Grafana | `compose.yaml`, `observability/` |
| CRUD editorial via API | ✅ | `/v1/items`, `/v1/item-versions/*`, `/v1/forms` |
| Cenário S6 | ✅ | `configs/scenarios/s6_multidim.yaml` |
| 3PL e GPCM como comparadores | ✅ via R | `r/fit_irt.R` |
| Relatório PDF | ✅ | `reporting/pdf.py` |

## P2 — após a PoC (v0.3.0 no que não depende de parceria)

| Item | Estado |
|---|---|
| Trilha B — dados públicos reais | ✅ ENEM 2023 (parâmetros e notas oficiais); Saeb ⏳ |
| Equalização longitudinal e linking com erro | ✅ simulação; ⏳ com itens comuns reais entre edições do ENEM |
| Teste adaptativo | ✅ simulação; ⏳ controle de exposição Sympson-Hetter |
| Multinível, testlet, bifator | ✅ |
| Desenho de estudo de impacto (MDES, poder, pré-registro) | ✅ |
| Piloto com escolas | 🧪 |
| Juízes reais, entrevistas cognitivas | 🧪 |
| Execução do estudo de impacto | 🧪 |
| Validação externa em outras redes | 🧪 |
