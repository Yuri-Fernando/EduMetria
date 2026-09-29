# ADR-015 — Trilha B com microdados públicos do ENEM 2023

**Status:** aceito (2026-09-29).

**Contexto.** A trilha B do plano previa dados públicos do Inep. Os microdados do Saeb não trazem resposta item a item com
parâmetros; os do **ENEM** trazem respostas por item, gabarito e os **parâmetros oficiais de TRI (a, b, c)** de cada item.

**Decisão.** Validar o motor em dados reais com `scripts/trilha_b_enem.py`: um caderno de Matemática, amostra de 20 mil participantes,
2PL nativo e 3PL (mirt), comparação com parâmetros oficiais (após transformação linear, porque as escalas diferem) e com a nota oficial.
Nenhum microdado é versionado — só agregados e parâmetros de item (públicos).

**Resultado (execução real).** θ 3PL × nota oficial: r = 0,994; b × b oficial: r = 0,981 (sem o item degenerado MT147) e Spearman 0,992.
**Limite:** não reproduz a nota oficial (o Inep usa procedimento, população e escala próprios); o ENEM não é o público-alvo (6º ano).
