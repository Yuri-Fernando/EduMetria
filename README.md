# 📐 EduMetria

### Python · R/mirt · lavaan · TRI (2PL/GRM/3PL) · TCT · DIF · Linking · CAT · FastAPI · PostgreSQL/RLS · OpenTelemetry

## Status

🟡 **v0.3.0 — P0, P1 e P2 (sem parceria) implementados e testados: 105 testes (R/mirt e PostgreSQL/RLS incluídos),
notebook end-to-end executado e validação com dados públicos reais (ENEM 2023). Piloto com escolas, juízes reais e
estudo de impacto dependem de parceria e ainda não foram realizados.**

🆕 **O que há de novo** — v0.2.0 (P1): CFA ordinal e invariância no pipeline, PostgreSQL com Row Level Security, OIDC,
tracing OpenTelemetry + Prometheus/Grafana/Jaeger, CRUD editorial com imutabilidade, copiloto restrito e integrações
**verificadas** contra o código real do ThemisAI, AegisLLM e Argus, relatório PDF · v0.3.0 (P2): trilha B com microdados do
ENEM, linking longitudinal, CAT, bifator/testlet, 3PL/GPCM, multinível, desenho de impacto e
[notebook end-to-end](notebooks/edumetria_end_to_end.ipynb). Detalhes em [CHANGELOG.md](CHANGELOG.md).

## Descrição / Contexto

**Pesquisa aplicada / Portfólio — projeto autoral em desenvolvimento.**

Infraestrutura de **medição educacional rastreável**: construção de instrumentos, análise psicométrica
(TCT, TRI 2PL e GRM com escores EAP e incerteza), equidade (DIF), evidências de validade por seção e
acompanhamento escolar com **revisão humana persistente** — mantendo separados três objetos que costumam
ser confundidos: *medida psicométrica*, *sinal observado* (faltas) e *risco preditivo*.

O estudo parte de uma pergunta: **como produzir medidas educacionais interpretáveis, com incerteza
conhecida e evidência rastreável, e combiná-las com registros escolares para orientar apoio pedagógico
e acompanhamento de permanência — sem que nenhum modelo decida sozinho sobre um estudante?**

Para responder com rigor, o projeto trabalha com **simulação com gabarito conhecido**: uma população
artificial (2 municípios, 20 escolas, 2.000 estudantes do 6º ano) responde a um instrumento autoral de
matemática (24 itens) e a uma escala de pertencimento escolar (12 itens), com frequência diária ao longo
de 60 dias letivos. Como os parâmetros verdadeiros são conhecidos, é possível verificar se o motor
**recupera** o que foi gerado, se **detecta** DIF plantado sem inflar falsos positivos, se **bloqueia**
dados inválidos e vazamento temporal, e se os escores **agregam** valor preditivo à frequência.

> **O que o estudo mostra:** que o método psicométrico pode ser transformado em software verificável,
> com resultados reproduzíveis por manifesto. **O que ainda não mostra:** validade do instrumento em
> contexto real ou efeito sobre permanência — isso exige dados reais, especialistas e estudo de impacto.
> Itens autorais e ilustrativos; pareceres de juízes simulados; nenhum dado de estudante real.

---

## 🎯 Objetivo

- Produzir medidas interpretáveis, **com incerteza conhecida** e evidência rastreável até a versão do item;
- Provar, por simulação com gabarito conhecido, que o motor recupera parâmetros e detecta DIF com falso
  positivo controlado;
- Bloquear, por construção, os erros clássicos: missing virando zero, vazamento temporal, escala comparada
  sem linking, aprovação sem ator/versão, identidade vinda do corpo da requisição;
- Tornar cada número publicado reproduzível a partir de manifesto (dados, código, seed, versões, hashes).

---

## 🔬 Linha de Pesquisa / Desenvolvimento

