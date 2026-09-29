# ADR-002 — R/mirt como referência; Python para produto, dados e predição

**Status:** aceito, com adaptação (2026-09-28)

**Decisão original.** R + mirt no worker de calibração; Python no produto.

**Adaptação.** A PoC tem um motor nativo em Python (MML-EM Bock–Aitkin, `src/edumetria/irt/estimation.py`) para rodar sem dependência de R. O mirt continua sendo a **referência**: `r/fit_irt.R` + `tests/statistical/test_recovery_and_parity.py` comparam logLik, parâmetros, EAP e SE.

**Evidência (execução real em 2026-09-28, mirt 1.47, R 4.6.1):** 2PL 2000×24 → |Δa| ≤ 5,4e-4, |Δb| ≤ 3,5e-4, |ΔlogLik| ≈ 1e-4, |ΔEAP| ≤ 3,4e-4, SE (crossprod) com diferença relativa ≤ 3e-4; GRM 2000×12 → |Δa| ≤ 8,6e-4, |Δb| ≤ 1,2e-3.

**Consequências.** Se o R não estiver disponível, os testes de paridade são pulados (e isso aparece no relatório de testes), mas nunca substituídos por outro método com o mesmo nome.
