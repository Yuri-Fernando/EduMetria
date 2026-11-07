#!/usr/bin/env python
"""Estudo Monte Carlo do sinal por eixo da Visão do Educador (EduMetria Social).

    python scripts/educator_signal_study.py [--reps 50]   → reports/ai4good2027/educator_signal_study.json

Pergunta: o sinal "acertos no eixo abaixo do esperado pela própria escola" encontra a
dificuldade localizada plantada (S12) sem acender onde não há efeito (S0 e demais
escolas/eixos do S12)? Gabarito conhecido; seeds sequenciais a partir da seed do cenário
(nenhuma seed escolhida a dedo); todas as réplicas entram no denominador.

Calcula, por réplica: calibração 2PL nativa nos dados aceitos → sinal por eixo com BH.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from edumetria.data_quality.validate import to_wide, validate_responses  # noqa: E402
from edumetria.irt.estimation import fit_2pl  # noqa: E402
from edumetria.reporting.educator import axis_signals, load_config  # noqa: E402
from edumetria.simulation.generator import _deep_merge, generate, load_scenario  # noqa: E402

OUT = ROOT / "reports" / "ai4good2027"


def one_rep(scenario: str, seed: int, cfg: dict, overrides: dict | None = None) -> dict:
    sc = load_scenario(scenario)
    sc = _deep_merge(sc, {"seed": seed, **(overrides or {})})
    ds = generate(sc)
    batch = validate_responses(ds.responses, ds.items, snapshot_prefix=f"study-{scenario}")
    X, persons, cols = to_wide(batch.accepted, "math6", ds.items)
    fit = fit_2pl(X, [c.split("-")[1] for c in cols])
    axis_of = ds.items.set_index("item_version_id")["axis"].to_dict()
    school_of = ds.students.set_index("student_ref")["school_id"].to_dict()
    rows = axis_signals(X, persons, [axis_of[c] for c in cols], fit.params["a"].to_numpy(),
                        fit.params["b"].to_numpy(), school_of, cfg)
    planted = {(e["school_id"], e["axis"]) for e in ds.truth.get("school_axis_effects", [])}
    hits = sum(1 for r in rows if (r["school_id"], r["axis"]) in planted and r["signal"] == "lower_than_expected")
    false_flags = [r for r in rows if (r["school_id"], r["axis"]) not in planted
                   and r["signal"] in ("lower_than_expected", "higher_than_expected")]
    per_planted = {f"{s}/{a}": any(r["school_id"] == s and r["axis"] == a and r["signal"] == "lower_than_expected"
                                   for r in rows) for s, a in planted}
    return {"seed": seed, "converged": bool(fit.converged), "n_tests": len(rows), "n_planted": len(planted),
            "hits": hits, "n_false_flags": len(false_flags), "per_planted": per_planted}


def summarize(reps: list[dict]) -> dict:
    n_null_tests = sum(r["n_tests"] - r["n_planted"] for r in reps)
    out = {"n_reps": len(reps), "converged_share": float(np.mean([r["converged"] for r in reps])),
           "false_flag_rate_per_test": sum(r["n_false_flags"] for r in reps) / n_null_tests if n_null_tests else None,
           "reps_with_any_false_flag": float(np.mean([r["n_false_flags"] > 0 for r in reps]))}
    if reps and reps[0]["n_planted"]:
        out["power_overall"] = sum(r["hits"] for r in reps) / sum(r["n_planted"] for r in reps)
        keys = reps[0]["per_planted"].keys()
        out["power_by_planted_effect"] = {k: float(np.mean([r["per_planted"][k] for r in reps])) for k in keys}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=50)
    args = ap.parse_args()
    cfg = load_config()
    t0 = time.perf_counter()
    result = {"description": __doc__.strip().splitlines()[0], "data_origin": "synthetic",
              "config_axis_signal": cfg["axis_signal"], "conditions": {}}
    weak = {"math": {"school_axis_effects": [{"school_id": "SCH01", "axis": "dados_graficos", "delta_b": 0.25},
                                             {"school_id": "SCH07", "axis": "resolucao_problemas", "delta_b": 0.25}]}}
    for name, scen, ovr in (("s12_planted", "s12", None), ("s12_weak_effect_0.25", "s12", weak),
                            ("s0_null", "s0", None)):
        base_seed = int(load_scenario(scen)["seed"])
        reps = []
        for i in range(args.reps):
            reps.append(one_rep(scen, base_seed + i, cfg, ovr))
            print(f"{name} réplica {i + 1}/{args.reps}: acertos {reps[-1]['hits']}/{reps[-1]['n_planted']}, "
                  f"falsos {reps[-1]['n_false_flags']}")
        result["conditions"][name] = {"scenario": scen, "overrides": ovr,
                                      "seeds": [base_seed, base_seed + args.reps - 1],
                                      "summary": summarize(reps), "replicates": reps}
    result["elapsed_seconds"] = time.perf_counter() - t0
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "educator_signal_study.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in result["conditions"].items()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