- Teoria de Resposta ao Item (2PL, 1PL/Rasch, GRM) por máxima verossimilhança marginal (EM);
- Teoria Clássica dos Testes e evidências de validade (Standards AERA/APA/NCME);
- Funcionamento diferencial do item (Mantel-Haenszel, regressão logística, BH);
- Estudos Monte Carlo de recuperação de parâmetros e poder/falso positivo;
- Estrutura interna (CFA ordinal WLSMV) e invariância de medida entre grupos;
- Linking de escalas entre ondas (mean-mean, mean-sigma, Stocking-Lord, Haebara) e testagem adaptativa (CAT);
- Validação externa com dados públicos reais (microdados do ENEM, parâmetros oficiais do Inep);
- Desenho de estudos de impacto por clusters (MDES, poder, pré-registro);
- Predição point-in-time com validação temporal e espacial externa;
- Governança: revisão humana, auditoria com hash-chain, outbox transacional.

---

## 🏗️ Arquitetura

```text
Gerador sintético (cenários S0–S11, seed)          configs/item_bank.yaml (matriz + itens autorais)
        ↓
Importação validada → quarentena (A2) → snapshot SHA-256
        ↓
TCT ──► TRI 2PL / 1PL / GRM (MML-EM) ──► EAP + posterior_sd + intervalo
        │                     ▲
        │          r/fit_irt.R (mirt) — referência de paridade
        ↓
Diagnósticos (Q3, obs×esp, dimensionalidade) · DIF (MH + LR, BH) · Validade de conteúdo (I-CVI, Aiken V)
        ↓
Risco point-in-time (B0–B3, escolas externas)  ← medida, sinal e risco em cartões separados
        ↓
PsychometricEvidenceReport (status por seção) · relatórios HTML · cards · manifest.json
        ↓
API FastAPI (demo ou OIDC/JWKS) ──► worker (lease/idempotência) ──► registry: candidate → released (revisão humana)
   │  CRUD editorial: item → versão → 3 pareceres → aprovação → caderno (versão travada)
   │  casos de apoio: proposed → under_review → approved → …   ·   copiloto restrito (/v1/copilot/ask)
   ↓
Persistência: SQLite  |  PostgreSQL + Row Level Security (papel da aplicação sem BYPASSRLS)
Observabilidade: logs JSON redigidos · /metrics → Prometheus → Grafana · spans OTLP → Collector → Jaeger
   ↓
Integrações verificadas contra o código real: ThemisAI (policy engine + prompt security) ·
AegisLLM (guardrails) · Argus (validador de contrato RFC-001) — status `verified_local` com commit registrado
```

Decisões registradas em [`docs/adr/`](docs/adr/) (ADR-001 a ADR-015).

---

## ⚙️ Funcionamento

1. `edumetria analyze --scenario s2` gera a população artificial do cenário (seed fixa);
2. O lote passa pela validação: versão desconhecida **bloqueia** o run; duplicatas, categorias inválidas e
   atrasos vão para quarentena com motivo;
3. TCT, 2PL, 1PL e GRM são ajustados; escores EAP saem com `posterior_sd` e intervalo 90%;
   estudante sem resposta informativa recebe `insufficient_evidence` (θ ausente, nunca a média do prior);
4. DIF, validade de conteúdo e diagnósticos entram no relatório de evidências com status próprio
   (`supported` / `exploratory` / `insufficient` / `not_assessed`);
5. O worker registra a calibração como **candidata**; só um psicometrista a libera (com motivo e versão);
6. Escores via API só existem para calibração liberada; casos de apoio só executam após aprovação por
   outra pessoa (segregação de funções), com auditoria encadeada.

---

## 🧠 Inteligência / Modelagem

- **2PL:** P(X=1|θ) = logistic(a(θ−b)), D=1; exporta (a, d) e (a, b). **GRM:** P(X≥k|θ) = logistic(a(θ−b_k)).
- **MML-EM (Bock–Aitkin)**, quadratura de 61 pontos, θ~N(0,1); SE por produto cruzado; SE(b) por delta.
- **EAP** com prior documentado; intervalo por quantis da posterior; MLE só para mostrar a divergência em
  padrões extremos.
- **DIF:** Δ_MH (ETS A/B/C) + LR uniforme/não uniforme, BH, grupos < 200 = evidência insuficiente.
- **Risco:** alvo proxy censurado; B2 = B1 + θ + posterior_sd; bootstrap agrupado por escola.
- **Nenhuma estatística depende de LLM** (ADR-009).

