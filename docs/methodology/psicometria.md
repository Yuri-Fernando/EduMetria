# Metodologia psicométrica — EduMetria v0.1

> Referências conceituais: Standards AERA/APA/NCME (2014) [S01]; Chalmers (2012), mirt [S02–S06];
> lavaan (dados categóricos) [S07]. Lista completa na seção 33 de `docs/plano/POC_EduMetria_Plano_Mestre_v1.1.txt`.

## TCT (`src/edumetria/ctt/analysis.py`)

- p = proporção de acerto **entre respostas válidas**; omissão reportada à parte.
- r ponto-bisserial corrigida = corr(item, total − item), casos completos; n efetivo sempre reportado.
- α = k/(k−1)·[1 − Σvar(X_j)/var(ΣX_j)], IC por bootstrap percentil. Coincide com KR-20 em itens 0/1 (testado).
- Estados explícitos: `constant_item`, `no_variance`, `small_sample`, `not_administered` — nunca zero como valor válido.
- Flags (p>0,95, p<0,05, r<0,15, r<0, omissão>10%) são gatilhos investigativos da PoC, não critérios de exclusão.

## TRI (`src/edumetria/irt/`)

- 2PL: P(X=1|θ) = logistic(a(θ−b)), D=1; exporta (a,d) e (a,b), com d = −ab.
- 1PL comparador: slope comum com θ~N(0,1) ≡ reparametrização do Rasch (σ = a comum).
- GRM: P(X≥k|θ) = logistic(a(θ−b_k)); limiares ordenados por parametrização; categoria vazia → erro explícito.
- Estimação: MML-EM (Bock–Aitkin), quadratura retangular de 61 pontos em [−6, 6], tolerância 1e-4 na mudança máxima de parâmetro; não convergência → aviso e bloqueio de liberação.
- SE: produto cruzado dos escores individuais (equivalente a `SE.type="crossprod"`); SE(b) por método delta.
- Paridade com mirt 1.47 verificada (ADR-002).

## Escores

- EAP com prior N(0,1); `posterior_sd` (não rotulado como SE frequentista); intervalo 90% por quantis da posterior.
- Sem resposta informativa → `insufficient_evidence`, θ ausente.
- MLE disponível só para demonstrar a divergência em padrões todos-corretos/incorretos.

## Diagnósticos

- Q3 de Yen (dependência local), observado × esperado por faixa de θ̂, triagem de autovalores (exploratória).
- CFA ordinal (lavaan, WLSMV) em `r/cfa_ordinal.R` — script pronto, ainda não integrado ao pipeline (roadmap P1).

## DIF (`src/edumetria/dif/analysis.py`)

- Mantel-Haenszel estratificado pelo escore (âncoras + item estudado); Δ_MH = −2,35·ln α_MH; classes ETS A/B/C.
- Regressão logística: LR para DIF uniforme (grupo) e não uniforme (grupo×escore); ΔR² de Nagelkerke como magnitude.
- Benjamini-Hochberg sobre todas as comparações; grupo < 200 → `insufficient_evidence`.
- Regra de sinalização (pré-definida, não ajustada depois): uniforme = ETS B/C com p_BH<0,05; não uniforme = p_BH<0,05. Todo achado → `pending_human_review`.
- Referência mirt: `r/dif.R` (multipleGroup + DIF, Wald/LR).

## Validade de conteúdo (`src/edumetria/validity/content.py`)

- I-CVI (proporção de notas 3–4 em relevância), S-CVI/Ave com distribuição, Aiken V com IC (Penfield & Giacobbi, 2004).
- Pareceres simulados têm `evidence_origin=simulated_review` e nunca contam como evidência humana.
