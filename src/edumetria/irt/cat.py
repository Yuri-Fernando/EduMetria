"""Teste adaptativo computadorizado (CAT) — simulação sobre banco calibrado.

Só faz sentido com banco suficiente e calibrado (seção 5, P2). Aqui:
- seleção por máxima informação de Fisher no θ̂ corrente, com
  controle de exposição "randomesque" (sorteia entre os k mais informativos);
- estimação EAP a cada passo (prior N(0,1));
- parada por posterior_sd ≤ alvo OU tamanho máximo;
- restrição de conteúdo opcional: mínimo de itens por eixo do blueprint.
Comparação justa: mesmo banco, mesmos examinandos, forma fixa × CAT.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from edumetria.irt.models import info_2pl, prob_2pl
from edumetria.irt.scoring import eap_2pl


def simulate_cat(a: np.ndarray, b: np.ndarray, theta_true: np.ndarray, se_target: float = 0.35,
                 max_items: int = 20, min_items: int = 5, randomesque: int = 3,
                 axes: np.ndarray | None = None, min_per_axis: int = 0, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    J = len(a)
    rows = []
    for i, th in enumerate(theta_true):
        used: list[int] = []
        x = np.full(J, np.nan)
        est, sd = 0.0, 1.0
        while True:
            avail = np.setdiff1d(np.arange(J), used)
            if len(avail) == 0:
                break
            if axes is not None and min_per_axis:
                remaining = max_items - len(used)
                need = [ax for ax in np.unique(axes) if (axes[used] == ax).sum() < min_per_axis] if used else list(np.unique(axes))
                if need and remaining <= len(need) * min_per_axis:
                    avail = avail[np.isin(axes[avail], need)] if np.isin(axes[avail], need).any() else avail
            info = info_2pl(np.array([est]), a[avail], b[avail])[0]
            top = avail[np.argsort(-info)[:randomesque]]
            j = int(rng.choice(top))
            used.append(j)
            x[j] = float(rng.random() < prob_2pl(np.array([th]), a[j:j + 1], b[j:j + 1])[0, 0])
            r = eap_2pl(x[None, :], a, b)
            est, sd = float(r.theta[0]), float(r.posterior_sd[0])
            if len(used) >= max_items or (len(used) >= min_items and sd <= se_target):
                break
        rows.append({"examinee": i, "theta_true": th, "theta_hat": est, "posterior_sd": sd, "n_items": len(used),
                     "items": used})
    return pd.DataFrame(rows)


def fixed_form(a: np.ndarray, b: np.ndarray, theta_true: np.ndarray, form_items: np.ndarray, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    P = prob_2pl(theta_true, a[form_items], b[form_items])
    X = np.full((len(theta_true), len(a)), np.nan)
    X[:, form_items] = (rng.random(P.shape) < P).astype(float)
    r = eap_2pl(X, a, b)
    return pd.DataFrame({"theta_true": theta_true, "theta_hat": r.theta, "posterior_sd": r.posterior_sd,
                         "n_items": len(form_items)})


def summarize(df: pd.DataFrame, bins=(-np.inf, -1, 1, np.inf)) -> dict:
    err = df["theta_hat"] - df["theta_true"]
    band = pd.cut(df["theta_true"], bins, labels=["θ<−1", "−1≤θ≤1", "θ>1"])
    by = df.assign(err2=err**2, band=band).groupby("band", observed=True).agg(
        rmse=("err2", lambda s: float(np.sqrt(s.mean()))), mean_items=("n_items", "mean"), n=("n_items", "size"))
    return {"rmse": float(np.sqrt((err**2).mean())), "bias": float(err.mean()),
            "mean_items": float(df["n_items"].mean()), "corr": float(np.corrcoef(df["theta_hat"], df["theta_true"])[0, 1]),
            "by_band": by.reset_index().to_dict(orient="records")}


def exposure_rates(cat: pd.DataFrame, n_items: int) -> np.ndarray:
    counts = np.zeros(n_items)
    for items in cat["items"]:
        counts[items] += 1
    return counts / len(cat)