Detalhes: [`docs/methodology/psicometria.md`](docs/methodology/psicometria.md) ·
[`docs/methodology/risco_preditivo.md`](docs/methodology/risco_preditivo.md).

---

## 🧪 Desenvolvimento Experimental

| Cenário | O que injeta | Uso |
|---|---|---|
| S0 | ajuste ao modelo, sem DIF, missing 2% | baseline |
| S1 | discriminação baixa, itens extremos | flags de TCT/TRI |
| S2 | DIF uniforme em A05, A13, A21 | sensibilidade de DIF |
| S3 | DIF não uniforme + grupos assimétricos | LR não uniforme |
| S4 | MCAR + MNAR + não alcançados | missing ≠ zero |
| S5 | testlet (dependência local) | Q3 · bifator |
| S6 | 2ª dimensão em 6 itens (r = 0,3) | triagem dimensional · CFA |
| S7 / S8 | mudança de θ / drift de parâmetro | ADR-008 |
| S9 | categorias raras, padrões extremos | GRM e EAP |
| S10 | duplicatas, versão inválida, categoria inválida, atraso | quarentena |
| S11 | feature com vazamento temporal | bloqueio point-in-time |

---

## 🛠️ Tecnologias

| Categoria | Ferramentas |
|---|---|
| Psicometria | NumPy/SciPy (motor nativo), R 4.6 + mirt 1.47 (referência, 3PL/GPCM/bifator), lavaan (CFA/invariância) |
| Dados/ML | pandas, scikit-learn, statsmodels (MixedLM), pyarrow |
| Produto | FastAPI, Pydantic v2, SQLite · PostgreSQL 16 + RLS, Streamlit, Matplotlib, ReportLab (PDF) |
| Segurança | OIDC (PyJWT RS256 + JWKS), RBAC por escola, RLS, integrações ThemisAI/AegisLLM |
| Qualidade | pytest (unit, statistical, integration, r_parity, PostgreSQL), GitHub Actions |
| Observabilidade | OpenTelemetry → Collector → Jaeger · Prometheus + regras de alerta · Grafana provisionado |

---

## 📊 Resultados

Todos os valores abaixo vêm de execuções reais registradas em `reports/` (dados sintéticos).

**Paridade com mirt 1.47 (R 4.6.1)** — mesmo dado, mesma parametrização:

| Modelo | logLik (Python × mirt) | máx. \|Δ\| parâmetros | máx. \|Δ\| EAP | SE (dif. relativa) |
|---|---|---|---|---|
| 2PL 2000×24 | −26027,3426 × −26027,3427 | a: 5,4e-4 · b: 3,5e-4 | 3,4e-4 | ≤ 3e-4 |
| GRM 2000×12 | −26488,3594 × −26488,3597 | a: 8,6e-4 · b: 1,2e-3 | — | — |

**Monte Carlo — recuperação 2PL** (`reports/monte_carlo/recovery_2pl.json`; 24 itens, 2% MCAR,
100 réplicas por condição, 100% convergência):

| N | RMSE(a) | RMSE(b) | Cobertura IC95% a | Cobertura IC95% b | corr(θ̂, θ) |
|---|---|---|---|---|---|
| 500 | 0,161 | 0,149 | 0,959 | 0,970 | 0,907 |
| 1000 | 0,112 | 0,107 | 0,956 | 0,957 | 0,906 |
| 2000 | 0,078 | 0,076 | 0,950 | 0,955 | 0,907 |

Meta exploratória do plano (RMSE ≤ 0,30 em N=2000) atingida; definida antes do estudo.

**Monte Carlo — DIF** (`reports/monte_carlo/dif_power_fpr.json`; N=2000, 50 réplicas, âncoras = todos os
outros itens): sem DIF → falso positivo 0,0%; com DIF uniforme em 3 itens → poder 97,3%
(A05 94%, A13 98%, A21 100%), falso positivo 0,57% por item (8% das réplicas com ≥1 falso positivo).

**Runs de demonstração** (`reports/demo_runs/`):

