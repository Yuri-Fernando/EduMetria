"""Visão do Educador (EduMetria Social) — agregados por escola para leitura não técnica.

Gera o artefato ``educator_view.json`` de cada run. O painel só LÊ este arquivo:
nenhuma estatística é recalculada na interface (regra da seção 16).

Três objetos continuam separados, como no resto do projeto:

- **medida psicométrica** — escores EAP do 2PL com intervalo posterior;
- **sinal observado** — (a) acertos por eixo comparados ao esperado pela própria
  proficiência dos estudantes nos OUTROS eixos; (b) faltas não justificadas;
- **risco preditivo** — só aparece como avaliação do modelo; não gera prioridade.

Garantias:

- só agregados por escola (nenhum identificador de estudante sai deste módulo);
- contagens pequenas são suprimidas na exibição (``small_cell``);
- missing nunca vira zero (respostas ausentes ficam fora do observado E do esperado);
- comparação é da escola com ela mesma (desempenho nos outros eixos), não ranking
  entre escolas;
- cartões de prioridade são consultivos: ``requires_human_review`` é sempre True e
  nenhum cartão dispara ação — encaminhar exige um profissional, via API.
"""

from __future__ import annotations

import html
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import optimize, stats
from scipy.special import logsumexp

from edumetria.dif.analysis import benjamini_hochberg
from edumetria.irt.estimation import QuadratureGrid
from edumetria.irt.models import prob_2pl
from edumetria.risk.features import day_ts

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "configs" / "educator_view.yaml"
PLAYBOOKS_PATH = ROOT / "configs" / "support_playbooks.yaml"
SCHEMA = "educator_view/1.0"
SYNTHETIC_LABEL = "DEMONSTRAÇÃO COM DADOS SINTÉTICOS"

WHAT_IT_DOES_NOT_DO = [
    "Não classifica, pune nem ranqueia estudantes, turmas, escolas ou docentes.",
    "Não decide sozinho aprovação, reprovação, encaminhamento ou direito a atendimento.",
    "Não compara escolas entre si: cada eixo é comparado ao desempenho da própria escola nos outros eixos.",
    "Não usa dados reais de menores nesta demonstração — toda a população é artificial.",
    "Não transforma ausência de resposta em nota zero: sem resposta informativa não há medida.",
    "Não usa o risco preditivo para priorizar: nesta simulação ele não superou a frequência sozinha.",
    "Toda sugestão pode ser contestada e só vira caso de apoio após revisão por profissional autorizado.",
]


def load_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8"))


def load_playbooks(path: Path | None = None) -> dict[str, dict]:
    pb = yaml.safe_load((path or PLAYBOOKS_PATH).read_text(encoding="utf-8"))
    return {p["id"]: p for p in pb["playbooks"]}


def display_count(n: int, small_cell: int) -> str:
    """Supressão de célula pequena: 0 aparece como 0; 1..small_cell-1 como 'menos de N'."""
    n = int(n)
    if 0 < n < small_cell:
        return f"menos de {small_cell}"
    return str(n)


# --------------------------------------------------------------------------- sinal por eixo
def _group_prior(L_rest: np.ndarray, nodes: np.ndarray) -> tuple[float, float]:
    """Prior N(μ, σ) do grupo (escola) por máxima verossimilhança marginal nos itens de referência.

    Usar o prior N(0,1) da população inteira encolhe θ de uma escola com média diferente
    em direção à média geral e enviesa o esperado do grupo (viés clássico do EAP em
    comparações de grupos). O prior do próprio grupo remove esse viés.
    """
    def nll(par):
        lw = stats.norm.logpdf(nodes, par[0], np.exp(par[1]))
        lw = lw - logsumexp(lw)
        return -float(logsumexp(L_rest + lw[None, :], axis=1).sum())

    res = optimize.minimize(nll, x0=[0.0, 0.0], method="Nelder-Mead",
                            options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 400})
    mu, sigma = float(res.x[0]), float(np.exp(res.x[1]))
    return float(np.clip(mu, -3, 3)), float(np.clip(sigma, 0.3, 2.0))


