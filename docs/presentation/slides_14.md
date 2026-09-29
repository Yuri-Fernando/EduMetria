# Apresentação — conteúdo de 14 slides

1. **EduMetria** — infraestrutura de medição e evidências para apoiar trajetórias escolares. Projeto autoral experimental.
2. **O problema de decisão** — frequência e questionários não viram evidência válida automaticamente. Visual: mesmo θ, incertezas diferentes (par real do run S2).
3. **O que a PoC testa** — H1–H6; sintético × real. H1 e H2 testados em Monte Carlo; H3 testado e **não confirmado** nesta simulação (B2 ≈ B1); H4 coberto por manifesto e testes; H5–H6 exigem piloto.
4. **Encaixe no ecossistema** — núcleo novo; adapters Themis/Argus `unverified`, Aegis `disabled`.
5. **Matriz e ciclo de itens** — blueprint, rubrica, juízes (simulados), revisão; B02 como caso de desalinhamento.
6. **Motor de medição** — TCT + 2PL/GRM + EAP; paridade com mirt (|Δ| < 1,2e-3).
7. **Validade e precisão** — mapa de evidências por seção, sem "score de validade".
8. **Equidade e comparabilidade** — DIF condicionado; poder de 97% e falso positivo de 0,6% (Monte Carlo, N=2000).
9. **Do escore ao acompanhamento** — janela temporal, censura, bloqueio de vazamento, capacidade, revisão humana.
10. **Arquitetura e contratos** — API + worker + SQLite (PostgreSQL no piloto), manifesto com hashes.
11. **Observabilidade** — logs JSON redigidos, métricas com labels fechados, traceparent, falha tratada.
12. **Demonstração e evidências** — tabela de runs efetivamente executados (README → Resultados).
13. **Piloto e governança** — entrevistas cognitivas, juízes reais, CFA/invariância, LGPD/ANPD, comitê de ética.
14. **Contribuição e próximos passos** — engenharia demonstrada; evidência de campo ainda necessária.

Perguntas de banca: ver seção 30 do plano mestre (`docs/plano/`).
