"""Sinal por eixo da Visão do Educador: encontra o que foi plantado e não inventa onde não há.

Uma réplica por condição com a seed do cenário (o estudo com 100 réplicas fica em
scripts/educator_signal_study.py → reports/ai4good2027/educator_signal_study.json).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from educator_signal_study import one_rep  # noqa: E402

from edumetria.reporting.educator import load_config  # noqa: E402


def test_planted_localized_difficulty_is_detected():
    r = one_rep("s12", 20260928, load_config())
    assert r["converged"]
    assert r["hits"] == r["n_planted"] == 2
    assert r["n_false_flags"] <= 1


def test_no_planted_effect_yields_at_most_rare_flags():
    r = one_rep("s0", 20260928, load_config())
    assert r["n_planted"] == 0
    assert r["n_false_flags"] <= 1
