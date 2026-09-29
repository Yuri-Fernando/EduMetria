"""Estudos Monte Carlo (seção 14): recuperação de parâmetros e DIF.

Regras: parâmetros verdadeiros fixos por estudo; runs falhos/não convergidos
permanecem no denominador (status registrado); erro Monte Carlo reportado;
escala alinhada por construção (θ ~ N(0,1) no gerador e no ajuste).
Metas exploratórias do plano (RMSE de a e b ≤ 0,30 em S0, N=2000) são alvos
de investigação — não validação universal.
"""

from __future__ import annotations

import time

import numpy as np

from edumetria.dif.analysis import run_dif
from edumetria.irt.estimation import fit_2pl
from edumetria.irt.models import prob_2pl
from edumetria.irt.scoring import eap_2pl


def _true_params(J: int, rng) -> tuple[np.ndarray, np.ndarray]:
    return rng.lognormal(0.1, 0.3, J), rng.normal(0, 1, J)


def run_recovery_study(reps: int = 100, sizes=(500, 1000, 2000), J: int = 24, missing: float = 0.02,
                       seed: int = 20260928) -> dict:
    rng = np.random.default_rng(seed)
    a_true, b_true = _true_params(J, rng)
    conditions = []
    t0 = time.perf_counter()
    for N in sizes:
        rec = {"a": [], "b": [], "cov_a": [], "cov_b": [], "theta_rmse": [], "theta_corr": []}
        status = {"converged": 0, "nonconverged": 0, "failed": 0}
        for _ in range(reps):
            th = rng.normal(0, 1, N)
            X = (rng.random((N, J)) < prob_2pl(th, a_true, b_true)).astype(float)
            X[rng.random((N, J)) < missing] = np.nan
            try:
                f = fit_2pl(X)
            except Exception:
                status["failed"] += 1
                continue
            status["converged" if f.converged else "nonconverged"] += 1
            a, b = f.params["a"].to_numpy(), f.params["b"].to_numpy()
            rec["a"].append(a - a_true)
            rec["b"].append(b - b_true)
            rec["cov_a"].append(np.abs(a - a_true) <= 1.96 * f.params["se_a"].to_numpy())
            rec["cov_b"].append(np.abs(b - b_true) <= 1.96 * f.params["se_b"].to_numpy())
            e = eap_2pl(X, a, b)
            ok = np.isfinite(e.theta)
            rec["theta_rmse"].append(float(np.sqrt(np.mean((e.theta[ok] - th[ok]) ** 2))))
            rec["theta_corr"].append(float(np.corrcoef(e.theta[ok], th[ok])[0, 1]))
        ea, eb = np.array(rec["a"]), np.array(rec["b"])
        ca, cb = np.array(rec["cov_a"]), np.array(rec["cov_b"])
        n_ok = len(ea)

        def mcse_prop(p, k):
            return float(np.sqrt(p * (1 - p) / k)) if k else None
        conditions.append({
            "N": N, "reps_planned": reps, "reps_used": n_ok, "status": status,
            "bias_a": float(ea.mean()), "bias_b": float(eb.mean()),
            "rmse_a": float(np.sqrt((ea**2).mean())), "rmse_b": float(np.sqrt((eb**2).mean())),
            "rmse_a_mcse": float(np.sqrt((ea**2).mean(axis=1)).std(ddof=1) / np.sqrt(n_ok)),
            "rmse_b_mcse": float(np.sqrt((eb**2).mean(axis=1)).std(ddof=1) / np.sqrt(n_ok)),
            "coverage95_a": float(ca.mean()), "coverage95_a_mcse": mcse_prop(ca.mean(), ca.size),
            "coverage95_b": float(cb.mean()), "coverage95_b_mcse": mcse_prop(cb.mean(), cb.size),
            "theta_rmse_mean": float(np.mean(rec["theta_rmse"])),
            "theta_corr_mean": float(np.mean(rec["theta_corr"])),
            "target_rmse_le_0_30_met": bool(np.sqrt((ea**2).mean()) <= 0.30 and np.sqrt((eb**2).mean()) <= 0.30),
        })
    return {
        "study": "recuperação 2PL MML-EM (engine python-native)",
        "design": {"J": J, "sizes": list(sizes), "reps": reps, "missing_mcar": missing, "seed": seed,
                   "true_params": {"a": a_true.tolist(), "b": b_true.tolist()},
                   "ci": "Wald 95% com SE crossprod"},
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        "conditions": conditions,
        "summary": [{k: c[k] for k in ("N", "reps_used", "rmse_a", "rmse_b", "coverage95_a", "coverage95_b",
                                        "target_rmse_le_0_30_met")} for c in conditions],
        "note": ("MCSE de cobertura assume independência entre itens e réplicas (aproximação); "
                 "metas são exploratórias e não foram ajustadas após ver resultados"),
    }


def run_dif_study(reps: int = 50, N: int = 2000, J: int = 24, seed: int = 20260929) -> dict:
    rng = np.random.default_rng(seed)
    a_true, b_true = _true_params(J, rng)
    names = [f"A{j + 1:02d}" for j in range(J)]
    dif_items = {"A05": 0.60, "A13": 0.50, "A21": -0.55}
    out = {}
    t0 = time.perf_counter()
    for cond in ("no_dif", "uniform_dif"):
        flags_u, flags_any = [], []
        for _ in range(reps):
            th = rng.normal(0, 1, N)
            grp = np.where(rng.random(N) < 0.5, "B", "A")
            B = np.tile(b_true, (N, 1))
            if cond == "uniform_dif":
                for it, d in dif_items.items():
                    B[grp == "B", names.index(it)] += d
            P = 1 / (1 + np.exp(-a_true * (th[:, None] - B)))
            X = (rng.random((N, J)) < P).astype(float)
            X[rng.random((N, J)) < 0.02] = np.nan
            d = run_dif(X, names, grp, anchors=None)
            flags_u.append(d["flag_uniform"].to_numpy(bool))
            flags_any.append(d["flagged"].to_numpy(bool))
        fu, fa = np.array(flags_u), np.array(flags_any)
        is_dif = np.array([n in dif_items for n in names]) if cond == "uniform_dif" else np.zeros(J, bool)
        res = {"reps": reps,
               "false_positive_rate_uniform_rule": float(fu[:, ~is_dif].mean()),
               "false_positive_rate_any_rule": float(fa[:, ~is_dif].mean()),
               "reps_with_any_false_positive": float((fa[:, ~is_dif].any(axis=1)).mean())}
        if is_dif.any():
            res["power_uniform_rule"] = float(fu[:, is_dif].mean())
            res["power_per_item"] = {n: float(fu[:, names.index(n)].mean()) for n in dif_items}
        out[cond] = res
    return {
        "study": "DIF — Mantel-Haenszel (ETS B/C + BH) e regressão logística (não uniforme, BH)",
        "design": {"N": N, "J": J, "group_share_b": 0.5, "dif_items": dif_items, "anchors": "todos os outros itens",
                   "seed": seed},
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
        "results": out,
        "summary": {c: {k: v for k, v in r.items() if k != "power_per_item"} for c, r in out.items()},
        "note": "taxa por item×réplica; regra de sinalização definida antes do estudo e não ajustada depois",
    }
