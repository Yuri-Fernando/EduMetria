"""Adapter para o worker R/mirt (ADR-002).

Segurança (teste T24): só scripts fixos do diretório ``r/``, famílias da
allowlist, arquivos criados pelo próprio adapter em diretório temporário e
``subprocess`` sem shell. Nenhuma string do cliente vira comando R.

Descoberta do Rscript: variável ``EDUMETRIA_RSCRIPT`` ou PATH; bibliotecas
extras via ``EDUMETRIA_R_LIBS``. Se ausente, ``available()`` retorna False e
a parte bloqueada é reportada — nunca substituída silenciosamente.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from edumetria.domain.contracts import ALLOWED_MODEL_FAMILIES

R_DIR = Path(__file__).resolve().parents[3] / "r"
SCRIPTS = {"fit": R_DIR / "fit_irt.R", "dif": R_DIR / "dif.R", "cfa": R_DIR / "cfa_ordinal.R"}


class REngineUnavailable(RuntimeError):
    pass


def rscript_path() -> str | None:
    env = os.environ.get("EDUMETRIA_RSCRIPT")
    if env and Path(env).exists():
        return env
    return shutil.which("Rscript")


def _env() -> dict:
    env = dict(os.environ)
    libs = os.environ.get("EDUMETRIA_R_LIBS")
    if libs:
        env["R_LIBS_USER"] = libs
        env["R_LIBS"] = libs
    return env


def available() -> bool:
    rs = rscript_path()
    if not rs:
        return False
    try:
        out = subprocess.run([rs, "-e", "cat(requireNamespace('mirt', quietly=TRUE))"],
                             capture_output=True, text=True, timeout=60, env=_env())
        return out.stdout.strip().endswith("TRUE")
    except (OSError, subprocess.SubprocessError):
        return False


def _run(script: str, args: list[str], timeout: int = 900) -> None:
    rs = rscript_path()
    if not rs:
        raise REngineUnavailable("Rscript não encontrado (defina EDUMETRIA_RSCRIPT)")
    if script not in SCRIPTS:
        raise ValueError(f"script não permitido: {script}")
    proc = subprocess.run([rs, str(SCRIPTS[script]), *args], capture_output=True, text=True, timeout=timeout,
                          env=_env(), shell=False)
    if proc.returncode != 0:
        # erro sanitizado: só as últimas linhas técnicas, sem dados
        raise RuntimeError(f"worker R falhou (código {proc.returncode}): {proc.stderr.strip().splitlines()[-3:]}")


def fit_mirt(X: np.ndarray, item_names: list[str], family: str, seed: int = 20260928) -> dict:
    if family not in ALLOWED_MODEL_FAMILIES:
        raise ValueError(f"família fora da allowlist: {family!r}")
    if not all(n.replace("_", "").isalnum() for n in item_names):
        raise ValueError("nomes de item devem ser alfanuméricos")
    with tempfile.TemporaryDirectory(prefix="edumetria-r-") as td:
        inp, out = Path(td) / "X.csv", Path(td) / "out.json"
        pd.DataFrame(np.asarray(X, dtype=float), columns=item_names).to_csv(inp, index=False, na_rep="NA")
        _run("fit", [str(inp), str(out), family, str(int(seed))])
        return json.loads(out.read_text(encoding="utf-8"))


def dif_mirt(X: np.ndarray, item_names: list[str], group: np.ndarray, anchors: list[str]) -> dict:
    unknown = set(anchors) - set(item_names)
    if unknown:
        raise ValueError(f"âncoras desconhecidas: {sorted(unknown)}")
    with tempfile.TemporaryDirectory(prefix="edumetria-r-") as td:
        td = Path(td)
        pd.DataFrame(np.asarray(X, dtype=float), columns=item_names).to_csv(td / "X.csv", index=False, na_rep="NA")
        pd.DataFrame({"group": np.asarray(group)}).to_csv(td / "g.csv", index=False)
        (td / "anchors.txt").write_text("\n".join(anchors), encoding="utf-8")
        _run("dif", [str(td / "X.csv"), str(td / "g.csv"), str(td / "anchors.txt"), str(td / "out.json")],
             timeout=1800)
        return json.loads((td / "out.json").read_text(encoding="utf-8"))
