"""Relatórios determinísticos (seção 26). Todo valor vem do contexto do run;
nada é digitado à mão. Primeira página: propósito, população, método,
achados calculados e limites; apêndice técnico com ajustes e manifestos."""

from __future__ import annotations

import base64
import html
from pathlib import Path

import pandas as pd

CSS = """
:root{--bg:#fbfbfa;--fg:#1d2330;--muted:#5b6474;--card:#ffffff;--line:#dfe3ea;--accent:#2f5d8a;--warn:#9a5b00;--bad:#b23a48}
@media (prefers-color-scheme: dark){:root{--bg:#14171c;--fg:#e6e9ef;--muted:#a3abb9;--card:#1c2027;--line:#2c323c;--accent:#7fb0e0;--warn:#e0a84f;--bad:#e27d8a}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.7rem;margin:.2em 0}h2{font-size:1.25rem;margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:.3em}
.banner{background:var(--warn);color:#fff;padding:10px 14px;border-radius:8px;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.kpi b{display:block;font-size:1.35rem;color:var(--accent)} .muted{color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:.86rem;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;white-space:nowrap}
img{max-width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}
.status{font-weight:600}.supported{color:var(--accent)}.exploratory{color:var(--warn)}.not_assessed,.insufficient{color:var(--bad)}
code{font-size:.85em}
"""


def _img(path: Path) -> str:
    if not path.exists():
        return "<p class='muted'>figura indisponível neste run</p>"
    data = base64.b64encode(path.read_bytes()).decode()
    return f"<img alt='{html.escape(path.stem)}' src='data:image/png;base64,{data}'>"


def _table(df: pd.DataFrame, cols: list[str] | None = None, fmt: int = 3) -> str:
    d = df[cols] if cols else df
    return d.to_html(index=False, float_format=lambda x: f"{x:.{fmt}f}", na_rep="—", border=0, escape=True)


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body><main>{body}</main></body></html>")


