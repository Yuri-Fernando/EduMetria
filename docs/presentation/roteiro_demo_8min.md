# Roteiro de demonstração — 8 minutos

Todos os números vêm de runs reais em `reports/demo_runs/` (dados sintéticos). Se o ajuste ao vivo demorar, usar o run pré-executado **e dizer que é histórico**.

| Tempo | Bloco | O que mostrar | Comando/artefato |
|---|---|---|---|
| 0:00–0:45 | Problema | Aviso de dados sintéticos; medida antes de decisão | dashboard → Visão geral |
| 0:45–1:30 | Matriz e revisão | Blueprint 10/8/6 × 8/10/6; B02 sinalizado por desalinhamento (pareceres simulados) | `configs/item_bank.yaml`, aba Banco e revisão |
| 1:30–2:30 | Dados e qualidade | S10: 110 linhas em quarentena (25 versão desconhecida, 15 categoria inválida, 40 duplicatas, 30 atrasadas) → bloqueio → reexecução com lote corrigido | `edumetria analyze --scenario s10` e `--resolve-quarantine` |
| 2:30–4:00 | Medição | TCT, ICC 2PL, informação do teste, dois estudantes com θ parecido e incertezas diferentes | `technical_report.html` |
| 4:00–4:50 | Equidade | S2: A05/A13/A21 detectados (ETS C); S0: sem DIF plantado, 1 falso positivo (A08) indo para revisão humana | aba Equidade |
| 4:50–5:50 | Acompanhamento | Medida × risco separados; B2 não supera B1 nesta simulação; caso fictício só executa após aprovação persistida | API `/v1/support-cases` |
| 5:50–6:50 | Operação | `/metrics`, `traceparent`, job com snapshot inexistente falha com `invalid_input`; lease expirado é retomado | `pytest tests/integration -q` |
| 6:50–8:00 | Evidência e limites | Mapa de evidências (supported/exploratory/not_assessed); o que exige piloto; sem promessa de reduzir evasão | `evidence_report.json` |
