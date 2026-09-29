"""Baselines preditivos e avaliação externa (seção 12).

B0: regra explícita de frequência recente.
B1: logística regularizada só com dados administrativos.
B2: B1 + escores psicométricos e suas incertezas (posterior_sd).
B3: gradient boosting challenger (calibrado só no treino).

Split: temporal (treino em t0 anteriores) E espacial (escolas externas).
Intervalos: bootstrap agrupado por escola. O modelo nunca decide quem
recebe apoio — gera lista para revisão dentro da capacidade da equipe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ADMIN_FEATURES = ["unjust_abs_20d", "abs_rate_10d", "abs_trend"]
PSYCHO_FEATURES = ["theta_math", "psd_math", "theta_belong", "psd_belong"]
CAPACITY_SHARE = 0.10
SMALL_CELL_K = 10


def split_schools(school_ids: list[str], test_share: float = 0.3, seed: int = 11) -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(seed)
    s = sorted(set(school_ids))
    rng.shuffle(s)
    k = max(1, int(round(len(s) * test_share)))
    return sorted(s[k:]), sorted(s[:k])


def at_capacity(y: np.ndarray, score: np.ndarray, share: float = CAPACITY_SHARE) -> dict:
    k = max(1, int(np.ceil(len(y) * share)))
    top = np.argsort(-score, kind="stable")[:k]
    tp = y[top].sum()
    return {"k": int(k), "precision_at_capacity": float(tp / k),
            "recall_at_capacity": float(tp / y.sum()) if y.sum() else None}


def _metrics(y, p, prob: bool) -> dict:
    out = {"n": int(len(y)), "prevalence": float(y.mean()),
           "roc_auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p))}
    out["brier"] = float(brier_score_loss(y, p)) if prob else None
    out.update(at_capacity(y, p))
    return out


def cluster_bootstrap(y, scores: dict[str, np.ndarray], clusters, n_boot: int = 300, seed: int = 5) -> dict:
    rng = np.random.default_rng(seed)
    cl = np.asarray(clusters)
    uniq = np.unique(cl)
    idx_by = {c: np.where(cl == c)[0] for c in uniq}
    res = {k: [] for k in scores}
    diff = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ii = np.concatenate([idx_by[c] for c in pick])
        if y[ii].min() == y[ii].max():
            continue
        aucs = {k: roc_auc_score(y[ii], s[ii]) for k, s in scores.items()}
        for k, v in aucs.items():
            res[k].append(v)
        if "B1" in aucs and "B2" in aucs:
            diff.append(aucs["B2"] - aucs["B1"])
    out = {k: {"auc_ci95": [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))]} for k, v in res.items()}
    if diff:
        out["B2_minus_B1_auc"] = {"mean": float(np.mean(diff)),
                                  "ci95": [float(np.quantile(diff, 0.025)), float(np.quantile(diff, 0.975))]}
    out["n_boot_effective"] = len(diff) or len(next(iter(res.values())))
    out["cluster"] = "school_id"
    return out


def calibration_bins(y, p, n_bins: int = 10) -> list[dict]:
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = pd.qcut(df["p"], n_bins, labels=False, duplicates="drop")
    g = df.groupby("bin").agg(n=("y", "size"), mean_pred=("p", "mean"), observed=("y", "mean"))
    return g.reset_index().to_dict(orient="records")


def group_fairness(y, p, groups, share: float = CAPACITY_SHARE) -> list[dict]:
    """Métricas por grupo de auditoria (seção 11.4) no ponto de capacidade global.
    Células pequenas são suprimidas; nenhum limiar é ajustado por grupo."""
    k = max(1, int(np.ceil(len(y) * share)))
    thr = np.sort(p)[::-1][k - 1]
    flag = p >= thr
    rows = []
    for gname in sorted(np.unique(groups)):
        m = groups == gname
        yy, ff, pp = y[m], flag[m], p[m]
        pos, neg = yy.sum(), (1 - yy).sum()
        row = {"group": gname, "n": int(m.sum()), "n_positive": int(pos)}
        if pos < SMALL_CELL_K or ff.sum() < SMALL_CELL_K:
            row["status"] = "suppressed_small_cell"
        else:
            row.update(status="computed",
                       flag_rate=float(ff.mean()),
                       recall=float((ff & (yy == 1)).sum() / pos),
                       fpr=float((ff & (yy == 0)).sum() / neg) if neg else None,
                       precision=float((ff & (yy == 1)).sum() / ff.sum()),
                       calibration_in_the_large=float(pp.mean() - yy.mean()))
        rows.append(row)
    return rows


def evaluate_baselines(train: pd.DataFrame, test: pd.DataFrame, groups_test: np.ndarray | None = None,
                       seed: int = 3) -> dict:
    tr = train[train["target_status"] == "observed"].dropna(subset=ADMIN_FEATURES + PSYCHO_FEATURES)
    te = test[test["target_status"] == "observed"].dropna(subset=ADMIN_FEATURES + PSYCHO_FEATURES)
    ytr, yte = tr["target"].to_numpy(int), te["target"].to_numpy(int)

    scores, results = {}, {}
    scores["B0"] = te["unjust_abs_20d"].to_numpy(float) + 0.01 * te["abs_rate_10d"].to_numpy(float)
    results["B0"] = {**_metrics(yte, scores["B0"], prob=False),
                     "definition": "regra: faltas não justificadas nos últimos 20 dias (desempate por taxa 10d)"}

    b1 = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    b1.fit(tr[ADMIN_FEATURES], ytr)
    scores["B1"] = b1.predict_proba(te[ADMIN_FEATURES])[:, 1]
    results["B1"] = {**_metrics(yte, scores["B1"], prob=True),
                     "coefficients": dict(zip(ADMIN_FEATURES, b1[-1].coef_[0].round(4).tolist()))}

    feats2 = ADMIN_FEATURES + PSYCHO_FEATURES
    b2 = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    b2.fit(tr[feats2], ytr)
    scores["B2"] = b2.predict_proba(te[feats2])[:, 1]
    results["B2"] = {**_metrics(yte, scores["B2"], prob=True),
                     "coefficients": dict(zip(feats2, b2[-1].coef_[0].round(4).tolist()))}

    b3 = CalibratedClassifierCV(HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                                               max_iter=200, random_state=seed),
                                method="isotonic", cv=3)
    b3.fit(tr[feats2], ytr)
    scores["B3"] = b3.predict_proba(te[feats2])[:, 1]
    results["B3"] = _metrics(yte, scores["B3"], prob=True)

    out = {
        "n_train": int(len(tr)), "n_test": int(len(te)),
        "train_t0": sorted(tr["t0_day"].unique().tolist()), "test_t0": sorted(te["t0_day"].unique().tolist()),
        "train_schools": sorted(tr["school_id"].unique().tolist()),
        "test_schools": sorted(te["school_id"].unique().tolist()),
        "models": results,
        "bootstrap": cluster_bootstrap(yte, scores, te["school_id"].to_numpy()),
        "calibration_B2": calibration_bins(yte, scores["B2"]),
        "capacity_share": CAPACITY_SHARE,
        "note": ("coeficientes descrevem o modelo, não causas individuais; ganho B2−B1 em dados "
                 "sintéticos não prova ganho em escolas reais"),
    }
    if groups_test is not None:
        g = pd.Series(groups_test, index=test.index).loc[te.index].to_numpy()
        out["fairness_B2"] = group_fairness(yte, scores["B2"], g)
    return out