def write_reports(out: Path, ctx: dict) -> None:
    fig = out / "figures"
    ev = ctx["evidence"]
    fit_m = ctx["fit_m"]
    risk = ctx["risk"]
    alpha = ctx["ctt_test"]["math6"]["alpha"]
    b2b1 = risk["bootstrap"].get("B2_minus_B1_auc", {})
    sections = ["content_review", "response_process", "dimensionality", "ctt", "irt", "precision", "dif",
                "external_relations"]
    ev_rows = "".join(
        f"<tr><td>{s}</td><td class='status {getattr(ev, s).status.value}'>{getattr(ev, s).status.value}</td>"
        f"<td style='white-space:normal'>{html.escape(getattr(ev, s).summary)}</td></tr>" for s in sections)
    pair = ctx.get("pair") or {}
    pair_html = ""
    if pair:
        hi, lo = pair["more_uncertain"], pair["less_uncertain"]
        pair_html = (
            "<div class='card'><b>Mesma estimativa, incertezas diferentes</b> (estudantes artificiais deste run)<br>"
            f"{html.escape(str(lo['subject_ref']))}: θ={lo['theta_math']:.2f}, posterior_sd={lo['psd_math']:.2f}, "
            f"intervalo 90% [{lo['q05_math']:.2f}; {lo['q95_math']:.2f}], {int(lo['n_answered_math'])} itens respondidos<br>"
            f"{html.escape(str(hi['subject_ref']))}: θ={hi['theta_math']:.2f}, posterior_sd={hi['psd_math']:.2f}, "
            f"intervalo 90% [{hi['q05_math']:.2f}; {hi['q95_math']:.2f}], {int(hi['n_answered_math'])} itens respondidos</div>")

    models = pd.DataFrame([{**{"modelo": k}, **{m: v.get(m) for m in ("roc_auc", "pr_auc", "brier",
                                                                         "precision_at_capacity", "recall_at_capacity")}}
                           for k, v in risk["models"].items()])
    body = f"""
<div class='banner'>DADOS SINTÉTICOS — PoC experimental. Nenhum resultado se refere a estudantes, escolas ou redes reais.</div>
<h1>EduMetria — relatório técnico</h1>
<p class='muted'>run <code>{ctx['run_id']}</code> · cenário <code>{ctx['scenario']['scenario_id']}</code> —
{html.escape(ctx['scenario']['description'])} · estado: <b>{html.escape(ev.approval_state)}</b></p>
<div class='card'><b>Propósito.</b> {html.escape(ev.population_and_purpose)}<br>
<b>Método.</b> TCT; TRI 2PL (MML-EM, quadratura 61 pontos, θ~N(0,1)) com comparador 1PL; GRM para escala ordinal;
escores EAP com incerteza posterior; DIF por Mantel-Haenszel e regressão logística com BH; risco preditivo com split
temporal + escolas externas.</div>
<div class='grid'>
<div class='card kpi'><span class='muted'>Linhas aceitas / quarentena</span><b>{ctx['dq']['n_accepted']:,} / {ctx['dq']['n_quarantined']:,}</b></div>
<div class='card kpi'><span class='muted'>α (IC95%) — matemática</span><b>{alpha.get('alpha', float('nan')):.3f}</b>
<span class='muted'>[{alpha.get('ci_low', float('nan')):.3f}; {alpha.get('ci_high', float('nan')):.3f}] n={alpha['n_complete']}</span></div>
<div class='card kpi'><span class='muted'>2PL convergiu</span><b>{'sim' if fit_m.converged else 'NÃO'}</b><span class='muted'>{fit_m.iterations} ciclos EM</span></div>
<div class='card kpi'><span class='muted'>Escores / sem evidência</span><b>{ctx['n_scored']:,} / {ctx['n_insufficient']}</b></div>
<div class='card kpi'><span class='muted'>AUC B2−B1 (externo)</span><b>{b2b1.get('mean', float('nan')):+.3f}</b>
<span class='muted'>IC95% {[round(x, 3) for x in b2b1.get('ci95', [])]}</span></div>
</div>
<h2>Mapa de evidências</h2>
<table><tr><th>seção</th><th>status</th><th>resumo</th></tr>{ev_rows}</table>
<h2>Limitações e usos proibidos</h2>
<ul>{''.join(f'<li>{html.escape(x)}</li>' for x in ev.limitations)}</ul>
<p><b>Usos proibidos:</b> {html.escape('; '.join(ev.prohibited_uses))}</p>

<h2>Qualidade dos dados</h2>
<table><tr><th>código</th><th>linhas</th><th>ação</th></tr>
{''.join(f"<tr><td>{f['code']}</td><td>{f['count']}</td><td style='white-space:normal'>{html.escape(f['action'])}</td></tr>" for f in ctx['dq']['findings']) or '<tr><td colspan=3>nenhum achado</td></tr>'}
</table>

<h2>TCT</h2>
{_img(fig / 'ctt_math6.png')}
{_table(ctx['ctt_items'], ['item', 'n_valid', 'omission_rate', 'p_value', 'r_pbis_corrected', 'state', 'flags'])}

<h2>TRI — 2PL (matemática)</h2>
{_img(fig / 'icc_math6.png')}
{_img(fig / 'information_math6.png')}
{_table(fit_m.params, ['item', 'a', 'se_a', 'b', 'se_b', 'd', 'n_obs'])}
<p class='muted'>Comparação de modelos: logLik 2PL={ctx['comparison']['2pl']['loglik']:.1f}, 1PL={ctx['comparison']['1pl']['loglik']:.1f};
LR={ctx['comparison']['lr_test']['statistic']:.1f} (gl={ctx['comparison']['lr_test']['df']}), p={ctx['comparison']['lr_test']['p_value']:.2g}.
{html.escape(ctx['comparison']['note'])}</p>
<p><b>Avisos:</b> {html.escape('; '.join(fit_m.warnings) or 'nenhum')}</p>
{_img(fig / 'obs_exp_worst_item.png')}

<h2>Precisão dos escores</h2>
{_img(fig / 'theta_uncertainty_math6.png')}
{pair_html}

<h2>TRI — GRM (pertencimento)</h2>
{_table(ctx['fit_b'].params, None) if ctx['fit_b'] is not None else "<p class='bad'>GRM não ajustado neste run — ver avisos.</p>"}

<h2>Equidade — DIF</h2>
<p class='muted'>Grupo de auditoria artificial A/B. DIF condicionado ao escore; revisão humana obrigatória.</p>
{_img(fig / 'dif_math6.png')}
{_table(ctx['dif'], [c for c in ['item', 'delta_mh', 'ets_class', 'p_mh_bh', 'p_uniform_bh', 'p_nonuniform_bh', 'flagged', 'review_state'] if c in ctx['dif']])}

<h2>Relação com acompanhamento (risco preditivo)</h2>
<p class='muted'>{html.escape(risk['target_definition'])}. Split: treino t0={risk['split']['train_t0_days']} em
{len(risk['split']['train_schools'])} escolas; teste t0={risk['split']['test_t0_days']} em {len(risk['split']['test_schools'])} escolas externas.
Vazamento injetado bloqueado: {risk['leakage_check']['blocked'] if risk['leakage_check']['injected'] else 'n/a (não injetado)'}.</p>
{_table(models)}
<p class='muted'>{html.escape(risk['note'])}</p>

<h2>Verificação de software (simulação)</h2>
<p>RMSE(a)={ctx['recovery']['rmse_a']:.3f} · RMSE(b)={ctx['recovery']['rmse_b']:.3f} · corr(θ̂, θ)={ctx['recovery']['corr_theta']:.3f}</p>
<p class='muted'>{html.escape(ctx['recovery']['note'])}</p>
<p class='muted'>Manifesto: <code>manifest.json</code> · linhagem: {html.escape(str(ev.lineage))}</p>
"""
    (out / "technical_report.html").write_text(_page("EduMetria — relatório técnico", body), encoding="utf-8")

    exec_body = f"""
<div class='banner'>DADOS SINTÉTICOS — leitura executiva de uma demonstração técnica.</div>
<h1>EduMetria — resumo executivo</h1>
<p class='muted'>run <code>{ctx['run_id']}</code></p>
<div class='card'><b>O que foi medido.</b> Instrumento ilustrativo de matemática (24 itens) e escala de pertencimento
(12 itens), aplicados a população artificial. <b>Nada aqui descreve uma rede escolar real.</b></div>
<div class='card'><b>Qualidade da medida.</b> {html.escape(ev.ctt.summary)} {html.escape(ev.precision.summary)}</div>
<div class='card'><b>Equidade.</b> {html.escape(ev.dif.summary)}</div>
<div class='card'><b>Acompanhamento.</b> {html.escape(ev.external_relations.summary)}
A lista de apoio é priorizada para revisão profissional dentro da capacidade ({int(risk['capacity_share'] * 100)}% dos estudantes);
o modelo não decide quem recebe apoio.</div>
<div class='card'><b>Próximo passo.</b> Validação com especialistas e escolas (piloto), com revisão humana real,
entrevistas cognitivas e estudo de impacto antes de qualquer uso.</div>
"""
    (out / "executive_report.html").write_text(_page("EduMetria — resumo executivo", exec_body), encoding="utf-8")


