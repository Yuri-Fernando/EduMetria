# Metodologia — estudos P2 (linking, CAT, multinível, impacto, modelos alternativos)

Resultados em `reports/p2/` (gerados por `python scripts/p2_studies.py`).

- **Linking longitudinal** (`irt/linking.py`, `simulation/waves.py`): desenho NEAT com 12 âncoras; mean-mean, mean-sigma,
  Stocking-Lord e Haebara; erro de linking por bootstrap nas âncoras; âncora instável sinalizada por resíduo padronizado > 2,5
  (decisão humana, nunca descarte automático).
- **CAT** (`irt/cat.py`): máxima informação com exposição randomesque (k = 3), EAP a cada passo, parada por posterior_sd ≤ 0,35
  ou 24 itens; comparado a forma fixa com os 24 itens mais discriminativos.
- **Multinível** (`risk/multilevel.py`): MixedLM REML (otimizador bfgs/powell — o lbfgs fica preso na fronteira τ² = 0, verificado)
  com checagem cruzada pelo estimador ANOVA; efeitos EB encolhidos.
- **Impacto** (`impact/design.py`): MDES de Bloom para ensaio por clusters, número de escolas necessário e poder por simulação.
- **Modelos alternativos (R/mirt, lavaan):** bifator/testlet (`r/bifactor.R`), 3PL e GPCM como comparadores (`r/fit_irt.R`),
  CFA ordinal WLSMV e invariância configural → limiares → cargas (`r/invariance.R`).
