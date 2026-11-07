# WORKLOG — EduMetria

Log cronológico por sessão, complementar ao `CHANGELOG.md` (orientado a versão).

## 2026-09-28 — v0.1.0: do plano mestre ao P0 executável

### Contexto
Plano mestre (`docs/plano/POC_EduMetria_Plano_Mestre_v1.1.txt`, v1.0) especificava a PoC.
Nesta sessão o P0 foi implementado de ponta a ponta, com execução real.

### Ambiente
Windows 11, Python 3.10.8. R 3.5.1 local não tinha mirt; foi instalado R 4.6.1 em `C:\tmp\R-4.6.1`
(sem admin) + mirt 1.47, lavaan e jsonlite em `C:\tmp\Rlib`. Variáveis usadas nos testes de paridade:
`EDUMETRIA_RSCRIPT=C:/tmp/R-4.6.1/bin/Rscript.exe`, `EDUMETRIA_R_LIBS=C:/tmp/Rlib`.

### Feito (comandos executados, código de saída 0 salvo indicação)
- `python -m pytest -q` → **58 passed** (inclui 3 testes de paridade com mirt).
- Paridade Python × mirt (2PL 2000×24): |Δa| ≤ 5,4e-4, |Δb| ≤ 3,5e-4, |ΔEAP| ≤ 3,4e-4, SE relativo ≤ 3e-4;
  GRM 2000×12: |Δa| ≤ 8,6e-4, |Δb| ≤ 1,2e-3; 1PL: slope 1,07134 × 1,07139.
- `edumetria recovery-study --reps 100 --dif-reps 50` → 33 s (recuperação) + 26 s (DIF); todos os ajustes convergiram.
- `edumetria analyze --scenario s0|s2` → sucesso; `--scenario s10` → **bloqueado** (exit 2) e depois sucesso
  com `--resolve-quarantine`.
- `edumetria benchmark` → 2PL 2000×24 em 0,30 s de parede.

### Achados honestos
- H3 **não confirmado** na simulação: B2 (com θ) ≈ B1 (só frequência): ΔAUC = +0,003, IC95% [−0,034; 0,037].
  A simulação liga θ às faltas, mas a frequência recente já captura quase todo o sinal.
- DIF em S0/S2 sinaliza A08 (não uniforme) sem DIF plantado — falso positivo que vai para revisão humana.
- Pareceres de juízes são simulados; A16/B11 aparecem para revisão por ruído, B02/A23 por desenho.

### Pendente
- CFA ordinal no pipeline, S6, PostgreSQL/RLS, OIDC, perfil de observabilidade, copiloto (ver ROADMAP).

## 2026-09-28 (noite) — correção da CI de paridade

- Detectado ao revisar o log do GitHub Actions: o job "Paridade com R/mirt" terminava verde com os 3 testes pulados (`mirt` não instalou no R 4.4 do runner: dependência `Deriv` indisponível).
- Correção: `r-version: release`, instalação explícita de `Deriv`, passo que falha se `mirt` não carregar e teste `test_r_required_when_flagged` (`EDUMETRIA_REQUIRE_R=1`).
- Local: `EDUMETRIA_REQUIRE_R=1 pytest -m r_parity` → 4 passed com R; 1 failed sem R (comportamento desejado). Suíte total: 59 testes.

## 2026-09-29 — v0.2.0 (P1) + v0.3.0 (P2 sem parceria) + notebook

### Ambiente
Docker Desktop 29.8 (PostgreSQL 16, OTel Collector, Jaeger, Prometheus, Grafana). O Docker Desktop não monta arquivos da
pasta do Google Drive — o compose foi executado a partir de uma cópia em `C:\tmp\edumetria-compose`. Após reinício do
Windows, a porta 55432 caiu numa faixa reservada (Hyper-V) → porta padrão passou a 15432 (`EDUMETRIA_PG_PORT`).

### Feito (execuções reais)
- `pytest -q` com R e PostgreSQL → 105 passed.
- ENEM 2023 (620 MB, lido do zip): θ 3PL × nota oficial r = 0,994; b × b oficial r = 0,981 (sem MT147) — 97 s com cache.
- `scripts/p2_studies.py` → linking, CAT, bifator, 3PL/GPCM, ICC, impacto, copiloto (`reports/p2/`).
- Perfil observability: trace no Jaeger, alvo `edumetria-api` up no Prometheus, dashboard provisionado no Grafana.
- `scripts/build_notebook.py` → notebook executado, 0 erros.

