#!/usr/bin/env python
"""Trilha B — dados públicos reais: microdados do ENEM 2023 (Inep).

    python scripts/trilha_b_enem.py --zip C:/tmp/enem/microdados_enem_2023.zip

O que faz (e o que NÃO faz):
- Lê o zip oficial do Inep sem descompactar (só colunas de Matemática).
- Escolhe o caderno regular de Matemática com mais participantes presentes,
  corrige as respostas pelo gabarito oficial e sorteia uma amostra.
- Calibra 2PL (motor nativo EduMetria) e 3PL (R/mirt, se disponível).
- Compara com os parâmetros OFICIAIS publicados em ITENS_PROVA_2023.csv
  (NU_PARAM_A/B/C) após transformação linear de escala (as escalas diferem:
  o Inep usa a escala de referência do ENEM e uma população de calibração
  distinta), e compara os escores EAP com a nota oficial NU_NOTA_MT.
- NÃO reproduz a nota oficial (o Inep usa procedimento próprio, BILOG-MG,
  população e escala de referência) e NÃO versiona microdados: só resultados
  agregados e parâmetros de itens (públicos).
Dados: microdados públicos do Inep (Lei de Acesso à Informação); anonimizados na origem.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from edumetria.irt import r_engine  # noqa: E402
from edumetria.irt.estimation import fit_2pl  # noqa: E402
from edumetria.irt.linking import mean_sigma  # noqa: E402
from edumetria.irt.scoring import eap_2pl  # noqa: E402

OUT = ROOT / "reports" / "trilha_b_enem"
COLS = ["TP_PRESENCA_MT", "CO_PROVA_MT", "TX_RESPOSTAS_MT", "TX_GABARITO_MT", "NU_NOTA_MT"]


def _member(z: zipfile.ZipFile, suffix: str) -> str:
    return next(n for n in z.namelist() if n.endswith(suffix))


def load_math(zip_path: Path, chunksize: int = 400_000) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        with z.open(_member(z, "MICRODADOS_ENEM_2023.csv")) as f:
            parts = []
            for ch in pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), sep=";", usecols=COLS, chunksize=chunksize,
                                  dtype={"CO_PROVA_MT": "Int64"}):
                parts.append(ch[ch["TP_PRESENCA_MT"] == 1])
    return pd.concat(parts, ignore_index=True)


def load_items(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        with z.open(_member(z, "ITENS_PROVA_2023.csv")) as f:
            return pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), sep=";")


def _corr(x, y) -> float:
    x = np.asarray([np.nan if v is None else v for v in x], dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def main(zip_path: Path, n_sample: int, seed: int) -> dict:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    items = load_items(zip_path)
    cache = zip_path.with_name("enem2023_mt_presentes.parquet")  # cache local (fora do repositório)
    if cache.exists():
        mt = pd.read_parquet(cache)
    else:
        mt = load_math(zip_path)
        mt.to_parquet(cache, index=False)
    print(f"presentes em Matemática: {len(mt):,} participantes")
    counts = mt["CO_PROVA_MT"].value_counts()
    booklet = int(counts.index[0])
    sub = mt[mt["CO_PROVA_MT"] == booklet].dropna(subset=["TX_RESPOSTAS_MT", "NU_NOTA_MT"])
    sub = sub.sample(min(n_sample, len(sub)), random_state=seed)
    it = items[(items["CO_PROVA"] == booklet) & (items["SG_AREA"] == "MT")].sort_values("CO_POSICAO")
    key = sub["TX_GABARITO_MT"].iloc[0]
    resp = np.array([list(s) for s in sub["TX_RESPOSTAS_MT"]])
    X = (resp == np.array(list(key))[None, :]).astype(float)
    X[resp == "*"] = np.nan  # dupla marcação
    X[resp == "."] = np.nan  # em branco (tratado como não observado — ver nota)
    names = [f"MT{p:03d}" for p in it["CO_POSICAO"]]
    official = it[["CO_POSICAO", "CO_ITEM", "NU_PARAM_A", "NU_PARAM_B", "NU_PARAM_C"]].reset_index(drop=True)
    valid = official["NU_PARAM_A"].notna().to_numpy()  # itens anulados vêm sem parâmetro
    Xv = X[:, valid]
    nv = [n for n, v in zip(names, valid) if v]
    off = official[valid].reset_index(drop=True)

    f2 = fit_2pl(Xv, nv)
    A, B = mean_sigma(off["NU_PARAM_A"].to_numpy(), off["NU_PARAM_B"].to_numpy(),
                      f2.params["a"].to_numpy(), f2.params["b"].to_numpy())
    b_link = A * f2.params["b"].to_numpy() + B
    a_link = f2.params["a"].to_numpy() / A
    eap = eap_2pl(Xv, f2.params["a"].to_numpy(), f2.params["b"].to_numpy())
    res = {
        "source": "Inep — Microdados ENEM 2023 (download.inep.gov.br), Matemática",
        "booklet_CO_PROVA_MT": booklet, "n_present_math": int(len(mt)), "n_booklet": int(counts.iloc[0]),
        "n_sample": int(len(sub)), "n_items": int(len(names)), "n_items_with_official_params": int(valid.sum()),
        "blank_policy": "branco/dupla marcação = não observado; o Inep trata diferente — fonte de discrepância",
        "python_2pl": {"converged": f2.converged, "iterations": f2.iterations,
                       "corr_b_vs_official": float(np.corrcoef(f2.params["b"], off["NU_PARAM_B"])[0, 1]),
                       "corr_a_vs_official": float(np.corrcoef(f2.params["a"], off["NU_PARAM_A"])[0, 1]),
                       "spearman_b_vs_official": float(pd.Series(f2.params["b"].to_numpy()).corr(off["NU_PARAM_B"], method="spearman")),
                       "note_a": "2PL sem assíntota inferior absorve o acerto casual nas inclinações — a não é comparável ao a do 3PL oficial",
                       "rmsd_b_after_mean_sigma": float(np.sqrt(np.mean((b_link - off["NU_PARAM_B"]) ** 2))),
                       "mean_sigma_A_B": [A, B],
                       "corr_eap_vs_nota_oficial": _corr(eap.theta, sub["NU_NOTA_MT"]),
                       "spearman_eap_vs_nota_oficial": float(pd.Series(eap.theta).corr(
                           pd.Series(sub["NU_NOTA_MT"].to_numpy()), method="spearman"))},
    }
    per_item = off.assign(item=nv, a_2pl=f2.params["a"], b_2pl=f2.params["b"], a_2pl_linked=a_link,
                          b_2pl_linked=b_link, p_value=np.nanmean(Xv, axis=0))
    if r_engine.available():
        r3 = r_engine.fit_mirt(Xv, nv, "3pl", seed=seed)
        ip = pd.DataFrame(r3["irt_pars"])
        A3, B3 = mean_sigma(off["NU_PARAM_A"].to_numpy(), off["NU_PARAM_B"].to_numpy(), ip["a"].to_numpy(), ip["b"].to_numpy())
        res["mirt_3pl"] = {"engine": r3["engine"], "converged": r3["converged"], "iterations": r3["iterations"],
                           "corr_a_vs_official": float(np.corrcoef(ip["a"], off["NU_PARAM_A"])[0, 1]),
                           "corr_b_vs_official": float(np.corrcoef(ip["b"], off["NU_PARAM_B"])[0, 1]),
                           "corr_c_vs_official": float(np.corrcoef(ip["g"], off["NU_PARAM_C"])[0, 1]),
                           "rmsd_b_after_mean_sigma": float(np.sqrt(np.mean((A3 * ip["b"] + B3 - off["NU_PARAM_B"]) ** 2))),
                           "corr_eap_vs_nota_oficial": _corr(r3["eap"], sub["NU_NOTA_MT"])}
        per_item = per_item.assign(a_3pl=ip["a"].to_numpy(), b_3pl=ip["b"].to_numpy(), c_3pl=ip["g"].to_numpy())
        degen = per_item["a_3pl"] < 0.2  # discriminação ~0 ⇒ b indeterminado (não é erro de escala)
        ok = per_item[~degen]
        res["mirt_3pl"].update({
            "spearman_b_vs_official": float(per_item["b_3pl"].corr(per_item["NU_PARAM_B"], method="spearman")),
            "spearman_a_vs_official": float(per_item["a_3pl"].corr(per_item["NU_PARAM_A"], method="spearman")),
            "spearman_c_vs_official": float(per_item["c_3pl"].corr(per_item["NU_PARAM_C"], method="spearman")),
            "degenerate_items_a_lt_0_2": per_item.loc[degen, "item"].tolist(),
            "corr_b_vs_official_excluding_degenerate": float(np.corrcoef(ok["b_3pl"], ok["NU_PARAM_B"])[0, 1]),
            "corr_a_vs_official_excluding_degenerate": float(np.corrcoef(ok["a_3pl"], ok["NU_PARAM_A"])[0, 1]),
        })
    else:
        res["mirt_3pl"] = {"status": "not_run", "reason": "Rscript + mirt indisponíveis"}
    res["elapsed_seconds"] = round(time.perf_counter() - t0, 1)
    per_item.to_csv(OUT / "item_parameters_vs_official.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    ax[0].scatter(off["NU_PARAM_B"], b_link, c="#2f5d8a")
    lim = [min(off["NU_PARAM_B"].min(), b_link.min()), max(off["NU_PARAM_B"].max(), b_link.max())]
    ax[0].plot(lim, lim, "--", c="grey")
    ax[0].set(xlabel="b oficial (Inep)", ylabel="b 2PL EduMetria (escala ligada)", title="Dificuldade: EduMetria × Inep")
    ax[1].scatter(sub["NU_NOTA_MT"], eap.theta, s=2, alpha=0.3, c="#2f5d8a")
    ax[1].set(xlabel="nota oficial de Matemática", ylabel="θ EAP 2PL EduMetria", title="Escore: EduMetria × nota oficial")
    plt.tight_layout()
    plt.savefig(OUT / "enem_vs_official.png", dpi=120)
    print(json.dumps(res, indent=2, ensure_ascii=False, default=float))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="C:/tmp/enem/microdados_enem_2023.zip")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=2023)
    a = ap.parse_args()
    main(Path(a.zip), a.n, a.seed)
