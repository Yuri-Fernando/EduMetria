"""Snapshots preditivos point-in-time (seção 12).

Três conceitos separados: medida psicométrica (θ com incerteza), sinal de
acompanhamento (faltas observadas) e risco preditivo (probabilidade de evento
numa janela futura). Aqui só se constrói o terceiro.

Alvo sintético da PoC (proxy demonstrativo, NÃO definição de evasão):
≥ 5 faltas não justificadas nos próximos 20 dias letivos após t0.
Sem seguimento completo → alvo ``NaN`` (censurado), nunca zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON_DAYS = 20
TARGET_MIN_UNJUSTIFIED = 5
BASE_DATE = pd.Timestamp("2026-03-02")


class LeakageError(RuntimeError):
    """Feature com available_at posterior a t0 (vazamento temporal)."""


def day_ts(day: int) -> pd.Timestamp:
    return BASE_DATE + pd.Timedelta(days=int(day))


def assert_point_in_time(feature_availability: dict[str, pd.Timestamp], t0: pd.Timestamp) -> None:
    late = {k: v for k, v in feature_availability.items() if pd.Timestamp(v) > t0}
    if late:
        raise LeakageError(
            "features indisponíveis em t0 (vazamento temporal bloqueado): "
            + ", ".join(f"{k} (available_at={v})" for k, v in late.items()))


def build_snapshot(
    attendance: pd.DataFrame,
    t0_day: int,
    scores: pd.DataFrame | None = None,
    last_day: int | None = None,
    inject_future_feature: bool = False,
) -> pd.DataFrame:
    """Uma linha por estudante em t0. ``scores``: student_ref, theta_math,
    psd_math, theta_belong, psd_belong, available_at."""
    t0 = day_ts(t0_day)
    att = attendance.copy()
    att["available_at"] = pd.to_datetime(att["available_at"])
    last_day = int(last_day or att["school_day"].max())

    known = att[att["available_at"] <= t0]
    availability: dict[str, pd.Timestamp] = {
        "unjust_abs_20d": known["available_at"].max(),
        "abs_rate_10d": known["available_at"].max(),
        "abs_trend": known["available_at"].max(),
    }
    known = known.assign(absent=1 - known["present"],
                         unjust=(1 - known["present"]) * (1 - known["absence_justified"]))
    max_known = int(known["school_day"].max())
    w20 = known[known["school_day"] > max_known - 20]
    w10 = known[known["school_day"] > max_known - 10]
    p10 = known[(known["school_day"] > max_known - 20) & (known["school_day"] <= max_known - 10)]
    g = pd.DataFrame({
        "unjust_abs_20d": w20.groupby("student_ref")["unjust"].sum(),
        "abs_rate_10d": w10.groupby("student_ref")["absent"].mean(),
        "abs_rate_prev10d": p10.groupby("student_ref")["absent"].mean(),
    })
    g["abs_trend"] = g["abs_rate_10d"] - g["abs_rate_prev10d"]
    g = g.drop(columns="abs_rate_prev10d")
    g["school_id"] = att.drop_duplicates("student_ref").set_index("student_ref")["school_id"]

    if scores is not None:
        sc = scores.set_index("student_ref")
        avail = pd.to_datetime(sc["available_at"]).max()
        for c in ("theta_math", "psd_math", "theta_belong", "psd_belong"):
            availability[c] = avail
        assert_point_in_time({k: v for k, v in availability.items() if k.startswith(("theta", "psd"))}, t0)
        g = g.join(sc[["theta_math", "psd_math", "theta_belong", "psd_belong"]])

    if inject_future_feature:
        fut = att[att["school_day"] > t0_day]
        g["future_absences"] = fut.groupby("student_ref")["present"].apply(lambda s: int((1 - s).sum()))
        availability["future_absences"] = fut["available_at"].max()

    assert_point_in_time(availability, t0)

    # alvo: janela futura (t0, t0 + H]; censurado se a janela não terminou
    end = t0_day + HORIZON_DAYS
    if end > last_day:
        g["target"] = np.nan
        g["target_status"] = "censored"
    else:
        fut = att[(att["school_day"] > t0_day) & (att["school_day"] <= end)]
        unj = ((1 - fut["present"]) * (1 - fut["absence_justified"])).groupby(fut["student_ref"]).sum()
        g["target"] = (unj.reindex(g.index).fillna(0) >= TARGET_MIN_UNJUSTIFIED).astype(float)
        g["target_status"] = "observed"
    g["t0_day"] = t0_day
    return g.reset_index().rename(columns={"index": "student_ref"})
