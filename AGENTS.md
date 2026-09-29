# AGENTS.md — instruções para agentes de desenvolvimento

## Comandos (existem e foram executados)

```bash
export PYTHONPATH=src                      # Windows PowerShell: $env:PYTHONPATH="src"
python -m pytest -q                        # suíte completa (paridade R pulada se não houver Rscript+mirt)
python -m pytest -q -m r_parity            # exige EDUMETRIA_RSCRIPT e EDUMETRIA_R_LIBS
python -m edumetria.cli analyze --scenario s2
python -m edumetria.cli recovery-study --reps 100 --dif-reps 50
python -m edumetria.cli benchmark
python scripts/p2_studies.py
python scripts/build_notebook.py          # regenera e executa o notebook end-to-end
docker compose --profile core up -d       # PostgreSQL + RLS (testes de Store rodam nos dois backends)
```

## Limites inegociáveis (seção 31 do plano mestre)

- Dados sintéticos nunca apresentados como reais; toda saída carrega `data_origin`.
- Nenhuma métrica em README/dashboard/apresentação sem run ou artefato que a produza.
- Nenhuma decisão de alto impacto automatizada; revisão humana persistente (ADR-007).
- Missing nunca vira zero; calibrações independentes nunca são a mesma escala.
- Identidade/tenant/role nunca vêm do corpo (contratos com `extra="forbid"`).
- Nada executa string arbitrária do usuário (R só via scripts fixos + allowlist).
- Nunca alterar limiar ou seed para melhorar métrica; registrar falhas no denominador.

## Contratos

- `src/edumetria/domain/contracts.py` — entrada/saída da API e `PsychometricEvidenceReport`.
- Mudança de contrato → incrementar `SCHEMA_VERSION` e registrar no CHANGELOG.

## Definição de pronto

Testes relevantes executados, comando + código de saída registrados no WORKLOG, CHANGELOG atualizado,
README diferenciando implementado × testado × planejado × dependente de piloto.

## Histórico e versionamento

- `CHANGELOG.md` — documento mestre de histórico (Keep a Changelog + SemVer).
- `ROADMAP.md` — escopo por fase; nada é descartado, só sequenciado.
- `WORKLOG.md` — log cronológico por sessão.
- `docs/plano/` — plano mestre original (fonte da especificação; não editar — versionar como `_v2` se mudar).
