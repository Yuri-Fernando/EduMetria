"""Escores EAP com incerteza posterior (seção 10.4).

- Prior documentado: N(0, 1) na escala interna.
- ``posterior_sd`` NÃO é rotulado como erro-padrão frequentista.
- Intervalo por quantis da posterior (preferido à aproximação ±1,96·sd).
- Sem respostas informativas → ``insufficient_evidence`` e θ ausente
  (nunca a média do prior como medida individual).
- MLE é oferecido só para demonstrar a divergência em padrões extremos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.special import logsumexp

from edumetria.domain.enums import ScoreStatus
from edumetria.irt.estimation import QuadratureGrid, _grm_logprobs
from edumetria.irt.models import logistic, prob_2pl

PRIOR_DESCRIPTION = "N(0, 1) — escala interna EduMetria"


@dataclass
class EAPResult:
    theta: np.ndarray  # NaN quando insuficiente
    posterior_sd: np.ndarray
    q05: np.ndarray
    q95: np.ndarray
    n_answered: np.ndarray
    status: np.ndarray  # ScoreStatus.value

    def to_frame(self, subject_refs: list[str] | None = None) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "theta_eap": self.theta,
                "posterior_sd": self.posterior_sd,
                "q05": self.q05,
                "q95": self.q95,
                "n_answered": self.n_answered,
                "status": self.status,
            }
        )
        if subject_refs is not None:
            df.insert(0, "subject_ref", subject_refs)
        return df


def _summarize(L: np.ndarray, grid: QuadratureGrid, n_answered: np.ndarray) -> EAPResult:
    joint = L + grid.log_weights[None, :]
    post = np.exp(joint - logsumexp(joint, axis=1)[:, None])
    th = grid.nodes
    mean = post @ th
    sd = np.sqrt(np.clip(post @ th**2 - mean**2, 0, None))
    cdf = np.cumsum(post, axis=1)
    q05 = np.array([np.interp(0.05, c, th) for c in cdf])
    q95 = np.array([np.interp(0.95, c, th) for c in cdf])
    insufficient = n_answered == 0
    status = np.where(insufficient, ScoreStatus.INSUFFICIENT_EVIDENCE.value, ScoreStatus.COMPUTED.value)
    for arr in (mean, sd, q05, q95):
        arr[insufficient] = np.nan
    return EAPResult(mean, sd, q05, q95, n_answered.astype(int), status)


def eap_2pl(X: np.ndarray, a: np.ndarray, b: np.ndarray, n_quad: int = 61) -> EAPResult:
    X = np.asarray(X, dtype=float)
    O = (~np.isnan(X)).astype(float)
    X0 = np.nan_to_num(X, nan=0.0)
    grid = QuadratureGrid.normal(n_quad)
    P = prob_2pl(grid.nodes, a, b)  # (K, J)
    P = np.clip(P, 1e-12, 1 - 1e-12)
    L = X0 @ np.log(P).T + (O - X0) @ np.log(1 - P).T
    return _summarize(L, grid, O.sum(axis=1))


def eap_grm(X: np.ndarray, a: np.ndarray, B: np.ndarray, n_quad: int = 61) -> EAPResult:
    X = np.asarray(X, dtype=float)
    n, J = X.shape
    obs = ~np.isnan(X)
    grid = QuadratureGrid.normal(n_quad)
    L = np.zeros((n, len(grid.nodes)))
    for j in range(J):
        d = -a[j] * B[j]
        lp = _grm_logprobs(a[j], d, grid.nodes)  # (K, C)
        idx = np.where(obs[:, j])[0]
        L[idx] += lp[:, X[idx, j].astype(int)].T
    return _summarize(L, grid, obs.sum(axis=1))


def mle_2pl(x: np.ndarray, a: np.ndarray, b: np.ndarray, max_iter: int = 50) -> dict:
    """MLE de θ por Newton-Raphson para um único padrão de respostas.

    Padrões todos corretos/incorretos não têm máximo finito: retorna
    ``diverged=True`` em vez de um número arbitrário.
    """
    x = np.asarray(x, dtype=float)
    obs = ~np.isnan(x)
    xo, ao, bo = x[obs], a[obs], b[obs]
    if xo.size == 0:
        return {"theta": None, "diverged": False, "status": ScoreStatus.INSUFFICIENT_EVIDENCE.value}
    if np.all(xo == 1) or np.all(xo == 0):
        return {"theta": None, "diverged": True, "status": ScoreStatus.NOT_COMPUTED.value,
                "reason": "padrão extremo (todos corretos/incorretos): MLE diverge para ±∞"}
    theta = 0.0
    for _ in range(max_iter):
        p = logistic(ao * (theta - bo))
        g = np.sum(ao * (xo - p))
        h = -np.sum(ao**2 * p * (1 - p))
        step = g / h
        theta -= np.clip(step, -1, 1)
        if abs(step) < 1e-6:
            break
    info = np.sum(ao**2 * p * (1 - p))
    return {"theta": float(theta), "se": float(1 / np.sqrt(info)), "diverged": False,
            "status": ScoreStatus.COMPUTED.value}


# --------------------------------------------------------------------------
# diagnósticos
# --------------------------------------------------------------------------

def q3_matrix(X: np.ndarray, a: np.ndarray, b: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Q3 de Yen: correlação entre resíduos x_ij − P_j(θ̂_i) (dependência local)."""
    X = np.asarray(X, dtype=float)
    P = prob_2pl(theta, a, b)
    R = X - P
    df = pd.DataFrame(R)
    return df.corr(min_periods=30).to_numpy()


