# Model card — risco preditivo (B2)

- **Alvo:** proxy sintético: ≥5 faltas não justificadas nos 20 dias letivos seguintes a t0; não é definição oficial de abandono/evasão
- **Janela:** 20 dias letivos após t0; alvo censurado quando a janela não terminou (nunca negativo)
- **População:** estudantes artificiais; teste em escolas externas ['SCH02', 'SCH03', 'SCH09', 'SCH10', 'SCH16', 'SCH19']
- **Features:** frequência recente (20d/10d/tendência) + θ matemática/pertencimento e respectivos posterior_sd, todos point-in-time
- **Splits:** {'train_t0_days': [20, 30], 'test_t0_days': [40], 'train_schools': ['SCH01', 'SCH04', 'SCH05', 'SCH06', 'SCH07', 'SCH08', 'SCH11', 'SCH12', 'SCH13', 'SCH14', 'SCH15', 'SCH17', 'SCH18', 'SCH20'], 'test_schools': ['SCH02', 'SCH03', 'SCH09', 'SCH10', 'SCH16', 'SCH19'], 'horizon_days': 20, 'embargo': 'escolas de teste disjuntas do treino; sem estudante em comum'}
- **Métricas (teste externo):** {'n': 603, 'prevalence': 0.0845771144278607, 'roc_auc': 0.9075731741972151, 'pr_auc': 0.5907420820160215, 'brier': 0.05318486679155333, 'k': 61, 'precision_at_capacity': 0.4918032786885246, 'recall_at_capacity': 0.5882352941176471, 'coefficients': {'unjust_abs_20d': -0.0854, 'abs_rate_10d': 1.0329, 'abs_trend': -0.5438, 'theta_math': -0.5252, 'psd_math': -0.1885, 'theta_belong': -0.3166, 'psd_belong': 0.016}}
- **Valor incremental B2−B1:** {'mean': 0.009227303216955429, 'ci95': [-0.002556228410447669, 0.02258179594004104]}
- **Calibração:** ver `risk_evaluation.json` → calibration_B2
- **Equidade preditiva por grupo artificial:** [{'group': 'A', 'n': 300, 'n_positive': 23, 'status': 'computed', 'flag_rate': 0.09666666666666666, 'recall': 0.5652173913043478, 'fpr': 0.05776173285198556, 'precision': 0.4482758620689655, 'calibration_in_the_large': -0.01572180607639169}, {'group': 'B', 'n': 303, 'n_positive': 28, 'status': 'computed', 'flag_rate': 0.10561056105610561, 'recall': 0.6071428571428571, 'fpr': 0.05454545454545454, 'precision': 0.53125, 'calibration_in_the_large': -0.02474972643746276}]
- **Limitações:** relação θ→faltas foi gerada pela simulação; não prova ganho em escolas reais
- **Política de uso:** priorização para revisão humana dentro da capacidade; nunca excluir estudante por score
- **Drift/revisão:** recalibração só por decisão humana (ADR-008)