def axis_expected_observed(X: np.ndarray, a: np.ndarray, b: np.ndarray, axis_mask: np.ndarray,
                           rest_mask: np.ndarray | None = None, prior: tuple[float, float] | str = "group",
                           n_quad: int = 61) -> pd.DataFrame:
    """Observado × esperado nos itens de um eixo, por estudante de UM grupo (escola).

    O esperado usa a posterior de θ estimada SÓ com os itens de referência (por padrão,
    todos fora do eixo — leave-axis-out), para que o próprio sinal não puxe a expectativa.
    ``prior="group"`` estima N(μ, σ) do grupo por verossimilhança marginal; uma tupla fixa o
    prior. A variância é a preditiva posterior (inclui a incerteza de θ, não só a binomial).
    Itens não respondidos ficam fora dos dois lados (missing ≠ zero).
    """
    X = np.asarray(X, dtype=float)
    O = ~np.isnan(X)
    X0 = np.nan_to_num(X, nan=0.0)
    Of = O.astype(float)
    grid = QuadratureGrid.normal(n_quad)
    P = np.clip(prob_2pl(grid.nodes, a, b), 1e-12, 1 - 1e-12)  # (K, J)
    lP, l1P = np.log(P), np.log(1 - P)
    rest = (~axis_mask) if rest_mask is None else (rest_mask & ~axis_mask)
    L_rest = X0[:, rest] @ lP[:, rest].T + (Of[:, rest] - X0[:, rest]) @ l1P[:, rest].T  # (n, K)
    mu, sigma = _group_prior(L_rest, grid.nodes) if prior == "group" else prior
    lw = stats.norm.logpdf(grid.nodes, mu, sigma)
    joint = L_rest + (lw - logsumexp(lw))[None, :]
    post = np.exp(joint - logsumexp(joint, axis=1)[:, None])
    Pm = P[:, axis_mask]
    S = Of[:, axis_mask] @ Pm.T                  # soma esperada dado θ_k (n, K)
    V = Of[:, axis_mask] @ (Pm * (1 - Pm)).T     # variância binomial dado θ_k
    expected = (post * S).sum(axis=1)
    var = (post * (V + S ** 2)).sum(axis=1) - expected ** 2
    out = pd.DataFrame({"observed": X0[:, axis_mask].sum(axis=1), "expected": expected,
                        "variance": np.clip(var, 0, None), "n_responses": Of[:, axis_mask].sum(axis=1)})
    out.attrs["prior"] = (float(mu), float(sigma))
    return out


def _one_pass(X, school_idx, axes, axis_masks, a, b, excluded, zc) -> list[dict]:
    rows = []
    for sid, idx in school_idx.items():
        Xs = X[idx]
        for axis in axes:
            mask = axis_masks[axis]
            rest = np.ones_like(mask)
            for ex in excluded.get(sid, set()) - {axis}:
                rest &= ~axis_masks[ex]
            if not (rest & ~mask).any():   # sem itens de referência: volta ao leave-axis-out simples
                rest = np.ones_like(mask)
            df = axis_expected_observed(Xs, a, b, mask, rest_mask=rest)
            n_resp = int(df["n_responses"].sum())
            if n_resp == 0:
                continue
            obs, exp, var = float(df["observed"].sum()), float(df["expected"].sum()), float(df["variance"].sum())
            sd = np.sqrt(var) if var > 0 else np.nan
            z = (obs - exp) / sd if sd and sd > 0 else np.nan
            rows.append({"school_id": sid, "axis": axis, "n_items": int(mask.sum()), "n_responses": n_resp,
                         "observed_pct": 100 * obs / n_resp, "expected_pct": 100 * exp / n_resp,
                         "diff_pp": 100 * (obs - exp) / n_resp,
                         "interval_pp": [100 * (obs - exp - zc * sd) / n_resp, 100 * (obs - exp + zc * sd) / n_resp],
                         "z": z, "p_value": float(2 * stats.norm.sf(abs(z))) if np.isfinite(z) else np.nan,
                         "group_prior": list(df.attrs["prior"]),
                         "reference_excludes": sorted(excluded.get(sid, set()) - {axis})})
    return rows