def q3_flags(q3: np.ndarray, item_names: list[str], threshold: float = 0.2) -> list[dict]:
    """Pares com Q3 acima da média + limiar (critério ilustrativo, não universal)."""
    J = q3.shape[0]
    iu = np.triu_indices(J, 1)
    vals = q3[iu]
    mean = np.nanmean(vals)
    out = []
    for i, j, v in zip(iu[0], iu[1], vals):
        if np.isfinite(v) and v - mean > threshold:
            out.append({"item_i": item_names[i], "item_j": item_names[j], "q3": float(v),
                        "q3_minus_mean": float(v - mean)})
    return sorted(out, key=lambda r: -r["q3"])


def observed_vs_expected(X: np.ndarray, a: np.ndarray, b: np.ndarray, theta: np.ndarray,
                         item_names: list[str], n_bins: int = 8) -> pd.DataFrame:
    """Proporção observada vs. esperada por faixa de θ̂ (diagnóstico gráfico,
    não teste formal de ajuste)."""
    X = np.asarray(X, dtype=float)
    ok = np.isfinite(theta)
    bins = pd.qcut(theta[ok], n_bins, labels=False, duplicates="drop")
    rows = []
    for j, name in enumerate(item_names):
        xj = X[ok, j]
        for g in np.unique(bins):
            m = (bins == g) & ~np.isnan(xj)
            if m.sum() < 10:
                continue
            th_mean = float(theta[ok][m].mean())
            rows.append({"item": name, "bin": int(g), "theta_mean": th_mean, "n": int(m.sum()),
                         "observed": float(xj[m].mean()),
                         "expected": float(prob_2pl(np.array([th_mean]), a[j:j + 1], b[j:j + 1])[0, 0])})
    return pd.DataFrame(rows)


def dimensionality_screen(X: np.ndarray) -> dict:
    """Triagem exploratória: autovalores da correlação inter-item (Pearson/phi,
    listwise). Razão 1º/2º autovalor é heurística, não confirmação de
    unidimensionalidade — CFA ordinal (lavaan/WLSMV) fica no roadmap P1."""
    df = pd.DataFrame(np.asarray(X, dtype=float)).dropna()
    if len(df) < 50:
        return {"status": "insufficient", "n": int(len(df))}
    ev = np.sort(np.linalg.eigvalsh(df.corr().to_numpy()))[::-1]
    return {
        "status": "exploratory",
        "n": int(len(df)),
        "eigenvalues_top5": [float(v) for v in ev[:5]],
        "ratio_first_second": float(ev[0] / ev[1]),
        "note": "correlação phi subestima associação de itens dicotômicos; heurística exploratória",
    }
