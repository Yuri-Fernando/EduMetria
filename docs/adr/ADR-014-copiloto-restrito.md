# ADR-014 — Copiloto restrito, determinístico por padrão, LLM local opcional

**Status:** aceito (2026-09-29). Complementa o ADR-009.

**Decisão.** O copiloto responde só por ferramentas em allowlist que leem artefatos já calculados; cita a fonte; abstém-se sem
evidência. Antes de responder, aplica guarda em camadas: regras locais (injeção, dado individual, gabarito, escola fora do escopo,
atribuição causal) + AegisLLM `inspect_input` (injeção direta e indireta nos documentos) + Themis `prompt_security.scan`.
LLM é opcional (`EDUMETRIA_COPILOT_LLM=ollama:<modelo>`, local e gratuito) e só reescreve texto; a reescrita é descartada se trouxer
número que não esteja nos dados das ferramentas.

**Evidência.** `configs/copilot_eval.yaml` (20 casos) → acurácia 100%, recusa de ataques 100%, falsa recusa 0%.
**Limite:** dataset escrito pelo mesmo autor — mede conformidade à especificação, não robustez adversarial real.
