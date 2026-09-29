# CHANGELOG

Este é o **documento mestre de histórico** do EduMetria. Segue o formato
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e [SemVer](https://semver.org/lang/pt-BR/).

Ver também: [ROADMAP.md](ROADMAP.md) (escopo/fases), [WORKLOG.md](WORKLOG.md) (log por sessão),
`docs/adr/` (decisões) e `docs/plano/` (plano mestre, versão pública v1.1).

## [Unreleased]

Nada ainda.

## [0.3.0] — 2026-09-29 — P2: dados reais, linking, CAT, modelos alternativos, impacto e notebook

### Added
- **Trilha B — dados públicos reais:** `scripts/trilha_b_enem.py` lê os microdados do ENEM 2023 (Inep) direto do zip, calibra
  2PL (nativo) e 3PL (mirt) num caderno de Matemática e compara com parâmetros e notas oficiais (`reports/trilha_b_enem/`).
- **Linking longitudinal** (`irt/linking.py`, `simulation/waves.py`): mean-mean, mean-sigma, Stocking-Lord, Haebara, erro de
  linking por bootstrap e sinalização de âncora instável.
- **CAT** (`irt/cat.py`): máxima informação + randomesque, EAP, parada por precisão; comparação com forma fixa.
- **Modelos alternativos via R:** bifator/testlet (`r/bifactor.R`), comparadores 3PL e GPCM (`r/fit_irt.R`).
- **Cenário S6** (multidimensionalidade) no gerador.
- **Multinível** (`risk/multilevel.py`): ICC por REML com checagem ANOVA, efeitos EB encolhidos.
- **Desenho de impacto** (`impact/design.py`): MDES para ensaio por escolas, escolas necessárias, poder por simulação;
  `docs/impact/preregistro_template.md`.
- `scripts/p2_studies.py` + `reports/p2/`; **notebook end-to-end executado** (`notebooks/edumetria_end_to_end.ipynb`,
  gerado por `scripts/build_notebook.py`).
- ADR-015 (trilha B), `docs/methodology/p2_estudos.md`.

### Fixed
- ICC: o otimizador `lbfgs` do statsmodels ficava preso na fronteira τ² = 0 (ICC verdadeiro 0,15 → estimado 0,0); agora
  `bfgs`/`powell` + checagem ANOVA (verificado com ICC conhecido).
- Pipeline: quando o GRM falha (categoria vazia), o bloco de risco quebrava com `KeyError`; agora o B2 usa só os escores
  disponíveis e registra isso (`b2_psycho_features`) — teste de regressão incluído.
- PostgreSQL: consultas com `%` literal (`LIKE 'x-%'`) quebravam no psycopg2 com tupla vazia de parâmetros.
- Script R do bifator perdia os nomes (`jsonlite` + vetor nomeado).

## [0.2.0] — 2026-09-29 — P1: plataforma, governança e integrações verificadas

### Added
- **CFA ordinal e invariância** (lavaan WLSMV: configural → limiares → cargas) integradas ao pipeline;
  seção `structure_invariance` no relatório de evidências (**SCHEMA_VERSION 1.1.0**, campo opcional — compatível).
- **PostgreSQL + Row Level Security** no `Store` (mesmo código para SQLite); papel da aplicação sem `BYPASSRLS`
  (`infra/postgres/init.sql`); auditoria hash-chain por tenant. ADR-012.
- **OIDC** (`apps/api/auth.py`): JWT RS256 + JWKS, emissor local `scripts/dev_oidc.py`. ADR-013.
- **OpenTelemetry** (`apps/api/tracing.py`) + `compose.yaml` com perfis `core` e `observability`
  (Collector, Jaeger, Prometheus com regras de alerta, Grafana com dashboard RED provisionado).
- **CRUD editorial** via API: item → versões → pareceres humanos (≥3, autor não julga) → aprovação → caderno com versões travadas.
- **Copiloto restrito** (`copilot/`): ferramentas em allowlist, guarda local + AegisLLM + Themis, citação obrigatória,
  abstenção, LLM local opcional com verificação numérica; dataset de avaliação `configs/copilot_eval.yaml`. ADR-014.
- **Integrações verificadas** (`integrations/verify.py`): chamadas reais ao policy engine e prompt security do ThemisAI, aos
  guardrails do AegisLLM e ao validador de contratos do Argus, com commit registrado (`/v1/integrations/status`).
- **Relatório PDF** (`reporting/pdf.py`) com fonte Unicode (θ, α, −).
- `EDUMETRIA_LOG_LEVEL` para o console (o `run.log` segue completo).
- CI com serviço PostgreSQL e `EDUMETRIA_REQUIRE_PG=1` (sem skip silencioso).

### Changed
- README: seção de contexto reescrita para descrever o **estudo** (pergunta de pesquisa, população simulada, o que se verifica) — sem referência a processo seletivo.
- Plano mestre publicado como `docs/plano/POC_EduMetria_Plano_Mestre_v1.1.txt` (versão pública, sem seções de edital/aderência); a v1.0 original fica só local (ignorada pelo Git).

### Fixed (CI)
- CI: o job de paridade com R ficava verde com os 3 testes **pulados** (`mirt` não instalava no R 4.4 do runner por falta de `Deriv`). Agora usa `r-version: release`, instala `Deriv`, verifica o `mirt` explicitamente e `EDUMETRIA_REQUIRE_R=1` transforma a ausência de R em falha.

## [0.1.0] — 2026-09-28 — P0: núcleo psicométrico, evidências e fluxo controlado

### Added

- **Simulação (trilha A)** — `src/edumetria/simulation/generator.py`: 2 municípios fictícios, 20 escolas,
  2.000 estudantes artificiais, 24 itens 2PL + 12 itens GRM, 60 dias letivos de frequência, pareceres de
  juízes simulados, grupo de auditoria A/B artificial. Cenários S0, S1, S2, S3, S4, S5, S7, S8, S9, S10, S11
  em `configs/scenarios/` (S6 ficou no roadmap).
- **Banco de itens autorais** — `configs/item_bank.yaml`: 24 itens de matemática (blueprint 10/8/6 × 8/10/6,
  conferido por código) e 12 de pertencimento; códigos BNCC `null` até verificação.
- **Qualidade de dados** — validação de schema, versão desconhecida (bloqueia o lote), categoria inválida,
  duplicata, atraso, tentativa extra; quarentena com motivo; snapshot por hash SHA-256.
- **TCT** — p, omissão, r ponto-bisserial corrigida, distratores, α com IC bootstrap, estados explícitos.
- **TRI nativa** — 2PL/1PL e GRM por MML-EM (Bock–Aitkin), SE por produto cruzado, EAP com posterior_sd e
  intervalo por quantis, MLE só para demonstrar divergência, Q3, observado × esperado, triagem dimensional.
- **Worker R de referência** — `r/fit_irt.R`, `r/dif.R`, `r/cfa_ordinal.R` + adapter com allowlist
  (`src/edumetria/irt/r_engine.py`). Paridade verificada com mirt 1.47 / R 4.6.1.
- **DIF** — Mantel-Haenszel (ETS A/B/C), regressão logística uniforme/não uniforme, BH, âncoras conhecidas
  (simulação) e "todos os outros itens", `insufficient_evidence` para grupos pequenos, revisão humana.
- **Validade de conteúdo** — I-CVI, S-CVI/Ave, Aiken V com IC; origem simulada nunca conta como humana.
- **Risco preditivo** — snapshots point-in-time com bloqueio de vazamento, alvo censurado, B0–B3, split
  temporal + escolas externas, bootstrap por escola, calibração, equidade preditiva com supressão de célula.
- **Registry/persistência (SQLite)** — calibrações candidate → released (liberação manual, bloqueio sem
  convergência), jobs com lease/heartbeat/idempotência, casos de apoio com máquina de estados, segregação de
  funções, outbox transacional, consumidor idempotente, auditoria com hash-chain.
- **API FastAPI** (`apps/api/main.py`) e **worker** (`src/edumetria/worker.py`).
- **Dashboard Streamlit** (`apps/dashboard/app.py`) com 8 abas e estados de erro/bloqueio.
- **Relatórios** — `technical_report.html`, `executive_report.html`, instrument/model/dataset cards,
  `evidence_report.json`, `manifest.json` com hashes de todos os artefatos.
- **Observabilidade** — logs JSON com redação de PII, métricas RED com labels fechados, `traceparent` W3C.
- **Adapters** — Themis (payload de política) e Argus (data product), declarados `unverified`; Aegis `disabled`.
- **Estudo Monte Carlo** — `reports/monte_carlo/` (100 réplicas × N ∈ {500, 1000, 2000}; DIF 50 × 2 condições).
- **Testes** — 58 testes (unit, statistical, integration, r_parity).
- **Documentação** — README, AGENTS.md, ADR-001..011, metodologia, runbooks A1–A8, roteiro de demo de
  8 minutos e conteúdo dos 14 slides.

### Decisões que divergem do plano (registradas)

- Motor TRI nativo em Python com mirt como referência de paridade (ADR-002), em vez de mirt obrigatório.
- SQLite em vez de PostgreSQL na PoC (ADR-011).
- CFA ordinal com script pronto, mas fora do pipeline; S6 (multidimensionalidade) não implementado.