| Run | Resultado principal |
|---|---|
| S0 (`run-s0-20260929T001555-192303`) | α=0,851 [0,840; 0,862]; 2PL e GRM convergiram; RMSE(b)=0,076; 1 falso positivo de DIF (A08, não uniforme) → revisão |
| S2 (`run-s2-20260929T001628-ab547f`) | A05, A13, A21 detectados (ETS C), mais A08; RMSE(b)=0,137 (o 2PL comum fica mal especificado sob DIF, por construção) |
| S10 (`run-s10-…-ada755` → `run-s10-…-395e01`) | lote **bloqueado** (110 linhas em quarentena: 25 versão desconhecida, 15 categoria inválida, 40 duplicatas, 30 atrasadas); reexecução com lote corrigido reproduz S0 |
| 🆕 v0.3.0: S0, S2, S6 (`run-s0-20260929T152744-6b9ca7`, `run-s2-20260929T152846-a6a9d6`, `run-s6-20260929T153018-527483`) | mesmos resultados de medição, agora com seção `structure_invariance` (CFA/invariância), PDF técnico e manifesto ligado ao commit `9d805ae` |

**Risco preditivo (S0/S2, escolas externas, t0=40)**: AUC B0=0,872 · B1=0,873 · B2=0,875 · B3=0,79;
**ΔAUC B2−B1 = +0,003, IC95% [−0,034; 0,037]** → a hipótese H3 (escores agregam valor preditivo) **não foi
confirmada** nesta simulação. Resultado mantido como está.

**Benchmark:** 2PL 2000×24 em 0,30 s de parede (Intel x64 Family 6 Model 158, Python 3.10.8) — orçamento do plano: 10 min.

### 🆕 Dados reais — ENEM 2023, Matemática (`reports/trilha_b_enem/`)

Microdados públicos do Inep, caderno 1213 (674.819 presentes), amostra de 20 mil, 43 itens com parâmetro oficial:

| Motor | corr(θ, nota oficial) | b × b oficial | observação |
|---|---|---|---|
| 2PL nativo EduMetria | 0,969 (Spearman 0,982) | Spearman 0,980 | 2PL absorve o acerto casual nas inclinações |
| 3PL R/mirt | **0,994** | **r = 0,981** (Spearman 0,992) | item MT147 degenerou (a = 0,02) e foi sinalizado, não escondido |

Não reproduz a nota oficial (procedimento, população e escala próprios do Inep) — mostra que o motor ordena
itens e pessoas como o Inep em dados reais.

### 🆕 Estudos P2 (`reports/p2/`, `python scripts/p2_studies.py`)

| Estudo | Resultado |
|---|---|
| **Linking** (2 ondas, crescimento real 0,40, âncora com drift) | sem linking o crescimento some (0,000); Stocking-Lord com todas as âncoras: 0,480 (erro +0,080); âncora I00 sinalizada; sem ela: 0,394 (erro −0,006) |
| **CAT** (banco de 120 itens) | 13,9 itens em média com RMSE 0,355 × forma fixa de 24 itens com RMSE 0,344; **exposição máx. 90% e 49 itens nunca usados** → controle Sympson-Hetter no roadmap |
| **Bifator** (S5, testlet A15/A19/A24) | bifator preferido: BIC 53.305 × 53.590 (LR p < 0,001) |
| **3PL × 2PL** (dados gerados por 2PL) | BIC favorece o 2PL (53.146 × 53.314) — como deveria |
| **GRM × GPCM** (dados gerados por GRM) | logLik favorece o GRM (−28.637 × −28.691) |
| **Multinível** (ICC conhecido) | ICC estimado 0,204 (REML) e 0,204 (ANOVA) × realizado 0,196 |
| **Impacto** (ICC de planejamento 0,05) | MDES com 20 escolas × 100 alunos = 0,32 dp; 50 escolas para 0,20 dp; poder simulado para −3 p.p. com 20 escolas: 56% |
| **CFA / invariância** (S0, run `run-s0-20260929T152744-6b9ca7`) | CFA 1 fator: matemática CFI 0,999 / RMSEA 0,006, pertencimento CFI 1,000; invariância A×B: limiares p = 0,82, cargas p = 0,22 · no S6 (`run-s6-20260929T153018-527483`, 2 dimensões) a CFA de matemática cai para CFI 0,879 / RMSEA 0,052 |

