# 📐 EduMetria

### Python · R/mirt · TRI (2PL/GRM) · TCT · DIF · FastAPI · Streamlit · Psicometria Educacional

## Status

🟡 **PoC v0.1.0 — P0 implementado e testado localmente (59 testes, paridade com mirt verificada).
Dados 100% sintéticos; piloto real, juízes reais e validação de campo ainda não realizados.**

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
API FastAPI ──► worker (lease/idempotência) ──► registry: candidate → released (revisão humana)
        ↓                                         casos de apoio: proposed → under_review → approved → …
Dashboard Streamlit (8 abas)                      auditoria hash-chain · outbox · /metrics · traceparent
        ↓
Adapters: ThemisAI (política, unverified) · Argus (data product, unverified) · AegisLLM (disabled)
```

Decisões registradas em [`docs/adr/`](docs/adr/) (ADR-001 a ADR-011).

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
| S5 | testlet (dependência local) | Q3 |
| S7 / S8 | mudança de θ / drift de parâmetro | ADR-008 |
| S9 | categorias raras, padrões extremos | GRM e EAP |
| S10 | duplicatas, versão inválida, categoria inválida, atraso | quarentena |
| S11 | feature com vazamento temporal | bloqueio point-in-time |

---

## 🛠️ Tecnologias

| Categoria | Ferramentas |
|---|---|
| Psicometria | NumPy/SciPy (motor nativo), R 4.6 + mirt 1.47 (referência), lavaan (CFA, roadmap) |
| Dados/ML | pandas, scikit-learn, statsmodels |
| Produto | FastAPI, Pydantic v2, SQLite, Streamlit, Matplotlib |
| Qualidade | pytest (unit, statistical, integration, r_parity), GitHub Actions |
| Observabilidade | logs JSON com redação, métricas RED, W3C traceparent |

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

**Risco preditivo (S0/S2, escolas externas, t0=40)**: AUC B0=0,872 · B1=0,873 · B2=0,875 · B3=0,79;
**ΔAUC B2−B1 = +0,003, IC95% [−0,034; 0,037]** → a hipótese H3 (escores agregam valor preditivo) **não foi
confirmada** nesta simulação. Resultado mantido como está.

**Benchmark:** 2PL 2000×24 em 0,30 s de parede (Intel x64 Family 6 Model 158, Python 3.10.8) — orçamento do plano: 10 min.

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
- **P1** CFA ordinal no pipeline, PostgreSQL + RLS, OIDC, perfil OTel/Grafana, CRUD de itens, adapters verificados, copiloto via Aegis.
- **P2 🧪** piloto real, juízes reais, entrevistas cognitivas, linking longitudinal, estudos de impacto.

---

## 🔮 Próximos Passos

1. Integrar `r/cfa_ordinal.R` ao pipeline e documentar invariância;
2. Migrar persistência para PostgreSQL com RLS testada;
3. Testar o adapter Themis contra o serviço real e só então marcá-lo como verificado;
4. Buscar parceria para piloto com revisão ética e especialistas.

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
python -m pytest -q                                      # 59 testes

python -m edumetria.cli demo-data --scenario s2          # snapshot p/ a API
uvicorn apps.api.main:app --port 8000                    # API (tokens demo em configs/demo_users.yaml)
python -m edumetria.worker --loop                        # worker de jobs
streamlit run apps/dashboard/app.py                      # painel
```

Paridade com R (opcional): `EDUMETRIA_RSCRIPT=<caminho do Rscript>`, `EDUMETRIA_R_LIBS=<lib com mirt>` e
`python -m pytest -q -m r_parity`. Sem R, esses testes são **pulados e reportados**, nunca substituídos.

---

## Estrutura

```text
EduMetria/
├── src/edumetria/      domain · simulation · data_quality · ctt · irt · dif · validity · risk
│                       registry · reporting · observability · integrations · pipeline · worker · cli
├── apps/               api (FastAPI) · dashboard (Streamlit)
├── r/                  fit_irt.R · dif.R · cfa_ordinal.R (mirt/lavaan)
├── configs/            item_bank.yaml · scenarios/ · demo_users.yaml
├── tests/              unit · statistical · integration
├── reports/            monte_carlo/ · demo_runs/ · benchmark.json
└── docs/               adr/ · methodology/ · runbooks/ · presentation/ · plano/ (plano mestre)
```

Histórico: [CHANGELOG.md](CHANGELOG.md) (documento mestre) · [WORKLOG.md](WORKLOG.md) · [AGENTS.md](AGENTS.md).

---

## Status

| Camada | Estado |
|---|---|
| Implementado e testado | TCT, 2PL/1PL/GRM, EAP, DIF, DQ, risco, registry, API, worker, relatórios |
| Implementado, não integrado | CFA ordinal (script R) |
| Planejado | PostgreSQL/RLS, OIDC, OTel, copiloto, CRUD editorial |
| Depende de piloto | validade real, juízes reais, invariância empírica, impacto |

## Contexto / Observações

- Código público, sem dados ou credenciais reais; tokens em `configs/demo_users.yaml` são fictícios.
- Itens de `configs/item_bank.yaml` são ilustrativos e não revisados por especialistas.
- A escala interna (θ~N(0,1)) não é comparável a SAEB, ENEM ou PISA.
- Referências normativas (LGPD, Enunciado ANPD 1/2023) orientam o desenho; não há parecer jurídico.

---

## 🤖 Autor

**Yuri Fernando Dubbern**

Engenharia Elétrica · Ciência da Computação · Inteligência Artificial ·
Data Science · Automação · Sistemas Embarcados · Pesquisa e Desenvolvimento

[LinkedIn](https://www.linkedin.com/in/yuridubbern) · [GitHub](https://github.com/Yuri-Fernando) · [Lattes](http://lattes.cnpq.br/7151392692642166) · [Linktree](https://linktr.ee/yuri.f.dubbern)
