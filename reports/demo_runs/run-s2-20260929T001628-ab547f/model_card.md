# Model card — risco preditivo (B2)

- **Alvo:** proxy sintético: ≥5 faltas não justificadas nos 20 dias letivos seguintes a t0; não é definição oficial de abandono/evasão
- **Janela:** 20 dias letivos após t0; alvo censurado quando a janela não terminou (nunca negativo)
- **População:** estudantes artificiais; teste em escolas externas ['SCH02', 'SCH03', 'SCH09', 'SCH10', 'SCH16', 'SCH19']
- **Features:** frequência recente (20d/10d/tendência) + θ matemática/pertencimento e respectivos posterior_sd, todos point-in-time
- **Splits:** {'train_t0_days': [20, 30], 'test_t0_days': [40], 'train_schools': ['SCH01', 'SCH04', 'SCH05', 'SCH06', 'SCH07', 'SCH08', 'SCH11', 'SCH12', 'SCH13', 'SCH14', 'SCH15', 'SCH17', 'SCH18', 'SCH20'], 'test_schools': ['SCH02', 'SCH03', 'SCH09', 'SCH10', 'SCH16', 'SCH19'], 'horizon_days': 20, 'embargo': 'escolas de teste disjuntas do treino; sem estudante em comum'}
- **Métricas (teste externo):** {'n': 603, 'prevalence': 0.05970149253731343, 'roc_auc': 0.8747795414462081, 'pr_auc': 0.3924322625863346, 'brier': 0.047491250338326116, 'k': 61, 'precision_at_capacity': 0.2786885245901639, 'recall_at_capacity': 0.4722222222222222, 'coefficients': {'unjust_abs_20d': -0.0557, 'abs_rate_10d': 0.9819, 'abs_trend': -0.5422, 'theta_math': -0.387, 'psd_math': -0.0797, 'theta_belong': -0.4079, 'psd_belong': -0.0448}}
- **Valor incremental B2−B1:** {'mean': 0.002123205747484655, 'ci95': [-0.03489937497428951, 0.03620423967669615]}
- **Calibração:** ver `risk_evaluation.json` → calibration_B2
- **Equidade preditiva por grupo artificial:** [{'group': 'A', 'n': 300, 'n_positive': 18, 'status': 'computed', 'flag_rate': 0.08, 'recall': 0.3888888888888889, 'fpr': 0.06028368794326241, 'precision': 0.2916666666666667, 'calibration_in_the_large': 0.0040752191691136586}, {'group': 'B', 'n': 303, 'n_positive': 18, 'status': 'computed', 'flag_rate': 0.12211221122112212, 'recall': 0.5555555555555556, 'fpr': 0.09473684210526316, 'precision': 0.2702702702702703, 'calibration_in_the_large': 0.017167999683164042}]
- **Limitações:** relação θ→faltas foi gerada pela simulação; não prova ganho em escolas reais
- **Política de uso:** priorização para revisão humana dentro da capacidade; nunca excluir estudante por score
- **Drift/revisão:** recalibração só por decisão humana (ADR-008)