### 🆕 Governança e plataforma (P1) — verificações executadas

| Verificação | Resultado |
|---|---|
| PostgreSQL + RLS | `SELECT` sem filtro de tenant → só o tenant da sessão; `INSERT` em outro tenant bloqueado; papel sem `BYPASSRLS` |
| OIDC | token válido aceito; expirado, audience/issuer errados, papel inválido, `alg=none` e outra chave → 401 |
| Tracing | span por requisição continua o `traceparent`; atributos só rota/método/status; traces chegam ao Jaeger; Prometheus raspa `/metrics`; Grafana com dashboard RED |
| CRUD editorial | 3 pareceres independentes para aprovar; autor não julga o próprio item; versão travada após caderno (409); nova versão com linhagem |
| Integrações | ThemisAI `verified_local` (o policy engine real **nega** uso com menores sem consentimento do responsável — POL-003); AegisLLM `verified_local`; Argus: contrato validado pelo validador real, sem erros |
| Copiloto | 20 casos: acurácia 100%, recusa de ataques 100%, falsa recusa 0% — dataset do próprio autor (mede conformidade, não robustez adversarial) |

---

## 🚀 Aplicações

- Ensino e demonstração de TRI/TCT/DIF com gabarito conhecido;
- Base de engenharia para um piloto com redes municipais (após governança e ética);
- Referência de como separar medida, sinal e risco em sistemas de alerta educacional.

---

## 🔭 Visão de Longo Prazo

Um núcleo de medição que qualquer produto educacional do ecossistema possa consumir por contrato — com
escalas ligadas entre versões, invariância verificada, revisão por especialistas reais e avaliação de
impacto das intervenções — sem que nenhum modelo decida sozinho sobre um estudante.

---

## 🗺️ Roadmap

Resumo — detalhes em [ROADMAP.md](ROADMAP.md):

- **P0 ✅** matriz/itens, gerador, DQ, TCT, 2PL/GRM, EAP, DIF, registry com liberação manual, API, painel, testes.
- **P1 ✅** CFA ordinal e invariância no pipeline, PostgreSQL + RLS, OIDC, OTel/Prometheus/Grafana, CRUD editorial, integrações verificadas, copiloto, PDF.
- **P2 ✅ (o que não depende de parceria)** dados públicos reais (ENEM), linking, CAT, bifator, 3PL/GPCM, multinível, desenho de impacto e pré-registro.
- **P2 🧪 (depende de parceria)** piloto com escolas, juízes reais, entrevistas cognitivas, execução do estudo de impacto.

---

## 🔮 Próximos Passos

1. Controle de exposição Sympson-Hetter no CAT e banco maior de itens;
2. Migrations versionadas (Alembic) para o PostgreSQL;
3. Linking com dados reais entre edições do ENEM (itens comuns publicados);
4. Buscar parceria para piloto com revisão ética, juízes reais e o estudo de impacto pré-registrado.

---

## ▶️ Como Rodar

```bash
pip install -r requirements.txt
export PYTHONPATH=src            # PowerShell: $env:PYTHONPATH="src"

python -m edumetria.cli analyze --scenario s2           # run completo → runs/<run_id>/
python -m edumetria.cli analyze --scenario s10          # demonstra bloqueio (exit 2)
python -m edumetria.cli analyze --scenario s10 --resolve-quarantine
python -m edumetria.cli recovery-study --reps 100 --dif-reps 50
python -m edumetria.cli benchmark
python -m pytest -q                                      # 105 testes (R e PostgreSQL opcionais localmente)
jupyter notebook notebooks/edumetria_end_to_end.ipynb     # notebook end-to-end (já executado)
python scripts/build_notebook.py                         # regenera e reexecuta o notebook
python scripts/p2_studies.py                             # linking, CAT, bifator, multinível, impacto, copiloto
python scripts/trilha_b_enem.py --zip <microdados_enem_2023.zip>   # dados reais (download no site do Inep)

python -m edumetria.cli demo-data --scenario s2          # snapshot p/ a API
uvicorn apps.api.main:app --port 8000                    # API (tokens demo em configs/demo_users.yaml)
python -m edumetria.worker --loop                        # worker de jobs
streamlit run apps/dashboard/app.py                      # painel

docker compose --profile core up -d                      # PostgreSQL + RLS (porta 15432)
docker compose --profile observability up -d             # Collector + Jaeger (16686) + Prometheus (9090) + Grafana (3000)
python scripts/dev_oidc.py init && EDUMETRIA_AUTH_MODE=oidc ...   # OIDC com emissor local (ver ADR-013)
```

