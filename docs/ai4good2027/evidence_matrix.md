# Matriz de evidências — tecnologia × impacto (EduMetria Social)

Cada afirmação usada no README, no pitch ou no roteiro precisa de uma linha aqui. Números conferidos nos
artefatos em 07/11/2026. **Status:** implementado · validado tecnicamente · planejado · depende de piloto.

## 1. Validação técnica (já existe)

| Afirmação | Evidência verificável | Limite da conclusão | Status |
|---|---|---|---|
| O motor de TRI reproduz o mirt (referência em R) | README › Resultados; `tests/statistical/test_recovery_and_parity.py` (marca `r_parity`, roda na CI) | paridade numérica em dados sintéticos; não é validade do instrumento | validado tecnicamente |
| Recupera parâmetros 2PL com cobertura nominal | `reports/monte_carlo/recovery_2pl.json` (N=2000: RMSE(b) 0,076; cobertura IC95% b 0,955) | simulação com o próprio modelo gerador | validado tecnicamente |
| Detecta DIF plantado com falso positivo controlado | `reports/monte_carlo/dif_power_fpr.json` (poder 97,3%; FP 0,57% por item) | grupos A/B artificiais | validado tecnicamente |
| Revisão humana não pode ser contornada | `tests/integration/test_educator_flow.py` (docente 403; escola fora do escopo 403; `tenant_id` no corpo 422; autoaprovação 403; aprovação por outra coordenadora 200; auditoria íntegra) | proteção de software; não substitui governança institucional | validado tecnicamente |
| Suíte de testes passa | WORKLOG 2026-11-07: `pytest -q` → 103 passed, 16 skipped (R/mirt e PostgreSQL ausentes no ambiente local), exit 0 | os 16 pulados são reportados, não substituídos | validado tecnicamente |

## 2. Visão do Educador (v0.4.0)

| Afirmação | Evidência verificável | Limite da conclusão | Status |
|---|---|---|---|
| A visão não expõe estudantes | `test_view_is_aggregate_only_and_labelled_synthetic`, `test_export_summary_has_banner_and_no_student_ids` | agregados por escola; contagens < 5 suprimidas na exibição | implementado e testado |
| Ausência de resposta não vira zero | `test_missing_never_becomes_zero_in_axis_signal` | — | implementado e testado |
| O risco preditivo não gera prioridade | `test_risk_never_drives_prioritization`; run S12: ΔAUC B2−B1 = −0,009, IC95% [−0,033; +0,004] | decisão de produto baseada em simulação | implementado e testado |
| O sinal por eixo encontra dificuldade plantada | `reports/ai4good2027/educator_signal_study.json`, condição `s12_planted`: poder 98% (SCH01 × dados e gráficos 99%; SCH07 × resolução de problemas 97%), 100 réplicas, 100% de convergência | efeitos de Δb = +0,70 e +0,50 em escolas de ~100 estudantes | validado em simulação |
| O sinal raramente acende sem efeito | mesmo arquivo: falso positivo 0,38% por teste no S12 (15% das réplicas com ≥1) e 0,10% no S0 (6% das réplicas) | resíduo vem da calibração conjunta das escolas; BH controla taxa de descoberta, não elimina falso positivo | validado em simulação |
| Efeitos pequenos passam despercebidos | condição `s12_weak_effect_0.25`: poder 21,5% | limite de tamanho amostral, não defeito a esconder | validado em simulação |
| A primeira versão do sinal tinha viés, corrigido | `reports/ai4good2027/educator_signal_study_v1_sem_correcao.json` (FP 3,93% por teste; 89% das réplicas) × versão atual | mesmas seeds e limiares nas duas versões | registrado |
| Exemplo do caso fictício | run `reports/demo_runs/run-s12-20261107T155216-6daa13` (commit `f0f1d8f`): SCH01 acertou 25,6% em dados e gráficos × 38,8% esperado (−13,2 p.p., IC90% [−16,3; −10,0]); outros eixos +0,4 e −0,2 p.p. | escola e estudantes artificiais | implementado |
| Jornada funciona de ponta a ponta | `scripts/capture_ai4good_screens.py` + `docs/images/ai4good_*.png` (encaminhado por coord-bruno, aprovado com checklist por coord-clara) | usuários e dados de demonstração | implementado |

## 3. Dados públicos reais — ENEM 2023

| Afirmação | Evidência verificável | Limite da conclusão | Status |
|---|---|---|---|
| O motor ordena itens e pessoas como o Inep | `reports/trilha_b_enem/` (3PL mirt: θ × nota oficial r = 0,994; b × b oficial r = 0,981) | um caderno, amostra de 20 mil; **não** reproduz a escala oficial; **não** é acompanhamento longitudinal dos mesmos alunos | validado tecnicamente |

## 4. Simulação educacional

| Afirmação | Evidência | Limite | Status |
|---|---|---|---|
| População de 20 escolas e 2.000 estudantes do 6º ano | `configs/scenarios/` | artificial; **não** é estudo com participantes | implementado |
| Itens de matemática e pertencimento | `configs/item_bank.yaml` | autorais, sem revisão de especialistas reais nem entrevista cognitiva | implementado |

## 5. Impacto social

| Afirmação | Evidência | Limite | Status |
|---|---|---|---|
| Ajuda educadores a decidir onde apoiar | — | **hipótese**; nenhuma entrevista ou teste de usabilidade realizado | depende de piloto |
| Melhora aprendizagem ou permanência | — | **não demonstrado**; exige estudo pré-registrado com comparador | depende de piloto |
| Piloto pequeno detectaria efeito realista | `reports/p2/impact_design.json`: poder de 56% para −3 p.p. com 20 escolas | premissas de planejamento, não resultado | planejado |

**Frases proibidas** (sem evidência): "reduz evasão", "aumenta a aprendizagem em X%", "prevê abandono",
"diagnostica estudantes", "usado por escolas", "validado com professores".