def _classify(rows: list[dict], cfg: dict) -> None:
    if not rows:
        return
    p = np.array([r["p_value"] for r in rows], dtype=float)
    q = benjamini_hochberg(np.where(np.isfinite(p), p, 1.0))
    alpha, min_resp = float(cfg["axis_signal"]["fdr_alpha"]), int(cfg["axis_signal"]["min_responses"])
    for r, qv in zip(rows, q):
        r["q_value_bh"] = float(qv)
        if r["n_responses"] < min_resp:
            r["signal"] = "insufficient_data"
        elif qv < alpha:
            r["signal"] = "lower_than_expected" if r["diff_pp"] < 0 else "higher_than_expected"
        else:
            r["signal"] = "no_signal"


def axis_signals(X, persons, item_axes, a, b, school_of, cfg, max_iter: int = 3) -> list[dict]:
    """Sinal por eixo × escola com prior do grupo e purificação iterativa.

    Purificação (como a das âncoras em DIF): um eixo sinalizado como abaixo do esperado
    sai da referência dos demais eixos da MESMA escola na passada seguinte — senão ele
    puxa a proficiência de referência para baixo e faz os outros eixos parecerem "acima
    do esperado". Para quando o conjunto de eixos sinalizados se estabiliza.
    """
    X = np.asarray(X, dtype=float)
    zc = float(stats.norm.ppf(0.5 + float(cfg["axis_signal"]["interval_level"]) / 2))
    axes = sorted(set(item_axes))
    axis_masks = {ax: np.array([x == ax for x in item_axes]) for ax in axes}
    schools = np.array([school_of[p] for p in persons])
    school_idx = {sid: np.where(schools == sid)[0] for sid in sorted(set(schools))}
    excluded: dict[str, set] = {}
    rows: list[dict] = []
    for it in range(1, max_iter + 1):
        rows = _one_pass(X, school_idx, axes, axis_masks, a, b, excluded, zc)
        _classify(rows, cfg)
        new = {}
        for r in rows:
            if r["signal"] == "lower_than_expected":
                new.setdefault(r["school_id"], set()).add(r["axis"])
        for r in rows:
            r["purification_pass"] = it
        if new == excluded:
            break
        excluded = new
    return rows


# --------------------------------------------------------------------------- frequência
def _attendance(attendance: pd.DataFrame, cfg: dict) -> dict[str, dict]:
    t0, win, thr = (int(cfg["attendance"][k]) for k in ("t0_day", "window_days", "unjustified_threshold"))
    att = attendance[attendance["available_at"] <= day_ts(t0)]  # point-in-time: só o que já existia em t0
    if att.empty:
        return {}
    last = int(att["school_day"].max())
    att = att.assign(unjust=((att["present"] == 0) & (att["absence_justified"] == 0)).astype(int))
    window = att[att["school_day"] > last - win]
    base = att[att["school_day"] <= min(20, last - win)]
    per_student = window.groupby(["school_id", "student_ref"])["unjust"].sum().reset_index()
    out = {}
    for sid, g in per_student.groupby("school_id"):
        out[sid] = {"t0_day": t0, "window": [last - win + 1, last], "threshold": thr,
                    "n_students": int(len(g)), "n_with_signal": int((g["unjust"] >= thr).sum()),
                    "unjustified_rate_window": float(window.loc[window["school_id"] == sid, "unjust"].mean()),
                    "unjustified_rate_baseline": float(base.loc[base["school_id"] == sid, "unjust"].mean())
                    if not base.empty else None}
    return out


