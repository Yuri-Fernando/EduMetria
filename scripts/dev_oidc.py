#!/usr/bin/env python
"""Emissor OIDC LOCAL para desenvolvimento e testes (sem IdP externo, sem custo).

    python scripts/dev_oidc.py init  --dir runs/oidc
    python scripts/dev_oidc.py token --dir runs/oidc --sub psi-ana --role psychometrician --tenant demo-tenant

Gera par RSA (privada fica só em ``runs/oidc`` — ignorado pelo Git), publica
``jwks.json`` e emite tokens RS256 com os claims que a API espera. Em produção,
o IdP institucional (Keycloak, Azure AD, Google Workspace…) substitui este script.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.local.edumetria"
AUDIENCE = "edumetria-api"


def init(d: Path, kid: str = "dev-key-1") -> dict:
    d.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (d / "private.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                      serialization.NoEncryption()))
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    jwks = {"keys": [jwk]}
    (d / "jwks.json").write_text(json.dumps(jwks, indent=2), encoding="utf-8")
    (d / "kid").write_text(kid, encoding="utf-8")
    return jwks


def mint(d: Path, sub: str, role: str, tenant: str, schools: list[str] | None = None, ttl: int = 3600,
         audience: str = AUDIENCE, issuer: str = ISSUER, extra: dict | None = None) -> str:
    key = serialization.load_pem_private_key((d / "private.pem").read_bytes(), password=None)
    now = int(time.time())
    claims = {"iss": issuer, "aud": audience, "sub": sub, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex,
              "edumetria_role": role, "edumetria_tenant": tenant, "edumetria_schools": schools or []}
    claims.update(extra or {})
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": (d / "kid").read_text(encoding="utf-8")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "token"])
    ap.add_argument("--dir", default="runs/oidc")
    ap.add_argument("--sub", default="psi-ana")
    ap.add_argument("--role", default="psychometrician")
    ap.add_argument("--tenant", default="demo-tenant")
    ap.add_argument("--schools", nargs="*", default=[])
    a = ap.parse_args()
    d = Path(a.dir)
    if a.cmd == "init":
        init(d)
        print(f"JWKS em {d / 'jwks.json'} · OIDC_ISSUER={ISSUER} · OIDC_AUDIENCE={AUDIENCE}")
    else:
        print(mint(d, a.sub, a.role, a.tenant, a.schools))
