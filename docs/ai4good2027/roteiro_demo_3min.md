# Roteiro de demonstração — 3 minutos (EduMetria Social)

> Derivado de [`docs/presentation/roteiro_demo_8min.md`](../presentation/roteiro_demo_8min.md), que
> continua valendo para público técnico. Sem live coding: painel já aberto no modo **Educador**, run
> S12 de `reports/demo_runs/`, API em modo demo. Todos os números citados vêm desse run e de
> `reports/ai4good2027/` (dados sintéticos). Se algo falhar ao vivo, usar as capturas em
> `docs/images/ai4good_*.png` **e dizer que são capturas**.

| Tempo | Bloco | O que mostrar | Fala-guia |
|---|---|---|---|
| 0:00–0:25 | **Dor social** | aba *1 · O problema* (aviso sintético visível) | "Uma coordenadora tem notas e faltas de 100 alunos e pouco tempo. A média não diz onde agir nem o quanto confiar no número." |
| 0:25–0:50 | **O que faz / o que não faz** | mesmas colunas "faz" × "não faz" | "Ele mede com margem de erro, aponta sinais e leva tudo para revisão humana. Não classifica alunos, não decide atendimento, não usa dados reais de menores." |
| 0:50–1:30 | **Escola fictícia: medida e incerteza** | aba *2 · Escola fictícia*, SCH01 | "Três coisas separadas: proficiência com intervalo — quantos estão claramente abaixo do corte ilustrativo e quantos o sistema *não consegue* afirmar; acertos por eixo comparados com o que a própria escola faria esperar; faltas como registro observado." Apontar *Dados e gráficos* fora da margem e os outros eixos dentro dela. |
| 1:30–1:50 | **Risco preditivo** | cartão de risco | "O modelo de previsão foi testado e acrescentar a proficiência não melhorou a previsão de forma comprovada. Por isso ele não gera prioridade — dizer isso também é transparência." |
| 1:50–2:15 | **Revisão humana** | aba *3* → "Encaminhar"; aba *4* → checklist e aprovação por outra pessoa | "Quem propõe não aprova. A revisora marca o checklist de interpretação e justifica. Tudo fica na auditoria." |
| 2:15–2:40 | **Evidências e limites** | aba *5 · Como chegamos aqui* (tabela do estudo Monte Carlo) e *6 · Transparência* | "Em simulação com gabarito conhecido, o painel encontra dificuldades plantadas e quase não inventa sinal; efeitos pequenos ele não vê — com ~100 alunos isso é limite real. O motor também foi comparado com o ENEM 2023." |
| 2:40–3:00 | **Próximo passo** | `docs/ai4good2027/plano_piloto.md` | "Falta o principal: educadores reais. O próximo passo é ouvir professores com cuidado ético, antes de qualquer dado de estudante." |

**Números para citar** (conferir no run antes de apresentar): ver
[evidence_matrix.md](evidence_matrix.md). Não citar nenhum número que não esteja lá.

**Perguntas prováveis**

- *"Funciona em escola real?"* — Não sabemos; não houve piloto. Está documentado como a próxima etapa.
- *"Por que não prever evasão?"* — Porque o teste mostrou que a proficiência não melhorou a previsão
  nesta simulação, e porque predição de evasão sem validação pode estigmatizar estudantes.
- *"E se o sinal estiver errado?"* — Cada ponto lista o que pode estar errado, e nada acontece sem
  revisão humana; o estudo mede a taxa de falso positivo.