# --------------------------------------------------------------------------- cartões
def _cards(sid: str, measure: dict, axis_rows: list[dict], att: dict | None, cfg: dict,
           playbooks: dict[str, dict]) -> list[dict]:
    k = int(cfg["privacy"]["small_cell"])
    labels = cfg["axis_labels"]
    level = int(round(100 * float(cfg["axis_signal"]["interval_level"])))
    cut = cfg["proficiency"]["reference_cut"]

    def pb(pid):
        p = playbooks.get(pid, {})
        return {"id": pid, "name": p.get("nome"), "responsible": p.get("responsavel"),
                "status": "ilustrativo — requer aprovação institucional"}

    cards = []
    for r in axis_rows:
        if r["signal"] != "lower_than_expected":
            continue
        lab = labels.get(r["axis"], r["axis"])
        lo, hi = r["interval_pp"]
        cards.append({
            "card_id": f"{sid}-axis-{r['axis']}", "kind": "sinal_observado",
            "title": f"Possível dificuldade localizada em {lab}",
            "what_we_see": (f"Os estudantes acertaram {r['observed_pct']:.0f}% dos itens de {lab}; pelo desempenho "
                            f"deles nos outros eixos, o esperado era {r['expected_pct']:.0f}% "
                            f"(diferença {r['diff_pp']:+.1f} p.p., intervalo {level}% [{lo:+.1f}; {hi:+.1f}])."),
            "why": ("A diferença continua significativa depois de corrigir para múltiplas comparações "
                    f"(Benjamini-Hochberg, q = {r['q_value_bh']:.3g}) e foi calculada com a própria escola como "
                    "referência — não é comparação com outras escolas."),
            "uncertainty": f"{r['n_responses']} respostas em {r['n_items']} itens; o intervalo mostra a margem.",
            "could_be_wrong": ["conteúdo ainda não trabalhado no período (não é falta de capacidade)",
                               "item ambíguo ou com problema de redação/acessibilidade",
                               "problema na aplicação (tempo, caderno, ordem dos itens)",
                               "falso positivo — a correção reduz, mas não elimina"],
            "suggested_discussion": pb("PB-03"),
            "subject_ref": f"turma-{sid}-{r['axis']}"[:64],
            "evidence_refs": [f"educator_view.json#schools/{sid}/axis/{r['axis']}", "item_parameters_math6.csv"],
            "requires_human_review": True, "decided_by_model": False})
    if measure["n_clearly_below"] > 0:
        cards.append({
            "card_id": f"{sid}-measure-below", "kind": "medida_psicometrica",
            "title": "Estudantes com proficiência abaixo do corte ilustrativo, com incerteza baixa",
            "what_we_see": (f"{display_count(measure['n_clearly_below'], k)} estudantes têm o intervalo de 90% da "
                            f"proficiência inteiro abaixo do corte ilustrativo (θ = {cut}). Outros "
                            f"{display_count(measure['n_uncertain'], k)} têm intervalo que cruza o corte: para "
                            "eles a medida não permite concluir."),
            "why": "Só entram estudantes cuja incerteza não alcança o corte; o restante não é tratado como sinal.",
            "uncertainty": f"incerteza posterior média da escola: {measure['mean_posterior_sd']:.2f} (escala θ)",
            "could_be_wrong": ["o corte é ilustrativo e não é padrão de desempenho",
                               "o instrumento é autoral e não tem validade estabelecida em contexto real",
                               "um único teste é uma fotografia, não uma trajetória"],
            "suggested_discussion": pb("PB-03"),
            "subject_ref": f"turma-{sid}-proficiencia",
            "evidence_refs": [f"educator_view.json#schools/{sid}/measure", "restricted/scores.csv (acesso restrito)"],
            "requires_human_review": True, "decided_by_model": False})
    if measure["n_insufficient"] > 0:
        cards.append({
            "card_id": f"{sid}-measure-missing", "kind": "qualidade_da_medida",
            "title": "Estudantes sem medida (não é nota zero)",
            "what_we_see": (f"{display_count(measure['n_insufficient'], k)} estudantes não têm resposta informativa: "
                            "o sistema não estima proficiência para eles."),
            "why": "Ausência de resposta não vira zero; tratar como zero produziria um falso sinal de dificuldade.",
            "uncertainty": "sem dados não há estimativa — nem alta nem baixa",
            "could_be_wrong": ["falta no dia da aplicação", "caderno não alcançado por tempo", "erro de registro"],
            "suggested_discussion": pb("PB-06"),
            "subject_ref": f"turma-{sid}-sem-medida",
            "evidence_refs": [f"educator_view.json#schools/{sid}/measure", "data_quality.json"],
            "requires_human_review": True, "decided_by_model": False})
    if att and att["n_with_signal"] > 0:
        cards.append({
            "card_id": f"{sid}-attendance", "kind": "sinal_observado",
            "title": "Aumento de faltas não justificadas",
            "what_we_see": (f"{display_count(att['n_with_signal'], k)} estudantes têm {att['threshold']} ou mais faltas "
                            f"não justificadas nos dias letivos {att['window'][0]}–{att['window'][1]}."),
            "why": ("É um registro observado (frequência), não uma previsão. Taxa de faltas não justificadas na "
                    f"janela: {100 * att['unjustified_rate_window']:.1f}% dos dias; no início do período: "
                    f"{100 * (att['unjustified_rate_baseline'] or 0):.1f}%."),
            "uncertainty": "registro de frequência pode ter erro de lançamento — verificar antes de agir",
            "could_be_wrong": ["justificativa não lançada", "transferência não registrada",
                               "erro de digitação no diário"],
            "suggested_discussion": pb("PB-01"),
            "next_if_confirmed": pb("PB-02"),
            "subject_ref": f"turma-{sid}-frequencia",
            "evidence_refs": [f"educator_view.json#schools/{sid}/attendance"],
            "requires_human_review": True, "decided_by_model": False})
    return cards


