# Como foi feito — EduMetria Social (v0.4.0)

Registro do processo, na ordem real em que aconteceu, incluindo o erro encontrado no caminho.

## 1. Ponto de partida

O EduMetria v0.3.1 já tinha o motor psicométrico (TCT, TRI 2PL/GRM, EAP com incerteza, DIF), a separação
entre medida, sinal e risco, uma API com revisão humana persistente (RBAC, segregação de funções e auditoria
encadeada por hash) e um painel técnico com 8 abas. Faltava tornar o valor **legível para quem não é
especialista**. O plano de melhorias de 07/11/2026 pedia exatamente isso — sem novo framework, banco,
motor de IA ou reescrita da API.

## 2. Leitura e matriz

Leitura de `AGENTS.md`, README, ROADMAP, WORKLOG, CHANGELOG, roteiro de 8 minutos, slides e pré-registro;
depois, do painel, do pipeline, do gerador sintético e do fluxo `/v1/support-cases`. Resultado em
[matriz_plano.md](matriz_plano.md) (já existe · ajustado · criado · bloqueado por parceria).

**Achado que mudou o desenho:** no gerador, a proficiência não tinha efeito de escola nem dificuldade por
eixo. Qualquer "turma com dificuldade" mostrada no painel seria ruído amostral apresentado como sinal.

## 3. Decisões de desenho

| Decisão | Por quê |
|---|---|
| Estatística no domínio (`reporting/educator.py`), painel só lê `educator_view.json` | regra do projeto: a UI não recalcula estatística; o artefato entra no manifesto com hash |
| Comparar o eixo com **a própria escola** (proficiência nos outros eixos), não com outras escolas | o plano proíbe comparação indevida entre turmas; a pergunta pedagógica é "onde, dentro da minha escola" |
| Só agregados por escola, supressão de contagens < 5 | nenhum identificador de estudante na visão do educador |
| Cartões consultivos com "o que pode estar errado" e playbook ilustrativo | apoiar a discussão, não prescrever conduta |
| Encaminhar e revisar **pela API real**, com checklist que trava a aprovação | evitar aviso cosmético: não existe caminho no painel que contorne a revisão humana |
| Risco preditivo exibido, mas sem gerar prioridade | na simulação, acrescentar a proficiência não melhorou a previsão (IC do ganho inclui zero) |
| Cenário S12 com efeitos plantados, efeitos desligados por padrão | testar com gabarito conhecido sem alterar nenhum cenário existente (o S0 mantém o hash de dados da v0.3.0) |

## 4. Implementação

1. Gerador: `population.theta_school_sd` e `math.school_axis_effects` (sorteio só quando ativo).
2. Cenário S12: efeito de escola (ICC ≈ 0,08) e dificuldade plantada em SCH01 × Dados e gráficos
   (Δb = +0,70) e SCH07 × Resolução de problemas (Δb = +0,50).
3. Módulo `educator.py`: medida (EAP e intervalo de 90% contra corte ilustrativo), sinal por eixo, sinal
   de frequência point-in-time, cartões, avaliação do risco e resumo HTML exportável.
4. Painel: modo Educador (6 abas) e modo Pesquisador (as 8 abas originais).
5. Testes unitários, estatísticos e de integração, incluindo o painel renderizado pelo `streamlit.testing`
   nos dois modos e a jornada completa pela API.

## 5. O erro encontrado — e corrigido antes de publicar

O primeiro estudo Monte Carlo do sinal por eixo (100 réplicas por condição) mostrou **poder alto e
falso positivo quase nulo sem efeito plantado (S0), mas falso positivo de 3,9% por teste no S12, com 89%
das réplicas tendo pelo menos um sinal falso**. O diagnóstico, réplica a réplica, apontou duas causas:

- **Contaminação:** na escola com um eixo difícil, a proficiência estimada pelos "outros eixos" incluía
  esse eixo, então os eixos restantes pareciam "acima do esperado".
- **Encolhimento do prior:** a posterior usava o prior N(0,1) da população inteira; em escolas com média
  diferente, o esperado era puxado para a média geral (viés conhecido do EAP em comparação de grupos).
  O S0 não tinha efeito de escola, por isso não mostrava o problema.

Correções: **prior da própria escola estimado por verossimilhança marginal** e **purificação iterativa**
(como na purificação de âncoras em DIF). Os limiares (BH a 5%, IC de 90%) e as seeds **não foram
alterados**. O resultado da versão sem correção continua publicado em
`reports/ai4good2027/educator_signal_study_v1_sem_correcao.json`.

## 6. Validação

- Suíte completa: comando, código de saída e contagem no [WORKLOG](../../WORKLOG.md).
- Estudo Monte Carlo corrigido: `reports/ai4good2027/educator_signal_study.json` (números na
  [matriz de evidências](evidence_matrix.md)).
- Run de demonstração S12 ligado ao commit do código: `reports/demo_runs/run-s12-20261107T155216-6daa13`.
- Jornada no navegador (Playwright, `scripts/capture_ai4good_screens.py`) contra API e painel reais:
  encaminhamento por `coord-bruno`, aprovação com checklist por `coord-clara`, resumo exportado.

## 7. O que continua fora (e por quê)

Piloto, educadores reais, juízes reais e estudo de impacto dependem de parceria e de autorizações
éticas e legais — rota em [plano_piloto.md](plano_piloto.md). Resíduo de falso positivo do sinal por
eixo, vindo da calibração conjunta de todas as escolas, registrado como próximo passo técnico.
