"""Linking de escalas entre calibrações independentes (seção 10.5 do plano).

Calibrações separadas (ex.: onda 1 e onda 2) ficam cada uma em sua própria
escala θ~N(0,1) da população calibrada. Para comparar, é preciso uma
transformação θ* = A·θ + B estimada nos itens âncora comuns:

- mean-mean:   A = média(a_ref)/média(a_new);          B = média(b_ref) − A·média(b_new)
- mean-sigma:  A = dp(b_ref)/dp(b_new);                 B = média(b_ref) − A·média(b_new)
- Stocking-Lord: minimiza a diferença das curvas características do TESTE
  de âncoras ao longo de θ (critério de função característica).
- Haebara: idem, mas soma as diferenças item a item.

Parâmetros transformados: a* = a/A, b* = A·b + B.
Erro de linking: bootstrap sobre as âncoras (reamostra itens âncora) — a
incerteza vem da escolha/estabilidade das âncoras, não só dos respondentes.
Âncoras instáveis (drift) são detectadas pelo resíduo |b*_new − b_ref| e
tratadas por decisão humana (ADR-008), nunca descartadas automaticamente.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize

from edumetria.irt.models import logistic

GRID = np.linspace(-4, 4, 41)
WEIGHTS = np.exp(-GRID**2 / 2) / np.exp(-GRID**2 / 2).sum()


def _tcc(a, b, theta):
    return logistic(a[None, :] * (theta[:, None] - b[None, :]))


def mean_mean(a_ref, b_ref, a_new, b_new) -> tuple[float, float]:
    A = float(np.mean(a_new) / np.mean(a_ref))  # a* = a/A deve igualar a_ref ⇒ A = mean(a_new)/mean(a_ref)
    B = float(np.mean(b_ref) - A * np.mean(b_new))
    return A, B


def mean_sigma(a_ref, b_ref, a_new, b_new) -> tuple[float, float]:
    A = float(np.std(b_ref, ddof=1) / np.std(b_new, ddof=1))
    B = float(np.mean(b_ref) - A * np.mean(b_new))
    return A, B


def _characteristic(method: str, a_ref, b_ref, a_new, b_new) -> tuple[float, float]:
    P_ref = _tcc(a_ref, b_ref, GRID)

    def loss(x):
        A, B = x
        if A <= 0.05:
            return 1e6
        P_new = _tcc(a_new / A, A * b_new + B, GRID)
        if method == "stocking_lord":
            return float(np.sum(WEIGHTS * (P_ref.sum(1) - P_new.sum(1)) ** 2))
        return float(np.sum(WEIGHTS[:, None] * (P_ref - P_new) ** 2))

    x0 = mean_sigma(a_ref, b_ref, a_new, b_new)
    res = optimize.minimize(loss, x0, method="Nelder-Mead", options={"xatol": 1e-7, "fatol": 1e-10, "maxiter": 4000})
    return float(res.x[0]), float(res.x[1])


def stocking_lord(a_ref, b_ref, a_new, b_new) -> tuple[float, float]:
    return _characteristic("stocking_lord", a_ref, b_ref, a_new, b_new)


def haebara(a_ref, b_ref, a_new, b_new) -> tuple[float, float]:
    return _characteristic("haebara", a_ref, b_ref, a_new, b_new)


METHODS = {"mean_mean": mean_mean, "mean_sigma": mean_sigma, "stocking_lord": stocking_lord, "haebara": haebara}


def link(ref: pd.DataFrame, new: pd.DataFrame, anchors: list[str], method: str = "stocking_lord",
         n_boot: int = 200, seed: int = 0) -> dict:
    """``ref``/``new``: DataFrames com colunas item, a, b. Retorna A, B, erro de
    linking (bootstrap nas âncoras) e diagnóstico de drift por âncora."""
    r = ref.set_index("item").loc[anchors]
    n = new.set_index("item").loc[anchors]
    fn = METHODS[method]
    A, B = fn(r["a"].to_numpy(), r["b"].to_numpy(), n["a"].to_numpy(), n["b"].to_numpy())
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(anchors), len(anchors))
        if len(set(idx)) < 3:
            continue
        boots.append(fn(r["a"].to_numpy()[idx], r["b"].to_numpy()[idx], n["a"].to_numpy()[idx], n["b"].to_numpy()[idx]))
    boots = np.array(boots)
    b_star = A * n["b"].to_numpy() + B
    resid = b_star - r["b"].to_numpy()
    drift = pd.DataFrame({"item": anchors, "b_ref": r["b"].to_numpy(), "b_new_linked": b_star, "residual": resid})
    z = (resid - resid.mean()) / (resid.std(ddof=1) or 1.0)
    drift["flag_unstable"] = np.abs(z) > 2.5
    # erro de linking no θ: dp bootstrap da transformação de θ = 0 e θ = ±1
    theta_pts = np.array([-1.0, 0.0, 1.0])
    se_theta = (boots[:, :1] * theta_pts[None, :] + boots[:, 1:2]).std(axis=0, ddof=1) if len(boots) > 2 else [np.nan] * 3
    return {"method": method, "A": A, "B": B, "A_se": float(boots[:, 0].std(ddof=1)), "B_se": float(boots[:, 1].std(ddof=1)),
            "linking_error_theta": dict(zip(["-1", "0", "+1"], map(float, se_theta))),
            "n_anchors": len(anchors), "drift": drift, "n_boot_effective": int(len(boots))}


def transform(params: pd.DataFrame, A: float, B: float) -> pd.DataFrame:
    out = params.copy()
    out["a"] = params["a"] / A
    out["b"] = A * params["b"] + B
    return out


def transform_theta(theta, A: float, B: float):
    return A * np.asarray(theta, dtype=float) + B
