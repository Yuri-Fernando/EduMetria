# Metodologia — risco preditivo e acompanhamento

- **Alvo (proxy sintético):** ≥5 faltas não justificadas nos 20 dias letivos após t0. Janela incompleta → `censored` (NaN), nunca 0. Não é definição de abandono ou evasão.
- **Point-in-time:** toda feature carrega `available_at`; `assert_point_in_time` bloqueia qualquer coisa posterior a t0 (`LeakageError`). Escores psicométricos só existem a partir do dia 12.
- **Snapshots:** t0 = 20 e 30 (treino), 40 (teste), 45 (exemplo censurado).
- **Split:** temporal **e** espacial — escolas de teste disjuntas do treino (30% das escolas, seed fixa).
- **Baselines:** B0 regra de frequência; B1 logística só administrativa; B2 = B1 + θ e posterior_sd; B3 gradient boosting calibrado (isotônica, só no treino).
- **Métricas:** ROC-AUC, PR-AUC, Brier, precisão/recall na capacidade (10%), calibração por decil, IC por bootstrap agrupado por escola, ΔAUC B2−B1.
- **Equidade preditiva:** por grupo artificial A/B no ponto de capacidade global (sem limiar por grupo); células < 10 suprimidas.
- **Uso:** priorização para revisão profissional; o modelo nunca decide quem recebe apoio.