def write_cards(out: Path, ctx: dict, bank: dict) -> None:
    ev = ctx["evidence"]
    inst = {i["instrument_id"]: i for i in bank["instruments"]}
    m = inst["math6"]
    (out / "instrument_card.md").write_text(f"""# Instrument card — {m['instrument_id']} v{m['version']}

- **Propósito:** {m['purpose']}
- **População:** {m['population']}
- **Construto:** {m['construct']}
- **Matriz:** 3 eixos (10/8/6) × 3 demandas (8/10/6) — `configs/item_bank.yaml`
- **Itens/versões:** 24 itens dicotômicos autorais, versão 1 cada; códigos BNCC pendentes de verificação
- **Aplicação:** simulada (cenário `{ctx['scenario']['scenario_id']}`)
- **Revisão:** pareceres simulados (`simulated_review`) — não contam como evidência humana
- **Evidências:** ver `evidence_report.json` (conteúdo={ev.content_review.status.value}, TCT={ev.ctt.status.value},
  TRI={ev.irt.status.value}, precisão={ev.precision.status.value}, DIF={ev.dif.status.value})
- **Precisão:** {ev.precision.summary}
- **Comparabilidade:** sem linking/invariância — não comparar entre versões ou grupos agregados
- **Usos permitidos:** demonstração técnica e ensino de método
- **Usos proibidos:** {'; '.join(m['prohibited_uses'])}
- **Responsáveis:** autor do projeto (engenharia); revisão psicométrica real pendente
- **Estado de validação:** {ev.approval_state}
""", encoding="utf-8")
    r = ctx["risk"]
    (out / "model_card.md").write_text(f"""# Model card — risco preditivo (B2)

- **Alvo:** {r['target_definition']}
- **Janela:** 20 dias letivos após t0; alvo censurado quando a janela não terminou (nunca negativo)
- **População:** estudantes artificiais; teste em escolas externas {r['split']['test_schools']}
- **Features:** frequência recente (20d/10d/tendência) + θ matemática/pertencimento e respectivos posterior_sd, todos point-in-time
- **Splits:** {r['split']}
- **Métricas (teste externo):** {r['models']['B2']}
- **Valor incremental B2−B1:** {r['bootstrap'].get('B2_minus_B1_auc')}
- **Calibração:** ver `risk_evaluation.json` → calibration_B2
- **Equidade preditiva por grupo artificial:** {r.get('fairness_B2')}
- **Limitações:** relação θ→faltas foi gerada pela simulação; não prova ganho em escolas reais
- **Política de uso:** priorização para revisão humana dentro da capacidade; nunca excluir estudante por score
- **Drift/revisão:** recalibração só por decisão humana (ADR-008)
""", encoding="utf-8")
    (out / "dataset_card.md").write_text(f"""# Dataset card — {ctx['scenario']['scenario_id']}

- **Origem:** 100% sintética (`edumetria.simulation.generator`), seed {ctx['scenario']['seed']}
- **Composição:** {ctx['scenario']['population']['n_students']} estudantes artificiais, {ctx['scenario']['population']['n_schools']} escolas, 2 municípios fictícios
- **Identificadores:** sintéticos; nenhum nome, CPF ou telefone real
- **Grupo de auditoria:** A/B artificial, sem significado demográfico
- **Descrição do cenário:** {ctx['scenario']['description']}
- **Qualidade:** {ctx['dq']['n_accepted']} linhas aceitas, {ctx['dq']['n_quarantined']} em quarentena
- **Licença:** CC BY 4.0 (dados e itens); código MIT
""", encoding="utf-8")