### Bugs encontrados e corrigidos
- MixedLM com `lbfgs` preso na fronteira (ICC 0,15 → 0,0).
- `KeyError` no risco quando o GRM falha; `%` literal no psycopg2; nomes perdidos no JSON do bifator.

### Achados
- Themis (policy engine real) nega uso com menores sem consentimento do responsável (POL-003) — pré-condição do piloto.
- CAT: exposição máxima de 90% e 49/120 itens sem uso — randomesque insuficiente.
- Com 20 escolas, poder de 56% para −3 p.p. no desfecho — piloto pequeno não detectaria efeito realista.

## 2026-11-07 — v0.4.0: EduMetria Social (Visão do Educador, AI4Good 2027)

### Contexto
Aplicação do plano de melhorias AI4Good 2027 (versão 1.0, 07/11/2026): tornar o valor do EduMetria legível para
educadores sem novo framework, banco ou motor. Matriz item a item em `docs/ai4good2027/matriz_plano.md`.

### Ambiente
Windows 11, Python 3.10.8, Streamlit 1.54, Playwright 1.61 (Chromium). **R/mirt e Docker indisponíveis nesta sessão**
(o R 4.6.1 de 2026-09 não está mais na máquina; Docker Desktop parado) → testes de paridade com R e de PostgreSQL
pulados e reportados; a seção `structure_invariance` do run S12 sai `not_assessed` pelo mesmo motivo.

### Feito (comandos executados)
- Linha de base antes de alterar: `pytest -q` → 90 passed, 16 skipped, exit 0.
- `edumetria analyze --scenario s12` e `--scenario s0` → exit 0. S0 regenerado tem o mesmo `dataset_hash` do run de
  demonstração da v0.3.0 (`c46e9c4e…`) — gerador inalterado para cenários existentes (virou teste).
- `scripts/educator_signal_study.py --reps 100` (v1) → falso positivo de 3,93% por teste no S12 (89% das réplicas com
  ≥1 sinal falso) contra 0,05% no S0. Diagnóstico em 15 réplicas: 20 de 34 falsos eram "acima do esperado" nos outros
  eixos das escolas com efeito plantado (contaminação) e o restante vinha do prior N(0,1) aplicado a escolas com média
  diferente (encolhimento). Resultado preservado em `reports/ai4good2027/educator_signal_study_v1_sem_correcao.json`.
- Correção: prior por escola (ML marginal) + purificação iterativa; limiares e seeds inalterados. Diagnóstico nas
  mesmas 15 seeds: 34 → 5 sinais falsos.
- `scripts/educator_signal_study.py --reps 100` (v2, 1.894 s) → S12: poder 98% (99% / 97%), falso positivo 0,38% por
  teste, 15% das réplicas com ≥1; efeito fraco Δb = 0,25: poder 21,5%, FP 0,24%; S0: FP 0,10%, 6% das réplicas.
  Convergência 100% em todas as 300 réplicas.
- `pytest -q` (com a correção) → **103 passed, 16 skipped, exit 0** (262 s).
- Commit do código `f0f1d8f`; `edumetria analyze --scenario s12` → `run-s12-20261107T155216-6daa13` (exit 0, 31 s),
  copiado sem `restricted/` para `reports/demo_runs/`.
- API (`uvicorn`, banco novo) + painel (`streamlit`) + `scripts/capture_ai4good_screens.py` → jornada completa no
  navegador: caso `turma-SCH01-dados_graficos` criado por coord-bruno, aprovado com checklist 5/5 por coord-clara
  (versão 3), `verify_audit_chain()` = True; 7 capturas e resumo exportado.
- Após ajustes visuais no painel: testes da Visão do Educador → 13 passed, exit 0.

### Achados honestos
- O sinal por eixo não enxerga efeitos pequenos com ~100 estudantes por escola (poder 21,5% para Δb = 0,25).
- Resíduo de falso positivo (0,38% por teste no S12) vem da calibração 2PL conjunta das escolas → roadmap.
- No run S12, acrescentar a proficiência à frequência não melhorou o risco (ΔAUC −0,009, IC95% [−0,033; +0,004]).
- Defeitos encontrados nas capturas e corrigidos: gráfico de eixos sem pontos (Altair lê "." em nome de campo como
  acesso aninhado) e checkbox do Streamlit que só responde ao clique no rótulo.

### Pendente
- Piloto, educadores e juízes reais, estudo de impacto (dependem de parceria) — `docs/ai4good2027/plano_piloto.md`.
