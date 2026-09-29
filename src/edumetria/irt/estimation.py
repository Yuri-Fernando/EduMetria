"""Estimação por Máxima Verossimilhança Marginal via EM (Bock & Aitkin, 1981).

Motor nativo Python da PoC. O plano (ADR-002) prevê R/mirt como motor de
referência; os scripts em ``r/`` produzem a mesma parametrização e o teste
``tests/statistical/test_r_parity.py`` compara os dois quando Rscript + mirt
estão disponíveis. Não é regressão rebatizada: é TRI com integração sobre a
distribuição latente por quadratura.

Identificação: θ ~ N(0, 1) na população de referência (escala interna).
Parametrização exportada: slope-intercept (a, d) e tradicional (a, b), D = 1.
Missing (NaN) é tratado como não observado — nunca como zero.

Erros-padrão: produto cruzado dos escores individuais (aproximação XPD,
equivalente conceitual a ``SE.type = "crossprod"`` no mirt). Não é a matriz
de informação observada completa; documentado como aproximação.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import optimize, stats
from scipy.special import logsumexp

from edumetria.irt.models import logistic

LOW_A, HIGH_A, EXTREME_B = 0.2, 4.0, 4.0


@dataclass
class QuadratureGrid:
    nodes: np.ndarray
    log_weights: np.ndarray

    @classmethod
    def normal(cls, n_points: int = 61, limit: float = 6.0) -> "QuadratureGrid":
        nodes = np.linspace(-limit, limit, n_points)
        w = stats.norm.pdf(nodes)
        w = w / w.sum()
        return cls(nodes=nodes, log_weights=np.log(w))


@dataclass
class IRTFitResult:
    model_family: str
    params: pd.DataFrame
    loglik: float
    iterations: int
    converged: bool
    warnings: list[str] = field(default_factory=list)
    n_persons: int = 0
    n_items: int = 0
    n_quad: int = 61
    se_method: str = "crossprod"

    @property
    def n_free_params(self) -> int:
        if self.model_family == "1pl":
            return 1 + self.n_items
        if self.model_family == "grm":
            n_thr = int(self.params.filter(like="d").notna().sum().sum())
            return self.n_items + n_thr
        return 2 * self.n_items

    @property
    def aic(self) -> float:
        return -2 * self.loglik + 2 * self.n_free_params

    @property
    def bic(self) -> float:
        return -2 * self.loglik + np.log(self.n_persons) * self.n_free_params

    def to_dict(self) -> dict:
        return {
            "model_family": self.model_family,
            "loglik": self.loglik,
            "aic": self.aic,
            "bic": self.bic,
            "iterations": self.iterations,
            "converged": self.converged,
            "warnings": self.warnings,
            "n_persons": self.n_persons,
            "n_items": self.n_items,
            "n_quad": self.n_quad,
            "se_method": self.se_method,
            "parameterization": "slope-intercept (a, d) e tradicional (a, b); D = 1; θ ~ N(0,1)",
            "params": self.params.to_dict(orient="records"),
        }


# --------------------------------------------------------------------------
# utilitários comuns
# --------------------------------------------------------------------------

def _validate_dichotomous(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    obs = ~np.isnan(X)
    vals = np.unique(X[obs])
    if not set(vals.tolist()) <= {0.0, 1.0}:
        raise ValueError(f"matriz dicotômica deve conter apenas 0/1/NaN; encontrado {vals[:10]}")
    return X


def _posterior(loglik_nodes: np.ndarray, log_weights: np.ndarray) -> tuple[np.ndarray, float]:
    joint = loglik_nodes + log_weights[None, :]
    norm = logsumexp(joint, axis=1)
    post = np.exp(joint - norm[:, None])
    return post, float(norm.sum())


def _item_warnings(a: np.ndarray, b: np.ndarray, names: list[str]) -> list[str]:
    out = []
    for name, ai, bi in zip(names, a, b):
        if ai < 0:
            out.append(f"{name}: discriminação negativa (a={ai:.2f}) — revisar gabarito/redação")
        elif ai < LOW_A:
            out.append(f"{name}: discriminação baixa (a={ai:.2f})")
        elif ai > HIGH_A:
            out.append(f"{name}: discriminação muito alta (a={ai:.2f}) — possível dependência local")
        if np.isfinite(bi) and abs(bi) > EXTREME_B:
            out.append(f"{name}: localização extrema (b={bi:.2f}) — pouca informação na população")
    return out


# --------------------------------------------------------------------------
# 2PL / 1PL
# --------------------------------------------------------------------------

def _loglik_nodes_dich(X0: np.ndarray, O: np.ndarray, a: np.ndarray, d: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    z = nodes[:, None] * a[None, :] + d[None, :]  # (K, J)
    logP = -np.logaddexp(0.0, -z)
    log1mP = -np.logaddexp(0.0, z)
    return X0 @ logP.T + (O - X0) @ log1mP.T  # (n, K)


def fit_2pl(
    X: np.ndarray,
    item_names: list[str] | None = None,
    common_slope: bool = False,
    max_iter: int = 2000,
    tol: float = 1e-4,
    n_quad: int = 61,
) -> IRTFitResult:
    """Ajusta 2PL (ou 1PL com slope comum, ``common_slope=True``) por MML-EM.

    1PL com θ ~ N(0,1) e slope comum é uma reparametrização do Rasch
    (a = 1, variância latente livre): σ_Rasch = a_comum. As parametrizações
    não devem ser comparadas diretamente sem essa conversão.
    """
    X = _validate_dichotomous(X)
    n, J = X.shape
    names = item_names or [f"item_{j + 1:02d}" for j in range(J)]
    O = (~np.isnan(X)).astype(float)
    X0 = np.nan_to_num(X, nan=0.0)
    grid = QuadratureGrid.normal(n_quad)
    th = grid.nodes
    warnings: list[str] = []

    counts = O.sum(axis=0)
    for j in np.where(counts == 0)[0]:
        raise ValueError(f"{names[j]}: nenhum dado observado — remover do ajuste")
    pvals = np.divide(X0.sum(axis=0), counts)
    const = np.where((pvals == 0) | (pvals == 1))[0]
    if const.size:
        raise ValueError(
            "itens constantes não são estimáveis em TRI: " + ", ".join(names[j] for j in const)
        )

    a = np.ones(J)
    d = np.log(np.clip(pvals, 0.02, 0.98) / (1 - np.clip(pvals, 0.02, 0.98)))
    converged = False
    ll = -np.inf
    it = 0
    for it in range(1, max_iter + 1):
        L = _loglik_nodes_dich(X0, O, a, d, th)
        post, ll = _posterior(L, grid.log_weights)
        nk = post.T @ O  # (K, J) respondentes esperados
        rk = post.T @ X0  # (K, J) acertos esperados
        a_old, d_old = a.copy(), d.copy()
        for _ in range(4):  # passos de Newton por ciclo M
            P = logistic(th[:, None] * a[None, :] + d[None, :])
            W = nk * P * (1 - P)
            resid = rk - nk * P
            g_d = resid.sum(axis=0)
            g_a = (resid * th[:, None]).sum(axis=0)
            h_dd = W.sum(axis=0)
            h_ad = (W * th[:, None]).sum(axis=0)
            h_aa = (W * th[:, None] ** 2).sum(axis=0)
            if common_slope:
                # vetor [a, d_1..d_J]: Newton no sistema (J+1)
                H = np.zeros((J + 1, J + 1))
                H[0, 0] = h_aa.sum()
                H[0, 1:] = H[1:, 0] = h_ad
                H[np.arange(1, J + 1), np.arange(1, J + 1)] = h_dd
                g = np.concatenate([[g_a.sum()], g_d])
                step = np.linalg.solve(H + 1e-9 * np.eye(J + 1), g)
                step = np.clip(step, -1.0, 1.0)
                a = a + step[0]
                d = d + step[1:]
            else:
                det = h_aa * h_dd - h_ad**2
                det = np.where(np.abs(det) < 1e-12, 1e-12, det)
                step_a = (h_dd * g_a - h_ad * g_d) / det
                step_d = (h_aa * g_d - h_ad * g_a) / det
                a = a + np.clip(step_a, -1.0, 1.0)
                d = d + np.clip(step_d, -1.0, 1.0)
        delta = max(np.max(np.abs(a - a_old)), np.max(np.abs(d - d_old)))
        if delta < tol:
            converged = True
            break
    if not converged:
        warnings.append(f"EM não convergiu em {max_iter} ciclos (tol={tol}) — não publicar")

    # log-verossimilhança final e erros-padrão por produto cruzado
    L = _loglik_nodes_dich(X0, O, a, d, th)
    post, ll = _posterior(L, grid.log_weights)
    P = logistic(th[:, None] * a[None, :] + d[None, :])
    e_theta = post @ th
    ePk = post @ P
    ethP = post @ (th[:, None] * P)
    g_d = O * (X0 - ePk)
    g_a = O * (X0 * e_theta[:, None] - ethP)
    if common_slope:
        G = np.hstack([g_a.sum(axis=1, keepdims=True), g_d])
    else:
        G = np.empty((n, 2 * J))
        G[:, 0::2] = g_a
        G[:, 1::2] = g_d
    se_a = np.full(J, np.nan)
    se_d = np.full(J, np.nan)
    cov_ad = np.full(J, np.nan)
    try:
        cov = np.linalg.inv(G.T @ G)
        if common_slope:
            se_a[:] = np.sqrt(cov[0, 0])
            se_d = np.sqrt(np.diag(cov)[1:])
            cov_ad = cov[0, 1:]
        else:
            se_a = np.sqrt(np.diag(cov)[0::2])
            se_d = np.sqrt(np.diag(cov)[1::2])
            cov_ad = np.array([cov[2 * j, 2 * j + 1] for j in range(J)])
    except np.linalg.LinAlgError:
        warnings.append("matriz de informação singular — erros-padrão não estimáveis")

    b = -d / a
    db_da = d / a**2
    db_dd = -1 / a
    var_b = db_da**2 * se_a**2 + db_dd**2 * se_d**2 + 2 * db_da * db_dd * cov_ad
    se_b = np.sqrt(np.clip(var_b, 0, None))
    warnings.extend(_item_warnings(a, b, names))

    params = pd.DataFrame(
        {"item": names, "a": a, "d": d, "b": b, "se_a": se_a, "se_d": se_d, "se_b": se_b,
         "n_obs": counts.astype(int)}
    )
    return IRTFitResult(
        model_family="1pl" if common_slope else "2pl",
        params=params,
        loglik=ll,
        iterations=it,
        converged=converged,
        warnings=warnings,
        n_persons=n,
        n_items=J,
        n_quad=n_quad,
    )


# --------------------------------------------------------------------------
# GRM (Samejima)
# --------------------------------------------------------------------------

def _grm_d_from_u(u: np.ndarray) -> np.ndarray:
    """d_1 = u_0; d_k = d_{k-1} − exp(u_k): garante d decrescente → b crescente (a>0)."""
    d = np.empty(len(u))
    d[0] = u[0]
    for k in range(1, len(u)):
        d[k] = d[k - 1] - np.exp(u[k])
    return d


def _grm_u_from_d(d: np.ndarray) -> np.ndarray:
    u = np.empty(len(d))
    u[0] = d[0]
    u[1:] = np.log(np.maximum(-np.diff(d), 1e-6))
    return u


def _grm_logprobs(a: float, d: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    """log P(X = c | θ_k) → (K, C)."""
    cum = logistic(a * nodes[:, None] + d[None, :])  # (K, C-1)
    K = len(nodes)
    upper = np.hstack([np.ones((K, 1)), cum])
    lower = np.hstack([cum, np.zeros((K, 1))])
    return np.log(np.clip(upper - lower, 1e-300, None))


def fit_grm(
    X: np.ndarray,
    n_categories: int | None = None,
    item_names: list[str] | None = None,
    max_iter: int = 1000,
    tol: float = 1e-4,
    n_quad: int = 61,
) -> IRTFitResult:
    """Graded Response Model por MML-EM. Categorias 0..C−1; NaN = não observado.

    Categoria vazia gera erro explícito (colapsar exige nova versão de regra,
    nunca ajuste silencioso); categoria rara gera warning.
    """
    X = np.asarray(X, dtype=float)
    n, J = X.shape
    names = item_names or [f"item_{j + 1:02d}" for j in range(J)]
    obs = ~np.isnan(X)
    C = int(n_categories or (np.nanmax(X) + 1))
    grid = QuadratureGrid.normal(n_quad)
    th = grid.nodes
    warnings: list[str] = []

    onehots = []
    for j in range(J):
        xj = X[obs[:, j], j].astype(int)
        if np.any((xj < 0) | (xj >= C)):
            raise ValueError(f"{names[j]}: categoria fora de 0..{C - 1}")
        freq = np.bincount(xj, minlength=C)
        if np.any(freq == 0):
            raise ValueError(
                f"{names[j]}: categoria vazia {np.where(freq == 0)[0].tolist()} — GRM não identificado; "
                "colapsar exige justificativa e nova versão de regra"
            )
        rare = np.where(freq / freq.sum() < 0.02)[0]
        if rare.size:
            warnings.append(f"{names[j]}: categorias raras {rare.tolist()} (<2%) — limiares instáveis")
        oh = np.zeros((n, C))
        oh[np.where(obs[:, j])[0], xj] = 1.0
        onehots.append(oh)

    # valores iniciais pelas proporções acumuladas marginais
    a = np.ones(J)
    D = np.zeros((J, C - 1))
    for j in range(J):
        freq = onehots[j].sum(axis=0)
        cum = 1 - np.cumsum(freq)[:-1] / freq.sum()
        cum = np.clip(cum, 0.02, 0.98)
        D[j] = np.log(cum / (1 - cum))
        D[j] = np.minimum.accumulate(D[j] - 1e-3 * np.arange(C - 1))

    def loglik_nodes() -> np.ndarray:
        L = np.zeros((n, len(th)))
        for j in range(J):
            lp = _grm_logprobs(a[j], D[j], th)  # (K, C)
            L += onehots[j] @ lp.T
        return L

    converged = False
    ll = -np.inf
    it = 0
    for it in range(1, max_iter + 1):
        post, ll = _posterior(loglik_nodes(), grid.log_weights)
        max_delta = 0.0
        for j in range(J):
            r = post.T @ onehots[j]  # (K, C) contagens esperadas

            def negll(p, r=r):
                return -np.sum(r * _grm_logprobs(p[0], _grm_d_from_u(p[1:]), th))

            p0 = np.concatenate([[a[j]], _grm_u_from_d(D[j])])
            res = optimize.minimize(negll, p0, method="L-BFGS-B",
                                    bounds=[(-6, 6)] + [(None, None)] * (C - 1))
            new_a, new_d = res.x[0], _grm_d_from_u(res.x[1:])
            max_delta = max(max_delta, abs(new_a - a[j]), float(np.max(np.abs(new_d - D[j]))))
            a[j], D[j] = new_a, new_d
        if max_delta < tol:
            converged = True
            break
    if not converged:
        warnings.append(f"EM (GRM) não convergiu em {max_iter} ciclos — não publicar")

    post, ll = _posterior(loglik_nodes(), grid.log_weights)

    # SE por produto cruzado com gradientes numéricos de log P(x|θ_k)
    rows = []
    eps = 1e-5
    for j in range(J):
        p = np.concatenate([[a[j]], D[j]])
        base = _grm_logprobs(p[0], p[1:], th)
        grads = np.empty((len(th), C, len(p)))
        for m in range(len(p)):
            pp = p.copy()
            pp[m] += eps
            if m > 0 and np.any(np.diff(pp[1:]) >= 0):
                pp[m] -= 2 * eps
                grads[:, :, m] = (base - _grm_logprobs(pp[0], pp[1:], th)) / eps
            else:
                grads[:, :, m] = (_grm_logprobs(pp[0], pp[1:], th) - base) / eps
        # g_i = Σ_k post_ik ∂ log P(x_ij | θ_k)
        G = np.einsum("ik,ic,kcm->im", post, onehots[j], grads)
        se = np.full(len(p), np.nan)
        cov = None
        try:
            cov = np.linalg.inv(G.T @ G)
            se = np.sqrt(np.diag(cov))
        except np.linalg.LinAlgError:
            warnings.append(f"{names[j]}: informação singular — SE não estimável")
        b = -D[j] / a[j]
        se_b = np.full(C - 1, np.nan)
        if cov is not None:
            for k in range(C - 1):
                jac = np.zeros(len(p))
                jac[0] = D[j][k] / a[j] ** 2
                jac[1 + k] = -1 / a[j]
                se_b[k] = float(np.sqrt(max(jac @ cov @ jac, 0)))
        row = {"item": names[j], "a": a[j], "se_a": se[0], "n_obs": int(obs[:, j].sum())}
        for k in range(C - 1):
            row[f"d{k + 1}"] = D[j][k]
            row[f"b{k + 1}"] = b[k]
            row[f"se_b{k + 1}"] = se_b[k]
        rows.append(row)
        warnings.extend(_item_warnings(np.array([a[j]]), np.array([b.mean()]), [names[j]]))

    return IRTFitResult(
        model_family="grm",
        params=pd.DataFrame(rows),
        loglik=ll,
        iterations=it,
        converged=converged,
        warnings=warnings,
        n_persons=n,
        n_items=J,
        n_quad=n_quad,
    )


def grm_params_arrays(params: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Extrai (a, B) de um DataFrame de parâmetros GRM."""
    bcols = sorted([c for c in params.columns if c.startswith("b") and c[1:].isdigit()],
                   key=lambda c: int(c[1:]))
    return params["a"].to_numpy(float), params[bcols].to_numpy(float)
