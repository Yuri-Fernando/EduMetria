# Runbooks — alertas A1–A8

Formato: sintoma · impacto · consultas seguras · hipóteses · mitigação · recuperação · responsável.
A PoC não envia mensagens reais; cada alerta precisa de destinatário configurado no piloto.

| Alerta | Sintoma | Mitigação |
|---|---|---|
| A1 | job `running` sem heartbeat além do lease | **Implementado:** `claim_job` retoma job com lease expirado; tentativa contabilizada; candidato só é registrado no fim (sem duplicação). |
| A2 | lote com versão de item desconhecida | **Implementado:** `validate_responses` marca `blocking`; pipeline para com `blocked_by_data_quality`; reexecução só com `--resolve-quarantine` (linhas aceitas). |
| A3 | calibração não converge | **Implementado:** aviso no ajuste e `release_calibration` recusa (409). Inspecionar dados/categorias/inícios; nunca substituir por números. |
| A4 | aumento de missing | Manual: comparar `omission_by_reason` por escola/aplicação antes de qualquer interpretação pedagógica. |
| A5 | DIF/âncora instável | **Implementado:** achado nasce `pending_human_review`; nada é removido. Suspender comparação afetada e registrar decisão. |
| A6 | vazamento de dado em log | **Implementado (prevenção):** redação de chaves e padrões sensíveis no logger; teste T25. Incidente: restringir acesso, conter, corrigir coletor. |
| A7 | dependência LLM falha | N/A na PoC (LLM desligado); o relatório determinístico não depende de LLM. |
| A8 | fila de intervenção acima da capacidade | Manual: capacidade explícita (10%) no modelo; revisar fluxo com a coordenação. |

Consultas seguras: `GET /v1/jobs/{id}`, `GET /v1/audit` (auditor), `runs/<run_id>/run.log` (sanitizado), `data_quality.json`.
