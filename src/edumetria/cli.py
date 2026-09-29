"""CLI EduMetria. Cada comando só é anunciado no README depois de existir.

    edumetria demo-data --scenario s0
    edumetria analyze --scenario s2 [--resolve-quarantine]
    edumetria recovery-study --reps 100
    edumetria benchmark
    edumetria list-runs
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def cmd_demo_data(a) -> None:
    from edumetria.simulation.generator import generate
    ds = generate(a.scenario)
    out = ds.save(ROOT / "data" / "snapshots" / f"synthetic-{ds.scenario['scenario_id']}")
    print(json.dumps({"snapshot_dir": str(out), "responses": len(ds.responses),
                      "students": len(ds.students)}, ensure_ascii=False))


def cmd_analyze(a) -> None:
    from edumetria.pipeline import PipelineBlocked, run_analysis
    try:
        r = run_analysis(a.scenario, resolve_quarantine=a.resolve_quarantine)
        print(json.dumps(r, ensure_ascii=False, default=str, indent=2))
    except PipelineBlocked as exc:
        print(json.dumps({"status": "blocked_by_data_quality", "detail": str(exc),
                          "run_dir": str(exc.run_dir),
                          "next_step": "revisar data_quality.json; reexecutar com --resolve-quarantine"},
                         ensure_ascii=False, indent=2))
        sys.exit(2)


def cmd_recovery(a) -> None:
    from edumetria.simulation.monte_carlo import run_dif_study, run_recovery_study
    out = ROOT / "reports" / "monte_carlo"
    out.mkdir(parents=True, exist_ok=True)
    rec = run_recovery_study(reps=a.reps, sizes=tuple(a.sizes), seed=a.seed)
    (out / "recovery_2pl.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    dif = run_dif_study(reps=a.dif_reps, seed=a.seed + 1)
    (out / "dif_power_fpr.json").write_text(json.dumps(dif, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"recovery": rec["summary"], "dif": dif["summary"]}, indent=2, ensure_ascii=False))


def cmd_benchmark(a) -> None:
    import numpy as np
    from edumetria.irt.estimation import fit_2pl
    from edumetria.irt.models import prob_2pl
    rng = np.random.default_rng(1)
    n, J = 2000, 24
    X = (rng.random((n, J)) < prob_2pl(rng.normal(size=n), rng.lognormal(0.1, 0.3, J),
                                         rng.normal(size=J))).astype(float)
    tracemalloc.start()
    t0, c0 = time.perf_counter(), time.process_time()
    r = fit_2pl(X)
    wall, cpu = time.perf_counter() - t0, time.process_time() - c0
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    import platform
    res = {"task": "2PL MML-EM 2000x24", "wall_seconds": round(wall, 3), "cpu_seconds": round(cpu, 3),
           "peak_python_alloc_mb": round(peak / 2**20, 1), "iterations": r.iterations, "converged": r.converged,
           "hardware": platform.processor() or platform.machine(), "python": platform.python_version(),
           "budget_seconds": 600}
    out = ROOT / "reports" / "benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


def cmd_list_runs(a) -> None:
    runs = ROOT / "runs"
    for p in sorted(runs.glob("run-*")):
        st = p / "run_status.json"
        status = json.loads(st.read_text(encoding="utf-8"))["status"] if st.exists() else "unknown"
        print(f"{p.name}\t{status}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="edumetria")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("demo-data")
    p.add_argument("--scenario", default="s0")
    p.set_defaults(fn=cmd_demo_data)
    p = sub.add_parser("analyze")
    p.add_argument("--scenario", default="s0")
    p.add_argument("--resolve-quarantine", action="store_true")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("recovery-study")
    p.add_argument("--reps", type=int, default=100)
    p.add_argument("--dif-reps", type=int, default=50)
    p.add_argument("--sizes", type=int, nargs="+", default=[500, 1000, 2000])
    p.add_argument("--seed", type=int, default=20260928)
    p.set_defaults(fn=cmd_recovery)
    p = sub.add_parser("benchmark")
    p.set_defaults(fn=cmd_benchmark)
    p = sub.add_parser("list-runs")
    p.set_defaults(fn=cmd_list_runs)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    a.fn(a)


if __name__ == "__main__":
    main()
