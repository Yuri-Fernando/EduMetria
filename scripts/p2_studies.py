#!/usr/bin/env python
"""Estudos P2 que dependem só de código e dados simulados (sem custo, sem parceria).

    python scripts/p2_studies.py        → reports/p2/*.json + figuras

1. Linking longitudinal (2 ondas, âncoras, drift) — 4 métodos.
2. CAT × forma fixa (banco de 120 itens calibrado por simulação).
3. Testlet/bifator (S5) vs. unidimensional — R/mirt.
4. Comparadores 3PL e GPCM — R/mirt (sem prior; convergência reportada).
5. Multinível: recuperação do ICC com efeito de escola conhecido.
6. Impacto: MDES analítico e poder por simulação (ensaio por escolas).
7. Copiloto: avaliação no dataset versionado.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from edumetria.copilot.copilot import Copilot, evaluate_copilot  # noqa: E402
from edumetria.data_quality.validate import to_wide, validate_responses  # noqa: E402
from edumetria.impact.design import clusters_needed, mdes_cluster_rct, simulate_power  # noqa: E402
from edumetria.irt import r_engine  # noqa: E402
from edumetria.irt.cat import exposure_rates, fixed_form, simulate_cat, summarize  # noqa: E402
from edumetria.registry.store import Actor  # noqa: E402
from edumetria.risk.features import build_snapshot  # noqa: E402
from edumetria.risk.multilevel import school_icc  # noqa: E402
from edumetria.simulation.generator import generate  # noqa: E402
from edumetria.simulation.waves import run_linking_study  # noqa: E402

OUT = ROOT / "reports" / "p2"


def _dump(name: str, obj) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=lambda o: o.tolist()
                                       if hasattr(o, "tolist") else str(o)), encoding="utf-8")


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    summary = {}

    # 1. linking
    lk = run_linking_study()
    lk_table = lk.pop("table")
    lk_table.to_csv(OUT / "linking_study.csv", index=False)
    _dump("linking_study.json", {**lk, "drift": None, "table": lk_table.round(4).to_dict(orient="records")})
    summary["linking"] = {"unlinked_growth": lk["unlinked_growth"], "flagged": lk.get("flagged_anchors"),
                          "best_error_all_anchors": float(lk_table[lk_table["anchors"] == "todas as âncoras"]["error"].abs().min()),
                          "stocking_lord_error_after_removal": float(lk_table.query(
                              "anchors == 'sem âncora instável' and method == 'stocking_lord'")["error"].iloc[0])}
    print("[1] linking", summary["linking"])

    # 2. CAT
    rng = np.random.default_rng(7)
    J = 120
    a, b = rng.lognormal(0.2, 0.3, J), rng.normal(0, 1.2, J)
    th = rng.normal(0, 1, 600)
    cat = simulate_cat(a, b, th, se_target=0.35, max_items=24, seed=1)
    ff = fixed_form(a, b, th, np.argsort(-a)[:24], seed=1)  # forma fixa com os 24 mais discriminativos
    exp = exposure_rates(cat, J)
    summary["cat"] = {"cat": summarize(cat), "fixed_24": summarize(ff), "bank_size": J,
                      "max_exposure_rate": float(exp.max()), "items_never_used": int((exp == 0).sum())}
    _dump("cat_study.json", summary["cat"])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].scatter(cat["theta_true"], cat["n_items"], s=6, alpha=0.5)
    ax[0].set(xlabel="θ verdadeiro", ylabel="itens aplicados (CAT)", title="CAT: tamanho do teste por θ")
    ax[1].hist(exp, bins=30, color="#2f5d8a")
    ax[1].set(xlabel="taxa de exposição do item", ylabel="nº de itens", title="Exposição no banco (CAT)")
    plt.tight_layout()
    plt.savefig(OUT / "cat_study.png", dpi=120)
    plt.close()
    print("[2] CAT", {k: summary["cat"][k]["rmse"] for k in ("cat", "fixed_24")}, summary["cat"]["cat"]["mean_items"])

    # 3-4. R: bifator, 3PL, GPCM
    if r_engine.available():
        ds5 = generate("s5")
        b5 = validate_responses(ds5.responses, ds5.items)
        Xm, _, cm = to_wide(b5.accepted, "math6", ds5.items)
        names = [c.split("-")[1] for c in cm]
        spec = [1 if n in ds5.truth["testlet_items"] else None for n in names]
        bf = r_engine.bifactor(Xm, names, spec)
        ds0 = generate("s0")
        b0 = validate_responses(ds0.responses, ds0.items)
        X0, _, c0 = to_wide(b0.accepted, "math6", ds0.items)
        Xb, _, cb = to_wide(b0.accepted, "belong6", ds0.items)
        n0 = [c.split("-")[1] for c in c0]
        nb = [c.split("-")[1] for c in cb]
        r2 = r_engine.fit_mirt(X0, n0, "2pl")
        r3 = r_engine.fit_mirt(X0, n0, "3pl")
        rg = r_engine.fit_mirt(Xb, nb, "grm")
        rp = r_engine.fit_mirt(Xb, nb, "gpcm")
        k2, k3 = 2 * len(n0), 3 * len(n0)
        summary["r_models"] = {
            "bifactor_s5": {"lr_p": bf["lr_p"], "bic": bf["bic"], "aic": bf["aic"],
                            "testlet_items": ds5.truth["testlet_items"]},
            "comparators_s0_math": {"2pl": {"loglik": r2["loglik"], "converged": r2["converged"]},
                                    "3pl": {"loglik": r3["loglik"], "converged": r3["converged"],
                                            "iterations": r3["iterations"]},
                                    "bic_2pl": -2 * r2["loglik"] + np.log(2000) * k2,
                                    "bic_3pl": -2 * r3["loglik"] + np.log(2000) * k3,
                                    "note": "dados gerados por 2PL: 3PL não deve ser preferido; c sem prior é instável"},
            "comparators_s0_belong": {"grm": {"loglik": rg["loglik"], "converged": rg["converged"]},
                                      "gpcm": {"loglik": rp["loglik"], "converged": rp["converged"]},
                                      "note": "dados gerados por GRM; GPCM é comparador, não escolha por nome"}}
    else:
        summary["r_models"] = {"status": "not_run", "reason": "Rscript + mirt indisponíveis"}
    _dump("r_models.json", summary["r_models"])
    print("[3-4] R", json.dumps(summary["r_models"], default=str)[:300])

    # 5. multinível: ICC conhecido
    rng = np.random.default_rng(3)
    true_icc = 0.15
    schools = np.repeat(np.arange(40), 60)
    u = rng.normal(0, np.sqrt(true_icc), 40)[schools]
    y = u + rng.normal(0, np.sqrt(1 - true_icc), len(schools))
    mi = school_icc(pd.DataFrame({"theta": y, "school_id": schools.astype(str)}), "theta")
    ds0 = generate("s0")
    snap = build_snapshot(ds0.attendance, 40)
    yy = snap[["school_id", "target"]].rename(columns={"target": "y"}).dropna()
    mi_out = school_icc(yy, "y")
    realized = float(np.var(u[::60], ddof=1) / (np.var(u[::60], ddof=1) + (1 - true_icc)))
    summary["multilevel"] = {"recovery": {"true_icc_population": true_icc, "realized_icc_sample": realized,
                                          "estimated_icc_reml": mi["icc"], "estimated_icc_anova": mi["icc_anova_crosscheck"],
                                          "n_schools": 40, "per_school": 60},
                             "synthetic_outcome_icc": mi_out["icc"], "boundary": mi_out["boundary"],
                             "theta_icc_note": "no gerador, θ não tem efeito de escola (ICC verdadeiro = 0)"}
    _dump("multilevel.json", summary["multilevel"])
    print("[5] ICC", summary["multilevel"]["recovery"])

    # 6. impacto
    icc_plan = 0.05  # premissa conservadora de planejamento (literatura educacional costuma relatar 0,05–0,20)
    summary["impact"] = {
        "assumed_icc_for_planning": icc_plan,
        "mdes_20_schools_100_students": mdes_cluster_rct(20, 100, icc_plan),
        "schools_needed_es_0_20": clusters_needed(0.20, 100, icc_plan),
        "schools_needed_es_0_10": clusters_needed(0.10, 100, icc_plan),
        "simulated_power_rd_3pp_20_schools": simulate_power(yy, 0.03, n_reps=300),
        "note": "efeito plantado é premissa; o estudo real exige pré-registro e parceria"}
    _dump("impact_design.json", summary["impact"])
    print("[6] impacto", {k: v for k, v in summary["impact"].items() if k != "simulated_power_rd_3pp_20_schools"},
          summary["impact"]["simulated_power_rd_3pp_20_schools"]["power"])

    # 7. copiloto
    demo = sorted((ROOT / "reports" / "demo_runs").glob("run-s2-*"))[-1]
    cases = yaml.safe_load((ROOT / "configs" / "copilot_eval.yaml").read_text(encoding="utf-8"))["cases"]
    ev = evaluate_copilot(Copilot(demo), cases, Actor("coord-bruno", "demo-tenant", "coordinator",
                                                      frozenset({"SCH01", "SCH02"})))
    ev["caveat"] = ("dataset escrito pelo mesmo autor do copiloto: mede conformidade à especificação, "
                    "não robustez adversarial real")
    _dump("copilot_eval.json", ev)
    summary["copilot"] = {k: v for k, v in ev.items() if k != "cases"}
    print("[7] copiloto", summary["copilot"])

    summary["elapsed_seconds"] = round(time.perf_counter() - t0, 1)
    _dump("summary.json", summary)
    return summary


if __name__ == "__main__":
    main()
