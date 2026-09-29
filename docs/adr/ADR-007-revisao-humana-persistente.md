# ADR-007 — Revisão humana persistente para publicação e intervenções

**Status:** aceito. Liberação de calibração e aprovação de caso são transações auditadas (ator, versão, motivo), com controle otimista de versão (409 para versão antiga), segregação de funções (autor não aprova o próprio caso) e sobrevivência a reinício. `confirmed=True` no corpo não é aceito.