# --------------------------------------------------------------------------- montagem
def build_educator_view(*, run_id: str, scenario: dict, X: np.ndarray, persons: list[str], item_cols: list[str],
                        items: pd.DataFrame, a: np.ndarray, b: np.ndarray, scores: pd.DataFrame,
                        attendance: pd.DataFrame, risk: dict, converged: bool,
                        cfg: dict | None = None, playbooks: dict | None = None) -> dict:
    cfg = cfg or load_config()
    playbooks = playbooks or load_playbooks()
    axis_of = items.set_index("item_version_id")["axis"].to_dict()
    item_axes = [axis_of[c] for c in item_cols]
    school_of = scores.set_index("subject_ref")["school_id"].to_dict()
    cut = float(cfg["proficiency"]["reference_cut"])
    k = int(cfg["privacy"]["small_cell"])

    axis_rows = axis_signals(X, persons, item_axes, a, b, school_of, cfg)
    att = _attendance(attendance, cfg)

    schools = []
    for sid, g in scores.groupby("school_id"):
        ok = g[g["status_math"] == "computed"]
        th = ok["theta_math"].to_numpy(dtype=float)
        n_ok = int(len(ok))
        se = float(th.std(ddof=1) / np.sqrt(n_ok)) if n_ok > 1 else np.nan
        measure = {
            "n_students": int(len(g)), "n_computed": n_ok, "n_insufficient": int(len(g) - n_ok),
            "theta_mean": float(th.mean()) if n_ok else None,
            "theta_mean_interval_90": [float(th.mean() - 1.645 * se), float(th.mean() + 1.645 * se)]
            if n_ok > 1 else None,
            "mean_posterior_sd": float(ok["psd_math"].mean()) if n_ok else None,
            "n_clearly_below": int((ok["q95_math"] < cut).sum()),
            "n_uncertain": int(((ok["q05_math"] < cut) & (ok["q95_math"] >= cut)).sum()),
            "n_clearly_above": int((ok["q05_math"] >= cut).sum()),
        }
        measure["display"] = {key: display_count(measure[key], k)
                              for key in ("n_insufficient", "n_clearly_below", "n_uncertain", "n_clearly_above")}
        rows = [r for r in axis_rows if r["school_id"] == sid]
        schools.append({"school_id": sid, "label": f"Escola fictícia {sid} · 6º ano",
                        "measure": measure, "axis": rows, "attendance": att.get(sid),
                        "cards": _cards(sid, measure, rows, att.get(sid), cfg, playbooks)})

    models, boot = risk.get("models", {}), risk.get("bootstrap", {})
    delta = boot.get("B2_minus_B1_auc", {})
    ci = delta.get("ci95") or [None, None]
    risk_card = {
        "auc_B1_attendance_only": models.get("B1", {}).get("roc_auc"),
        "auc_B2_attendance_plus_scores": models.get("B2", {}).get("roc_auc"),
        "delta_auc_B2_minus_B1": delta.get("mean"), "delta_ci95": ci,
        "target_definition": risk.get("target_definition"),
        "used_for_prioritization": False,
        "message": ("O modelo de risco foi avaliado em escolas externas, mas acrescentar a proficiência à frequência "
                    "não melhorou a previsão de forma comprovada nesta simulação (o intervalo do ganho inclui zero). "
                    "Por isso o risco preditivo NÃO gera prioridades nesta visão."
                    if ci[0] is not None and ci[0] <= 0 <= ci[1] else
                    "O risco preditivo é exibido apenas como avaliação do modelo e não gera prioridades nesta visão."),
    }
    n_items_by_axis = {str(ax): int(n) for ax, n in pd.Series(item_axes).value_counts().items()}
    flags = [r for r in axis_rows if r.get("signal") in ("lower_than_expected", "higher_than_expected")]
    return {
        "schema": SCHEMA, "run_id": run_id, "scenario_id": scenario.get("scenario_id"),
        "data_origin": scenario.get("data_origin", "synthetic"), "label": SYNTHETIC_LABEL,
        "config": cfg,
        "provenance": {"model": "2PL MML-EM (motor nativo), escores EAP com prior N(0,1)",
                       "calibration_converged": bool(converged), "n_items_by_axis": n_items_by_axis,
                       "n_students": int(len(scores)), "n_schools": int(scores["school_id"].nunique())},
        "method": {
            "measure": ("Proficiência estimada por TRI (2PL) com escore EAP; cada estudante tem um intervalo de 90% "
                        "da posterior. A escola mostra quantos estudantes ficam claramente abaixo, claramente acima "
                        "ou com intervalo cruzando o corte ilustrativo."),
            "axis_signal": ("Para cada eixo, o esperado de acertos vem da proficiência estimada só com os itens dos "
                            "OUTROS eixos (leave-axis-out), com prior da própria escola estimado por verossimilhança "
                            "marginal (evita puxar a escola para a média geral) e variância preditiva posterior. "
                            "Eixos sinalizados como baixos saem da referência dos demais eixos da mesma escola "
                            "(purificação iterativa, como em DIF). A diferença observado − esperado é testada com "
                            "correção de Benjamini-Hochberg sobre todas as escolas × eixos."),
            "attendance": ("Contagem de faltas não justificadas na janela anterior a t0, usando só registros "
                           "disponíveis em t0 (point-in-time)."),
            "risk": "Avaliação dos modelos B0–B3 em escolas externas (ver risk_evaluation.json).",
        },
        "axis_flag_summary": {"n_tests": len(axis_rows), "n_flagged": len(flags),
                              "flagged": [(r["school_id"], r["axis"], r["signal"]) for r in flags]},
        "risk_model": risk_card,
        "schools": schools,
        "what_it_does_not_do": WHAT_IT_DOES_NOT_DO,
        "limitations": [
            "População, itens e frequência são sintéticos; nenhum número descreve escolas reais.",
            "Itens autorais e ilustrativos, sem revisão de especialistas reais nem entrevista cognitiva.",
            "Os resultados podem mudar com outros dados; a incerteza mostrada é parte do resultado.",
            "Nenhum piloto com escolas, educadores reais ou estudo de impacto foi realizado.",
        ],
    }


