# Plano de validação social e piloto responsável (proposta — nada executado)

> Rota testável, não execução. **Não há escola, rede ou ONG parceira.** Nenhuma entrevista, coleta ou
> piloto foi realizado. Base: [`docs/impact/preregistro_template.md`](../impact/preregistro_template.md)
> e `reports/p2/impact_design.json` (premissas de planejamento).

## Etapa 0 — Parceria (pré-requisito)

- Mapear escola, rede municipal ou ONG educacional potencial; registrar contatos sem afirmar parceria.
- Formalizar papéis antes de qualquer dado: quem é **controlador** e quem é **operador** (LGPD),
  finalidade, base legal, prazo de retenção e canal de contestação.

## Etapa 1 — Entrevistas exploratórias com educadores adultos (sem dados de estudantes)

| Item | Proposta |
|---|---|
| Participantes | 8–12 professores e coordenadores (adultos), recrutamento voluntário |
| Consentimento | termo de consentimento livre e esclarecido; sem gravação sem autorização |
| Material | o painel com **dados sintéticos** (S12) e o roteiro de 3 minutos |
| Perguntas | o problema descrito existe? o painel ajuda a decidir? a incerteza é compreendida? a revisão humana atrapalha ou protege? |
| Ética | verificar com comitê de ética se o protocolo exige submissão (pesquisa com seres humanos) |

**Métricas sugeridas (não são resultados):**

- **A — Usabilidade:** tempo para concluir a tarefa guiada ("encontre o eixo com sinal e encaminhe"),
  taxa de conclusão, erros de interpretação (ex.: ler "dentro da incerteza" como "abaixo").
- **B — Valor pedagógico:** concordância entre especialistas sobre a utilidade do sinal; adequação das
  sugestões dos playbooks; proporção de casos revisados versus encaminhados.
- **C — Compreensão da incerteza:** acerto em perguntas do tipo "esta diferença permite concluir?".

## Etapa 2 — Antes de qualquer dado real de estudante

- Comitê de ética e, quando aplicável, autorização da secretaria de educação.
- RIPD/DPIA (relatório de impacto à proteção de dados); proteção reforçada de crianças e adolescentes
  (art. 14 da LGPD; Enunciado ANPD 1/2023 orienta o desenho, sem parecer jurídico).
- Consentimento/autorização dos responsáveis quando exigido — o policy engine real do ThemisAI já
  **nega** uso com menores sem esse registro (POL-003, integração verificada).
- Revisão dos itens por especialistas reais e entrevistas cognitivas (hoje os itens são autorais).

## Etapa 3 — Qualidade técnica com dados reais (se as etapas anteriores permitirem)

- **C — Qualidade técnica:** calibração, intervalos, DIF com grupos reais definidos com a rede,
  falsos positivos do sinal por eixo, drift entre aplicações, ausências.
- **D — Equidade:** disparidades entre grupos só quando a avaliação for válida, legal e eticamente
  viável; nunca ranking por atributo sensível.

## Etapa 4 — Impacto (desenho definido antes de coletar)

- Desfecho primário e comparador congelados no pré-registro (template existente: ensaio por clusters,
  randomização por escola).
- Premissas atuais (`reports/p2/impact_design.json`): com ICC 0,05 e 100 estudantes por escola,
  MDES de 0,32 dp com 20 escolas e 50 escolas para 0,20 dp; poder simulado de 56% para −3 p.p. com
  20 escolas. **Um piloto pequeno não detectaria efeito realista** — ele serve para usabilidade e
  segurança, não para provar impacto.
- **E — Impacto:** nunca confundir correlação com efeito causal; nunca publicar "aumento de X%" sem
  desenho que sustente.

## O que não será feito

Coleta de dados de menores sem as autorizações acima; integração com sistemas escolares reais nesta
fase; predição de evasão como produto; decisão automatizada sobre estudantes.