Paridade com R (opcional): `EDUMETRIA_RSCRIPT=<caminho do Rscript>`, `EDUMETRIA_R_LIBS=<lib com mirt>` e
`python -m pytest -q -m r_parity`. Sem R, esses testes são **pulados e reportados**, nunca substituídos.

---

## Estrutura

```text
EduMetria/
├── src/edumetria/      domain · simulation · data_quality · ctt · irt · dif · validity · risk
│                       registry · reporting · observability · integrations · pipeline · worker · cli
│                       copilot · impact · irt/linking · irt/cat · risk/multilevel · reporting/pdf
├── apps/               api (FastAPI, auth OIDC, tracing OTel) · dashboard (Streamlit)
├── r/                  fit_irt.R · dif.R · cfa_ordinal.R · invariance.R · bifactor.R
├── notebooks/          edumetria_end_to_end.ipynb (executado)
├── scripts/            build_notebook · p2_studies · trilha_b_enem · dev_oidc
├── configs/            item_bank · scenarios/ (S0–S11) · demo_users · support_playbooks · copilot_eval
├── infra/postgres/     papel da aplicação sem BYPASSRLS
├── observability/      otel-collector · prometheus + alertas · grafana (datasources + dashboard)
├── compose.yaml        perfis core e observability
├── tests/              unit · statistical · integration
├── reports/            monte_carlo/ · demo_runs/ · p2/ · trilha_b_enem/ · benchmark.json
└── docs/               adr/ · methodology/ · impact/ · runbooks/ · presentation/ · plano/
```

Histórico: [CHANGELOG.md](CHANGELOG.md) (documento mestre) · [WORKLOG.md](WORKLOG.md) · [AGENTS.md](AGENTS.md).

---

## Status

| Camada | Estado |
|---|---|
| Implementado e testado | TCT, 2PL/1PL/GRM, EAP, DIF, DQ, risco, registry, API, worker, relatórios HTML/PDF, CFA/invariância, PostgreSQL/RLS, OIDC, OTel, CRUD editorial, copiloto, integrações verificadas, linking, CAT, bifator, 3PL/GPCM, multinível, desenho de impacto |
| Validado com dados reais | motor de TRI × ENEM 2023 (parâmetros e notas oficiais do Inep) |
| Planejado | Sympson-Hetter no CAT, Alembic, linking com dados reais entre edições |
| Depende de parceria | piloto, juízes reais, entrevistas cognitivas, execução do estudo de impacto |

## Contexto / Observações

- Código público, sem dados ou credenciais reais; tokens em `configs/demo_users.yaml` são fictícios.
- Itens de `configs/item_bank.yaml` são ilustrativos e não revisados por especialistas.
- A escala interna (θ~N(0,1)) não é comparável a SAEB, ENEM ou PISA; a comparação com o ENEM é de ordenação.
- Microdados do ENEM não são versionados (download público no site do Inep); só resultados agregados.
- `compose.yaml` usa credenciais **locais de demonstração**; em pastas sincronizadas (Google Drive) o Docker Desktop
  não monta arquivos — rode o compose a partir de uma cópia local.
- Referências normativas (LGPD, Enunciado ANPD 1/2023) orientam o desenho; não há parecer jurídico.

---

## 🤖 Autor

**Yuri Fernando Dubbern**

Engenharia Elétrica · Ciência da Computação · Inteligência Artificial ·
Data Science · Automação · Sistemas Embarcados · Pesquisa e Desenvolvimento

[LinkedIn](https://www.linkedin.com/in/yuridubbern) · [GitHub](https://github.com/Yuri-Fernando) · [Lattes](http://lattes.cnpq.br/7151392692642166) · [Linktree](https://linktr.ee/yuri.f.dubbern)
