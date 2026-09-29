"""Worker de jobs (seção 18): reivindica job com lease, executa, registra
candidato de calibração e encerra com status explícito.

Semântica de erro:
- dado bloqueado / entrada inválida → ``failed`` sem retentativa;
- erro transitório → volta para ``queued`` até ``max_attempts``;
- worker morto → lease expira e outro worker retoma (sem duplicar candidato:
  o registro só acontece no fim, junto do ``finish_job``).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

from edumetria.observability.telemetry import METRICS, get_logger, log_event
from edumetria.pipeline import PipelineBlocked, run_analysis
from edumetria.registry.store import Store

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_ROOT = ROOT / "data" / "snapshots"


def resolve_snapshot(snapshot_id: str, root: Path = SNAPSHOT_ROOT) -> Path:
    """Resolve id → diretório garantindo contenção no root (anti path traversal)."""
    p = (root / snapshot_id).resolve()
    if root.resolve() not in p.parents or not (p / "scenario.yaml").exists():
        raise ValueError(f"snapshot inexistente ou fora do repositório de dados: {snapshot_id!r}")
    return p


def run_once(store: Store, worker_id: str | None = None, runs_dir: Path | None = None,
             snapshot_root: Path = SNAPSHOT_ROOT, overrides: dict | None = None) -> dict | None:
    worker_id = worker_id or f"worker-{uuid.uuid4().hex[:6]}"
    logger = get_logger("edumetria.worker")
    job = store.claim_job(worker_id)
    if not job:
        return None
    payload = json.loads(job["payload"])
    log_event(logger, "job.claimed", job_id=job["job_id"], attempt=job["attempts"])
    try:
        snap = resolve_snapshot(payload["dataset_snapshot_id"], snapshot_root)
        import yaml
        snap_cfg = yaml.safe_load((snap / "scenario.yaml").read_text(encoding="utf-8"))
        scenario_id = snap_cfg["scenario_id"]
        known = {snap_cfg["math"]["instrument_version_id"], snap_cfg["belonging"]["instrument_version_id"]}
        if payload["instrument_version_id"] not in known:
            raise ValueError(f"versão de instrumento {payload['instrument_version_id']!r} não existe no snapshot")
        res = run_analysis(scenario_id, runs_dir=runs_dir, purpose=payload.get("purpose", "simulation"),
                           overrides=overrides)
        cal_id = store.register_calibration(job["tenant"], payload["instrument_version_id"],
                                            payload["dataset_snapshot_id"], payload["model_family"],
                                            res["run_id"], res["manifest_hash"], res["converged"])
        result = {"calibration_id": cal_id, "run_id": res["run_id"], "run_dir": res["run_dir"],
                  "converged": res["converged"]}
        store.finish_job(job["job_id"], worker_id, ok=True, result=result)
        METRICS.inc("edumetria_jobs_total", job_type="calibration", status="succeeded")
        return {"job_id": job["job_id"], "status": "succeeded", **result}
    except PipelineBlocked as exc:
        store.finish_job(job["job_id"], worker_id, ok=False, error_code="data_quality_blocked",
                         error_detail=str(exc)[:300])
        code = "data_quality_blocked"
    except (ValueError, KeyError) as exc:
        store.finish_job(job["job_id"], worker_id, ok=False, error_code="invalid_input",
                         error_detail=str(exc)[:300])
        code = "invalid_input"
    except Exception as exc:  # transitório: permite retentativa
        store.finish_job(job["job_id"], worker_id, ok=False, error_code="internal",
                         error_detail=type(exc).__name__, retryable=True)
        code = "internal"
    METRICS.inc("edumetria_jobs_total", job_type="calibration", status="failed")
    log_event(logger, "job.failed", job_id=job["job_id"], error_code=code)
    return {"job_id": job["job_id"], "status": "failed", "error_code": code}


def main() -> None:
    ap = argparse.ArgumentParser(description="Worker EduMetria")
    ap.add_argument("--db", default=os.environ.get("EDUMETRIA_DB", str(ROOT / "runs" / "edumetria.db")))
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=float, default=2.0)
    a = ap.parse_args()
    store = Store(a.db)
    while True:
        r = run_once(store)
        if r:
            print(json.dumps(r, ensure_ascii=False))
        if not a.loop:
            break
        if not r:
            time.sleep(a.interval)


if __name__ == "__main__":
    main()