# --------------------------------------------------------------------------- exportação
def render_school_summary_html(view: dict, school_id: str, manifest: dict | None = None) -> str:
    """Resumo de uma página, só agregados, com aviso sintético e ressalvas."""
    s = next(x for x in view["schools"] if x["school_id"] == school_id)
    cfg = view["config"]
    labels = cfg["axis_labels"]
    e = html.escape
    m = s["measure"]
    axis_rows = "".join(
        f"<tr><td>{e(labels.get(r['axis'], r['axis']))}</td><td>{r['observed_pct']:.0f}%</td>"
        f"<td>{r['expected_pct']:.0f}%</td><td>{r['diff_pp']:+.1f} [{r['interval_pp'][0]:+.1f}; "
        f"{r['interval_pp'][1]:+.1f}]</td><td>{e(_signal_label(r['signal']))}</td></tr>" for r in s["axis"])
    cards = "".join(
        f"<li><b>{e(c['title'])}</b> — {e(c['what_we_see'])} <i>Para discutir (não é prescrição):</i> "
        f"{e(c['suggested_discussion']['id'])} {e(c['suggested_discussion']['name'] or '')}.</li>" for c in s["cards"])
    att = s.get("attendance") or {}
    prov = (f"run {e(view['run_id'])} · origem dos dados: {e(view['data_origin'])}"
            + (f" · commit {e(str(manifest.get('code_commit', ''))[:12])} · seed {manifest.get('seed')}"
               if manifest else ""))
    limits = "".join(f"<li>{e(x)}</li>" for x in view["what_it_does_not_do"] + view["limitations"])
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>EduMetria Social — resumo {e(school_id)} (sintético)</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#1d2433}}
.banner{{background:#fff3cd;border:2px solid #b8860b;padding:10px 14px;font-weight:700}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd;padding:4px 8px;text-align:left}}
small{{color:#555}}</style></head><body>
<div class="banner">{e(view['label'])} — nenhum número descreve estudantes, escolas ou redes reais.</div>
<h1>EduMetria Social · {e(s['label'])}</h1>
<p><small>{prov}</small></p>
<h2>Medida psicométrica (proficiência em matemática)</h2>
<p>{m['n_computed']} estudantes com medida · sem medida: {e(m['display']['n_insufficient'])} ·
claramente abaixo do corte ilustrativo: {e(m['display']['n_clearly_below'])} ·
intervalo cruza o corte: {e(m['display']['n_uncertain'])} · claramente acima: {e(m['display']['n_clearly_above'])}.
<br><small>Corte: θ = {cfg['proficiency']['reference_cut']} — {e(cfg['proficiency']['reference_cut_label'])}.</small></p>
<h2>Sinal observado por eixo (comparação com a própria escola)</h2>
<table><tr><th>Eixo</th><th>Acertos</th><th>Esperado</th><th>Diferença p.p. [IC 90%]</th><th>Leitura</th></tr>
{axis_rows}</table>
<h2>Sinal observado — frequência</h2>
<p>{e(display_count(att.get('n_with_signal', 0), cfg['privacy']['small_cell']))} estudantes com
{att.get('threshold', '—')}+ faltas não justificadas na janela {att.get('window', '—')}.</p>
<h2>Risco preditivo</h2><p>{e(view['risk_model']['message'])}</p>
<h2>Pontos para revisão pedagógica (consultivos)</h2><ul>{cards or '<li>nenhum sinal acima da incerteza</li>'}</ul>
<h2>O que este resumo não faz · limitações</h2><ul>{limits}</ul>
<p><small>Gerado a partir de educator_view.json ({e(view['schema'])}). Agregados apenas; contagens abaixo de
{cfg['privacy']['small_cell']} suprimidas.</small></p></body></html>"""


def _signal_label(signal: str) -> str:
    return {"lower_than_expected": "abaixo do esperado (além da incerteza)",
            "higher_than_expected": "acima do esperado (além da incerteza)",
            "no_signal": "dentro da incerteza — não interpretar",
            "insufficient_data": "dados insuficientes"}.get(signal, signal)


signal_label = _signal_label
