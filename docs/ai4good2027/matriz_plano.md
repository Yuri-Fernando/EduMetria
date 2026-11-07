# Matriz do plano de melhorias AI4Good 2027 × estado do repositório

Comparação item a item do plano de melhorias (versão 1.0, 07/11/2026) com o que existia na v0.3.1 e o
que foi feito na v0.4.0. Legenda: **já existe** · **ajustado** · **criado** · **bloqueado por parceria**.

| Item do plano | Estado antes (v0.3.1) | Ação na v0.4.0 | Onde |
|---|---|---|---|
| Posicionamento "EduMetria Social", proposta em 1 frase, ODS 4 | inexistente (README técnico) | **criado** | README (seção AI4Good), `pitch_60seg.md`, painel aba 1 |
| P0-A Jornada guiada do educador | painel técnico com 8 abas | **criado** modo Educador; abas técnicas **preservadas** no modo Pesquisador | `apps/dashboard/educator_page.py`, `apps/dashboard/app.py` |
| P0-A.1 Aviso fixo de dados sintéticos | aviso global | **ajustado**: aviso em todas as telas, no JSON, no resumo exportado e nas capturas | painel, `educator_view.json`, `render_school_summary_html` |
| P0-A.2 Seleção de turma/cenário fictício | seleção de run | **criado** seletor de escola fictícia + cenário S12 | `configs/scenarios/s12_educator_demo.yaml` |
| P0-A.3 Painel por domínio com incerteza; medida × sinal × risco | separação existia só na aba técnica | **criado** artefato agregado por escola/eixo, com intervalos | `src/edumetria/reporting/educator.py` |
| P0-A.4 Cartões consultivos com a razão do sinal | inexistente | **criado** (o que vimos, por quê, incerteza, o que pode estar errado, playbook ilustrativo) | `educator.py::_cards` |
| P0-A.5 Encaminhar para revisão (fluxo existente) | API `/v1/support-cases` com RBAC, segregação e auditoria | **reutilizado**: o painel chama a API real; nenhum atalho | `educator_page.py::_cards_tab`, `_review_tab` |
| P0-A.6 Tela de transparência | mapa de evidências técnico | **criado** (proveniência, equidade, controle humano, usos proibidos) | aba 6 |
| P0-B Caso fictício antes/durante/depois | inexistente | **criado** no painel, gerado do run (sem nomes) | aba 1 |
| P0-C Matriz de evidências | resultados espalhados no README | **criado** | `evidence_matrix.md` |
| P0-D Roteiro 3 min e pitch 60 s | roteiro de 8 min | **criado** (8 min mantido) | `roteiro_demo_3min.md`, `pitch_60seg.md` |
| P0-E Ética e controle humano funcionais | proteções no domínio | **reutilizado** + cartões sempre `requires_human_review`; risco nunca gera prioridade (testado) | testes `test_educator_view.py`, `test_educator_flow.py` |
| P1 Plano de piloto | pré-registro de impacto | **criado** a partir do template | `plano_piloto.md` |
| P2 Exportar resumo de uma página | relatórios técnicos | **criado** (HTML, agregados, ressalvas) | aba 6 |
| P2 Tutorial de 3 passos | — | **criado** | topo do modo Educador |
| P2 Modo educador × pesquisador | — | **criado** | barra lateral |
| P2 Checklist de interpretação antes de aprovar | — | **criado** (aprovar fica desabilitado sem os 5 itens; contagem vai na justificativa auditada) | aba 4 |
| P2 "Como o modelo chegou aqui?" | — | **criado**, só com artefatos reais do run | aba 5 |
| Verificação de que o sinal funciona | — | **criado** estudo Monte Carlo com gabarito (e correção de 2 vieses encontrados) | `scripts/educator_signal_study.py` |
| Piloto, educadores reais, juízes reais, impacto | — | **bloqueado por parceria** | `plano_piloto.md` |
| Confirmações do edital (equipe, idade, IP, open source) | — | **fora do escopo do repositório** — depende da organização | — |

**Não feito, por decisão do plano:** novo framework/banco/motor de IA, reescrita da API, multiagentes,
predição de evasão, implantação cloud, integração com sistemas escolares, coleta de dados de menores.
