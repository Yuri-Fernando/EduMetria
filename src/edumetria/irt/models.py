"""Funções de resposta ao item (seção 10), convenção logística D=1.

2PL:  P(X=1 | θ) = logistic(a (θ − b))  ≡  logistic(a θ + d),  d = −a b.
GRM:  P(X ≥ k | θ) = logistic(a (θ − b_k)),  k = 1..K−1, com b_1 < b_2 < ...
A conversão d ↔ b vale apenas no caso unidimensional.
"""

from __future__ import annotations

import numpy as np


def logistic(x: np.ndarray | float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def prob_2pl(theta: np.ndarray | float, a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    """Probabilidade de acerto. ``theta`` (n,) × itens (j,) → (n, j) por broadcast."""
    theta = np.asarray(theta, dtype=float)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if theta.ndim == 1 and a.ndim == 1:
        return logistic(a[None, :] * (theta[:, None] - b[None, :]))
    return logistic(a * (theta - b))


def d_from_b(a, b):
    return -np.asarray(a, dtype=float) * np.asarray(b, dtype=float)


def b_from_d(a, d):
    a = np.asarray(a, dtype=float)
    if np.any(a == 0):
        raise ValueError("b indefinido para a = 0 (item sem discriminação)")
    return -np.asarray(d, dtype=float) / a


def info_2pl(theta, a, b) -> np.ndarray:
    """Informação de Fisher do item 2PL: a² P (1 − P)."""
    p = prob_2pl(theta, a, b)
    a = np.asarray(a, dtype=float)
    return (a**2) * p * (1 - p)


def total_information(theta, a, b) -> np.ndarray:
    """Informação do teste sob independência local = soma das informações dos itens."""
    return info_2pl(theta, a, b).sum(axis=-1)


def se_from_information(info: np.ndarray) -> np.ndarray:
    """SE(θ) ≈ 1/√I(θ). Aproximação baseada em informação — não é a incerteza
    posterior EAP (posterior_sd)."""
    info = np.asarray(info, dtype=float)
    with np.errstate(divide="ignore"):
        return np.where(info > 0, 1.0 / np.sqrt(info), np.inf)


def grm_cumulative(theta, a: float, b: np.ndarray) -> np.ndarray:
    """P(X ≥ k | θ) para k = 1..K−1 → matriz (n, K−1)."""
    theta = np.atleast_1d(np.asarray(theta, dtype=float))
    b = np.asarray(b, dtype=float)
    return logistic(a * (theta[:, None] - b[None, :]))


def grm_category_probs(theta, a: float, b: np.ndarray) -> np.ndarray:
    """Probabilidades por categoria (0..K−1) → (n, K). Soma 1 por linha;
    exige limiares ordenados (b_1 < ... < b_{K−1})."""
    b = np.asarray(b, dtype=float)
    if np.any(np.diff(b) <= 0):
        raise ValueError("limiares GRM devem ser estritamente crescentes")
    cum = grm_cumulative(theta, a, b)
    n = cum.shape[0]
    upper = np.hstack([np.ones((n, 1)), cum])
    lower = np.hstack([cum, np.zeros((n, 1))])
    return upper - lower


def grm_information(theta, a: float, b: np.ndarray) -> np.ndarray:
    """Informação do item GRM (Samejima): Σ_k (P*'_k − P*'_{k+1})² / P_k."""
    theta = np.atleast_1d(np.asarray(theta, dtype=float))
    cum = grm_cumulative(theta, a, b)
    n = cum.shape[0]
    pstar = np.hstack([np.ones((n, 1)), cum, np.zeros((n, 1))])
    dstar = a * pstar * (1 - pstar)
    probs = pstar[:, :-1] - pstar[:, 1:]
    num = (dstar[:, :-1] - dstar[:, 1:]) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(probs > 1e-12, num / probs, 0.0)
    return terms.sum(axis=1)
