"""Manifesto de execução (seção 15): versões, hashes, origem e parâmetros.
Referencia hashes — nunca inclui registros individuais."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from edumetria import __version__

ROOT = Path(__file__).resolve().parents[3]
TRACKED_PACKAGES = ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "pydantic", "matplotlib"]


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def code_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain", "src"], cwd=ROOT, capture_output=True, text=True,
                               timeout=10)
        if out.returncode == 0:
            return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        pass
    return "unversioned"


def package_versions() -> dict:
    out = {"python": platform.python_version(), "edumetria": __version__}
    for p in TRACKED_PACKAGES:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            out[p] = None
    return out


def build_manifest(run_id: str, purpose: str, data_origin: str, dataset_hash_: str, seed: int, method: dict,
                   fit_options: dict, sample_design: dict, split_manifest: dict, warnings: list[str],
                   artifacts_dir: Path, instrument_versions: list[str]) -> dict:
    lock = ROOT / "requirements.txt"
    artifacts = {}
    for p in sorted(artifacts_dir.rglob("*")):
        if p.is_file() and p.name not in ("manifest.json",):
            artifacts[str(p.relative_to(artifacts_dir)).replace("\\", "/")] = sha256_file(p)
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": purpose,
        "data_origin": data_origin,
        "dataset_hash": dataset_hash_,
        "item_bank_hash": sha256_file(ROOT / "configs" / "item_bank.yaml"),
        "instrument_versions": instrument_versions,
        "code_commit": code_commit(),
        "image_digest": None,
        "python_lock_hash": sha256_file(lock) if lock.exists() else None,
        "renv_lock_hash": None,
        "environment": {**package_versions(), "platform": platform.platform()},
        "seed": seed,
        "method": method,
        "fit_options": fit_options,
        "sample_design": sample_design,
        "split_manifest": split_manifest,
        "warnings": warnings,
        "artifacts": artifacts,
        "reviewer": None,
        "release_status": "candidate",
    }


def write_manifest(manifest: dict, out_dir: Path) -> str:
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return sha256_file(path)
