# Model card — risco preditivo (B2)

- **Alvo:** proxy sintético: ≥5 faltas não justificadas nos 20 dias letivos seguintes a t0; não é definição oficial de abandono/evasão
- **Janela:** 20 dias letivos após t0; alvo censurado quando a janela não terminou (nunca negativo)
- **População:** estudantes artificiais; teste em escolas externas ['SCH02', 'SCH03', 'SCH09', 'SCH10', 'SCH16', 'SCH19']
- **Features:** frequência recente (20d/10d/tendência) + θ matemática/pertencimento e respectivos posterior_sd, todos point-in-time
- **Splits:** {'train_t0_days': [20, 30], 'test_t0_days': [40], 'train_schools': ['SCH01', 'SCH04', 'SCH05', 'SCH06', 'SCH07', 'SCH08', 'SCH11', 'SCH12', 'SCH13', 'SCH14', 'SCH15', 'SCH17', 'SCH18', 'SCH20'], 'test_schools': ['SCH02', 'SCH03', 'SCH09', 'SCH10', 'SCH16', 'SCH19'], 'horizon_days': 20, 'embargo': 'escolas de teste disjuntas do treino; sem estudante em comum'}
- **Métricas (teste externo):** {'n': 603, 'prevalence': 0.05804311774461028, 'roc_auc': 0.9179577464788733, 'pr_auc': 0.6121992618915857, 'brier': 0.034538369413192285, 'k': 61, 'precision_at_capacity': 0.4098360655737705, 'recall_at_capacity': 0.7142857142857143, 'coefficients': {'unjust_abs_20d': 0.2142, 'abs_rate_10d': 0.7826, 'abs_trend': -0.264, 'theta_math': -0.4554, 'psd_math': -0.0785, 'theta_belong': -0.6877, 'psd_belong': -0.1511}}
- **Valor incremental B2−B1:** {'mean': -0.009450216920819099, 'ci95': [-0.03253781950965051, 0.0041102103293838566]}
- **Calibração:** ver `risk_evaluation.json` → calibration_B2
- **Equidade preditiva por grupo artificial:** [{'group': 'A', 'n': 300, 'n_positive': 16, 'status': 'computed', 'flag_rate': 0.08333333333333333, 'recall': 0.75, 'fpr': 0.045774647887323945, 'precision': 0.48, 'calibration_in_the_large': 0.012052944915502899}, {'group': 'B', 'n': 303, 'n_positive': 19, 'status': 'computed', 'flag_rate': 0.1188118811881188, 'recall': 0.6842105263157895, 'fpr': 0.08098591549295775, 'precision': 0.3611111111111111, 'calibration_in_the_large': 0.026020785090872134}]
- **Limitações:** relação θ→faltas foi gerada pela simulação; não prova ganho em escolas reais
- **Política de uso:** priorização para revisão humana dentro da capacidade; nunca excluir estudante por score
- **Drift/revisão:** recalibração só por decisão humana (ADR-008)
