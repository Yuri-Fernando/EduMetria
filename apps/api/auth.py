"""Autenticação da API: modo demo (tokens fixos) ou OIDC (JWT RS256 + JWKS).

``EDUMETRIA_AUTH_MODE=oidc`` exige:
- ``OIDC_ISSUER`` e ``OIDC_AUDIENCE`` (validados no token);
- ``OIDC_JWKS_FILE`` (JWKS local) ou ``OIDC_JWKS_URL`` (IdP institucional).
Claims usados (namespace próprio, emitidos pelo IdP):
``sub`` → user_id; ``edumetria_tenant``; ``edumetria_role``; ``edumetria_schools``.
Rejeita: assinatura inválida, ``alg`` diferente de RS256 (inclui ``none``),
issuer/audience errados, token expirado ou sem ``exp``/claims obrigatórios.
Identidade continua vindo SÓ do token — nunca do corpo.
Para desenvolvimento sem IdP externo: ``scripts/dev_oidc.py`` gera chaves,
JWKS e tokens (emissor local; nenhum serviço pago).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import jwt
import yaml

from edumetria.registry.store import Actor

ROOT = Path(__file__).resolve().parents[2]
ROLES = {"psychometrician", "coordinator", "teacher", "auditor", "author", "judge"}


class AuthError(Exception):
    pass


@lru_cache(maxsize=1)
def _demo_users() -> dict:
    return yaml.safe_load((ROOT / "configs" / "demo_users.yaml").read_text(encoding="utf-8"))["users"]


def _jwks_client():
    url = os.environ.get("OIDC_JWKS_URL")
    if url:
        return jwt.PyJWKClient(url, cache_keys=True)
    return None


@lru_cache(maxsize=4)
def _jwks_from_file(path: str) -> jwt.PyJWKSet:
    return jwt.PyJWKSet.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _signing_key(token: str):
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256":
        raise AuthError("algoritmo não permitido")
    client = _jwks_client()
    if client is not None:
        return client.get_signing_key_from_jwt(token).key
    path = os.environ.get("OIDC_JWKS_FILE")
    if not path:
        raise AuthError("OIDC sem JWKS configurado")
    kid = header.get("kid")
    for k in _jwks_from_file(path).keys:
        if k.key_id == kid:
            return k.key
    raise AuthError("chave de assinatura desconhecida (kid)")


def verify_oidc(token: str) -> Actor:
    try:
        claims = jwt.decode(token, _signing_key(token), algorithms=["RS256"],
                            audience=os.environ["OIDC_AUDIENCE"], issuer=os.environ["OIDC_ISSUER"],
                            options={"require": ["exp", "iat", "sub", "iss", "aud"]}, leeway=30)
    except (jwt.PyJWTError, KeyError) as exc:
        raise AuthError(f"token inválido: {type(exc).__name__}") from exc
    role = claims.get("edumetria_role")
    tenant = claims.get("edumetria_tenant")
    if role not in ROLES or not tenant:
        raise AuthError("claims de autorização ausentes ou inválidos")
    return Actor(claims["sub"], tenant, role, frozenset(claims.get("edumetria_schools", [])))


def authenticate(authorization: str | None) -> Actor:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("não autenticado")
    token = authorization.removeprefix("Bearer ").strip()
    mode = os.environ.get("EDUMETRIA_AUTH_MODE", "demo")
    if mode == "oidc":
        return verify_oidc(token)
    u = _demo_users().get(token)
    if not u:
        raise AuthError("token inválido")
    return Actor(u["user_id"], u["tenant"], u["role"], frozenset(u.get("schools", [])))
