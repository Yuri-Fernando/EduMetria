"""Figuras geradas a partir dos artefatos do run (gráfico e tabela usam a
mesma fonte — teste T27). Paleta neutra, legível em impressão."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from edumetria.irt.models import prob_2pl, se_from_information, total_information  # noqa: E402

BLUE, ORANGE, GREY, RED = "#2f5d8a", "#d9822b", "#8a8f98", "#b23a48"


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def icc_plot(params: pd.DataFrame, path: Path, highlight: list[str] | None = None) -> Path:
    th = np.linspace(-4, 4, 200)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    P = prob_2pl(th, params["a"].to_numpy(), params["b"].to_numpy())
    for j, name in enumerate(params["item"]):
        hl = highlight and name in highlight
        ax.plot(th, P[:, j], color=RED if hl else BLUE, alpha=0.9 if hl else 0.25, lw=2 if hl else 1,
                label=name if hl else None)
    ax.set(xlabel="θ (escala interna)", ylabel="P(acerto)", title="Curvas características dos itens — 2PL")
    if highlight:
        ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return _save(fig, path)


def information_plot(params: pd.DataFrame, path: Path) -> Path:
    th = np.linspace(-4, 4, 200)
    info = total_information(th, params["a"].to_numpy(), params["b"].to_numpy())
    fig, ax1 = plt.subplots(figsize=(7, 4.2))
    ax1.plot(th, info, color=BLUE, lw=2, label="Informação do teste")
    ax1.set(xlabel="θ", ylabel="Informação")
    ax2 = ax1.twinx()
    ax2.plot(th, se_from_information(info), color=ORANGE, lw=2, ls="--", label="SE ≈ 1/√I(θ)")
    ax2.set_ylabel("SE aproximado")
    ax2.set_ylim(0, 1.5)
    fig.legend(loc="upper right", fontsize=8)
    ax1.set_title("Informação do teste e erro-padrão aproximado")
    ax1.grid(alpha=0.3)
    return _save(fig, path)


def theta_uncertainty_plot(scores: pd.DataFrame, path: Path) -> Path:
    ok = scores["status"] == "computed"
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.scatter(scores.loc[ok, "theta_eap"], scores.loc[ok, "posterior_sd"], s=6, alpha=0.35, color=BLUE)
    ax.set(xlabel="θ EAP", ylabel="posterior_sd", title="Estimativa × incerteza posterior (EAP, prior N(0,1))")
    ax.grid(alpha=0.3)
    return _save(fig, path)


def dif_plot(dif: pd.DataFrame, path: Path) -> Path:
    d = dif.dropna(subset=["delta_mh"]).copy()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    colors = [RED if f else GREY for f in d.get("flagged", [False] * len(d))]
    ax.bar(d["item"], d["delta_mh"], color=colors)
    for y in (-1.5, -1.0, 1.0, 1.5):
        ax.axhline(y, color="black", lw=0.6, ls=":" if abs(y) == 1.0 else "--")
    ax.set(ylabel="Δ MH (ETS)", title="DIF Mantel-Haenszel por item (vermelho = sinalizado p/ revisão)")
    ax.tick_params(axis="x", rotation=90, labelsize=7)
    return _save(fig, path)


def obs_exp_plot(oe: pd.DataFrame, item: str, path: Path) -> Path:
    g = oe[oe["item"] == item]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(g["theta_mean"], g["expected"], "-o", color=BLUE, label="esperado (2PL)")
    ax.plot(g["theta_mean"], g["observed"], "s", color=ORANGE, label="observado")
    ax.set(xlabel="θ médio da faixa", ylabel="proporção de acerto", title=f"Observado × esperado — {item}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return _save(fig, path)


def ctt_plot(ctt: pd.DataFrame, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.scatter(ctt["p_value"], ctt["r_pbis_corrected"], color=BLUE)
    for _, r in ctt.iterrows():
        ax.annotate(r["item"].split("-")[1], (r["p_value"], r["r_pbis_corrected"]), fontsize=7)
    ax.axhline(0.15, color=GREY, ls=":")
    ax.set(xlabel="proporção de acerto (p)", ylabel="r ponto-bisserial corrigida",
           title="TCT — dificuldade × discriminação")
    ax.grid(alpha=0.3)
    return _save(fig, path)
