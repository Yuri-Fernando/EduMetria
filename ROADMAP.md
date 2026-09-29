# ROADMAP — EduMetria

Documento mestre de escopo. Tudo que está no plano mestre (`docs/plano/`) aparece aqui —
nada foi descartado, apenas sequenciado. "Não feito" ≠ "fora do projeto".

Legenda: ✅ implementado e testado · 🟡 parcial · ⏳ planejado · 🧪 depende de piloto real

## P0 — demonstração técnica principal (v0.1.0)

| Item | Estado | Onde |
|---|---|---|
| Matriz, itens e versões | ✅ (arquivo versionado; CRUD via API ⏳) | `configs/item_bank.yaml` |
| Fluxo de juízes com registros sintéticos | ✅ | `validity/content.py` |
| Gerador reprodutível (respostas + frequência) | ✅ | `simulation/generator.py` |
| TCT | ✅ | `ctt/analysis.py` |
| TRI 2PL e GRM + comparador 1PL | ✅ (paridade mirt) | `irt/` |
| Escores com incerteza, gráficos, exportação, manifesto | ✅ | `irt/scoring.py`, `reporting/` |
| DIF com âncoras conhecidas e estado de revisão | ✅ | `dif/analysis.py` |
| Registro de calibração e liberação manual | ✅ | `registry/store.py` |
| API, painel, auditoria, telemetria, testes | ✅ | `apps/`, `observability/` |

## P1 — PoC completa de produto

| Item | Estado | Observação |
|---|---|---|
| CFA ordinal (lavaan WLSMV) no pipeline | 🟡 | script `r/cfa_ordinal.R` pronto; falta integrar e testar |
| Estudo de invariância planejado | ⏳ | documento de desenho |
| Previsão com validação temporal e espacial | ✅ | `risk/` |
| Revisão humana persistente e acompanhamento | ✅ | casos + follow-up via outbox |
| Adapter Themis / Argus | 🟡 | payloads gerados; integração real não testada (`unverified`) |
| Copiloto restrito via Aegis | ⏳ | feature flag desligada; tools e dataset de avaliação a construir |
| PostgreSQL + RLS + Alembic | ⏳ | ADR-011 |
| Autenticação real (OIDC) | ⏳ | hoje: tokens demo fixos |
| Perfil `observability` (OTel collector, Prometheus, Grafana) | ⏳ | hoje: `/metrics` + logs JSON |
| Compose com perfis core/observability/integrations | ⏳ | |
| CRUD de itens/versões/pareceres via API | ⏳ | |
| Cenário S6 (multidimensionalidade) | ⏳ | |
| 3PL e GPCM como comparadores | ⏳ | só com amostra/justificativa |
| Relatório PDF | ⏳ | HTML já gerado |

## P2 — após a PoC

| Item | Estado |
|---|---|
| Piloto com escolas e dados legitimamente disponibilizados | 🧪 |
| Juízes reais, entrevistas cognitivas | 🧪 |
| Trilha B — microdados públicos do Saeb (após checar dicionário/licença) | ⏳ |
| Equalização longitudinal e linking com erro | ⏳ |
| Teste adaptativo (só com banco calibrado suficiente) | ⏳ |
| Modelos multinível, testlet, bifator | ⏳ |
| Estudos de impacto de intervenções (desenho por clusters) | 🧪 |
| Validação externa em outras redes | 🧪 |
