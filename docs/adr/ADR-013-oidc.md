# ADR-013 — Autenticação OIDC (JWT RS256 + JWKS) com emissor local para desenvolvimento

**Status:** aceito (2026-09-29).

**Decisão.** `EDUMETRIA_AUTH_MODE=oidc` valida tokens RS256 contra JWKS (arquivo local ou URL do IdP), exigindo `iss`, `aud`, `exp`,
`iat`, `sub` e os claims `edumetria_tenant`/`edumetria_role`. `alg` diferente de RS256 (inclusive `none`) é rejeitado. Para
desenvolvimento e testes sem custo, `scripts/dev_oidc.py` gera chaves, JWKS e tokens. O modo demo (tokens fixos) continua existindo só
para demonstração local.

**Consequências.** Nenhum IdP externo foi contratado; a integração com um IdP institucional real (Keycloak/Azure AD/Google) é troca de
configuração (`OIDC_JWKS_URL`, `OIDC_ISSUER`, `OIDC_AUDIENCE`).
