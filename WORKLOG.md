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
