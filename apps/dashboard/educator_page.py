"""EduMetria Social — Visão do Educador (Streamlit).

Jornada guiada para quem não é especialista: problema → escola fictícia → medida,
sinal e incerteza → pontos para revisão → encaminhamento para revisão humana →
transparência. Lê SOMENTE ``educator_view.json`` e demais artefatos do run; não
recalcula estatística. Escrita (encaminhar, revisar) vai pela API real
(``/v1/support-cases``), que aplica RBAC, segregação de funções e auditoria — o painel
não tem caminho que contorne a revisão.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import yaml

from edumetria.reporting.educator import display_count, render_school_summary_html, signal_label

API_URL = os.environ.get("EDUMETRIA_API_URL", "http://127.0.0.1:8000")
# Perfis FICTÍCIOS do modo demonstração (configs/demo_users.yaml). Tokens públicos de demo.
PROPOSER = {"label": "coord-bruno · coordenação (SCH01, SCH02) — propõe", "token": "demo-token-coord-sch01"}
REVIEWER = {"label": "coord-clara · coordenação (SCH01) — revisa", "token": "demo-token-coord2-sch01"}
CHECKLIST = [
    "Li o intervalo de incerteza e entendi o que ele permite (e não permite) concluir.",
    "Considerei explicações alternativas: conteúdo ainda não trabalhado, item ambíguo, problema na aplicação.",
    "Confirmei que o sinal é desta escola e deste período, sem comparar com outras escolas.",
    "A ação discutida é pedagógica, não punitiva, e não rotula estudantes.",
    "Sei que esta decisão pode ser contestada e fica registrada na trilha de auditoria.",
]
KIND_LABEL = {"sinal_observado": "Sinal observado", "medida_psicometrica": "Medida psicométrica",
              "qualidade_da_medida": "Qualidade da medida"}


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# --------------------------------------------------------------------------- API
def _api(method: str, path: str, token: str, body: dict | None = None):
    """Chamada à API real. Retorna (status, json|texto). Status 0 = API indisponível."""
    import httpx
    try:
        r = httpx.request(method, f"{API_URL}{path}", json=body, timeout=10,
                          headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as exc:
        return 0, str(exc)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text


def _api_error(status: int, payload) -> None:
    if status == 0:
        st.warning(f"API indisponível em `{API_URL}`. Inicie com `uvicorn apps.api.main:app --port 8000` "
                   "(modo demo). Sem API, nada é encaminhado — o painel não grava nada sozinho.")
    elif status == 403:
        st.error(f"Permissão negada pela API (RBAC/segregação de funções): {payload}")
    elif status == 409:
        st.error(f"Conflito de versão/estado: {payload}")
    else:
        st.error(f"API respondeu {status}: {payload}")


# --------------------------------------------------------------------------- blocos
def _banner():
    st.error("**DEMONSTRAÇÃO COM DADOS SINTÉTICOS** — escolas, estudantes, respostas e frequência são artificiais. "
             "Nenhum número descreve pessoas ou escolas reais. Nenhum piloto com escolas foi realizado.")


def _tutorial():
    with st.expander("Como usar em 3 passos", expanded=False):
        st.markdown(
            "1. **Escolha uma escola fictícia** na barra lateral e veja, na aba *Escola fictícia*, a proficiência "
            "com sua incerteza e os sinais observados.\n"
            "2. **Leia os pontos para revisão**: cada um diz o que foi visto, por quê, a margem de erro e o que "
            "pode estar errado.\n"
            "3. **Encaminhe para revisão pedagógica** se fizer sentido. Outra pessoa da coordenação revisa — "
            "o sistema não decide nada sozinho.")


def _problem_tab(view: dict, school: dict):
    st.subheader("O problema")
    st.markdown(
        "Educadores com pouco tempo e poucos recursos precisam decidir **onde oferecer apoio pedagógico**. "
        "Nota média e lista de faltas, isoladas, escondem duas coisas: **o quanto a medida é incerta** e "
        "**qual parte do conteúdo** concentra a dificuldade. Isso induz conclusões erradas — para mais ou para menos.")
    st.info("**O EduMetria ajuda educadores a interpretar sinais de aprendizagem e decidir onde oferecer apoio, "
            "mostrando a incerteza dos modelos e exigindo revisão humana.**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**O que faz**")
        st.markdown("- estima proficiência em matemática com **intervalo de incerteza**;\n"
                    "- aponta eixos em que a escola acertou **menos do que ela mesma faria esperar**;\n"
                    "- mostra faltas não justificadas como **registro observado**, não como previsão;\n"
                    "- leva pontos de atenção a uma **revisão humana registrada**.")
    with c2:
        st.markdown("**O que NÃO faz**")
        st.markdown("\n".join(f"- {x}" for x in view["what_it_does_not_do"]))
    st.markdown("---")
    st.markdown("#### Caso fictício — uma escola, um problema, uma decisão humana")
    axis_lab = view["config"]["axis_labels"]
    flagged = [r for r in school["axis"] if r["signal"] == "lower_than_expected"]
    k = view["config"]["privacy"]["small_cell"]
    att = school.get("attendance") or {}
    b1, b2, b3 = st.columns(3)
    with b1.container(border=True):
        st.markdown("**Antes** *(ilustrativo)*")
        st.markdown(f"A coordenação da {school['label']} tem uma planilha com notas e faltas de "
                    f"{school['measure']['n_students']} estudantes. A média parece 'normal' e não diz onde agir "
                    "nem o quanto confiar no número.")
    with b2.container(border=True):
        st.markdown("**Durante** *(o que o software mostra)*")
        if flagged:
            r = flagged[0]
            st.markdown(f"Em **{axis_lab.get(r['axis'], r['axis'])}**, a escola acertou {r['observed_pct']:.0f}% "
                        f"contra {r['expected_pct']:.0f}% esperados pela própria proficiência — diferença além da "
                        f"margem de erro. Os demais eixos ficam dentro da incerteza.")
        else:
            st.markdown("Nenhum eixo sai da margem de erro: o software diz explicitamente que **não há sinal** — "
                        "e isso também é informação.")
        st.markdown(f"{display_count(att.get('n_with_signal', 0), k)} estudantes têm aumento recente de faltas "
                    "não justificadas (registro a conferir).")
    with b3.container(border=True):
        st.markdown("**Depois** *(decisão humana)*")
        st.markdown("A coordenação encaminha o ponto para revisão. Outra pessoa revisa com um checklist de "
                    "interpretação e decide se vale planejar apoio pedagógico no eixo. **A IA não decide sobre "
                    "nenhum estudante.**")


def _school_tab(view: dict, school: dict):
    cfg = view["config"]
    k = cfg["privacy"]["small_cell"]
    m = school["measure"]
    st.subheader(school["label"])
    st.caption("Três objetos diferentes, mostrados separadamente: medida psicométrica, sinal observado e risco "
               "preditivo. Contagens abaixo de 5 aparecem como 'menos de 5'.")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("##### 📏 Medida psicométrica — proficiência em matemática")
        st.markdown(f"{m['n_computed']} estudantes com medida · sem medida (não é zero): "
                    f"**{m['display']['n_insufficient']}**")
        dist = pd.DataFrame({"situação": ["claramente abaixo do corte", "intervalo cruza o corte",
                                          "claramente acima do corte"],
                             "estudantes": [m["n_clearly_below"], m["n_uncertain"], m["n_clearly_above"]],
                             "exibição": [m["display"]["n_clearly_below"], m["display"]["n_uncertain"],
                                          m["display"]["n_clearly_above"]]})
        dist["estudantes_plot"] = [0 if (0 < n < k) else n for n in dist["estudantes"]]
        st.altair_chart(alt.Chart(dist).mark_bar().encode(
            x=alt.X("estudantes_plot:Q", title="estudantes"),
            y=alt.Y("situação:N", sort=None, title=None),
            tooltip=["situação", "exibição"]).properties(height=140), use_container_width=True)
        st.caption(f"Corte θ = {cfg['proficiency']['reference_cut']}: {cfg['proficiency']['reference_cut_label']}. "
                   "'Claramente' = o intervalo de 90% inteiro de um lado do corte. "
                   f"Contagens: abaixo {m['display']['n_clearly_below']} · cruza {m['display']['n_uncertain']} · "
                   f"acima {m['display']['n_clearly_above']}.")
    with c2.container(border=True):
        st.markdown("##### 🔎 Sinal observado — acertos por eixo × esperado pela própria escola")
        rows = pd.DataFrame([{"eixo": cfg["axis_labels"].get(r["axis"], r["axis"]), "diferença (p.p.)": r["diff_pp"],
                              "inf": r["interval_pp"][0], "sup": r["interval_pp"][1],
                              "acertos": f"{r['observed_pct']:.0f}%", "esperado": f"{r['expected_pct']:.0f}%",
                              "leitura": signal_label(r["signal"])} for r in school["axis"]])
        if rows.empty:
            st.info("Sem dados de eixo neste run.")
        else:
            base = alt.Chart(rows).encode(y=alt.Y("eixo:N", title=None))
            chart = (base.mark_rule(strokeWidth=3).encode(x=alt.X("inf:Q", title="observado − esperado (p.p.), IC 90%"),
                                                          x2="sup:Q", color=alt.Color("leitura:N", legend=None))
                     + base.mark_point(filled=True, size=80).encode(x="diferença (p.p.):Q",
                                                                     color="leitura:N",
                                                                     tooltip=["eixo", "acertos", "esperado",
                                                                              "leitura"])
                     + alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q"))
            st.altair_chart(chart.properties(height=150), use_container_width=True)
            st.dataframe(rows[["eixo", "acertos", "esperado", "leitura"]], hide_index=True, use_container_width=True)
    c3, c4 = st.columns(2)
    att = school.get("attendance") or {}
    with c3.container(border=True):
        st.markdown("##### 📅 Sinal observado — frequência")
        if att:
            st.markdown(f"**{display_count(att['n_with_signal'], k)}** de {att['n_students']} estudantes com "
                        f"{att['threshold']}+ faltas não justificadas nos dias letivos {att['window'][0]}–"
                        f"{att['window'][1]} (dados disponíveis até o dia {att['t0_day']}).")
            st.caption(f"Faltas não justificadas: {100 * att['unjustified_rate_window']:.1f}% dos dias na janela × "
                       f"{100 * (att['unjustified_rate_baseline'] or 0):.1f}% no início do período.")
        else:
            st.info("Sem registros de frequência disponíveis.")
    with c4.container(border=True):
        st.markdown("##### 📈 Risco preditivo — avaliação do modelo (não gera prioridade)")
        rm = view["risk_model"]
        if rm.get("auc_B1_attendance_only") is not None:
            st.markdown(f"AUC só frequência: {rm['auc_B1_attendance_only']:.3f} · frequência + proficiência: "
                        f"{rm['auc_B2_attendance_plus_scores']:.3f} · ganho {rm['delta_auc_B2_minus_B1']:+.3f} "
                        f"[IC95% {rm['delta_ci95'][0]:+.3f}; {rm['delta_ci95'][1]:+.3f}]")
        st.warning(rm["message"])


def _cards_tab(view: dict, school: dict, run_id: str):
    st.subheader("Pontos para revisão pedagógica")
    st.caption("Consultivos, não prescritivos. Cada ponto mostra o que foi visto, por quê, a margem de erro e o que "
               "pode estar errado. Sugestões vêm de playbooks ILUSTRATIVOS que exigem aprovação institucional.")
    if not school["cards"]:
        st.success("Nenhum sinal acima da incerteza nesta escola. Não encaminhar nada também é uma decisão válida.")
        return
    status, existing = _api("GET", "/v1/support-cases", PROPOSER["token"])
    existing = existing if status == 200 and isinstance(existing, list) else []
    for c in school["cards"]:
        with st.container(border=True):
            st.markdown(f"**{c['title']}**  ·  `{KIND_LABEL.get(c['kind'], c['kind'])}`")
            st.markdown(c["what_we_see"])
            with st.expander("Por quê? · incerteza · o que pode estar errado"):
                st.markdown(f"**Por quê:** {c['why']}")
                st.markdown(f"**Incerteza:** {c['uncertainty']}")
                st.markdown("**Pode estar errado se:**\n" + "\n".join(f"- {x}" for x in c["could_be_wrong"]))
                st.caption("Evidências: " + ", ".join(c["evidence_refs"]))
            pb = c["suggested_discussion"]
            nxt = c.get("next_if_confirmed")
            st.markdown(f"Para discutir (não é prescrição): **{pb['id']} — {pb['name']}** "
                        f"(responsável: {pb['responsible']})"
                        + (f"; se confirmado: {nxt['id']} — {nxt['name']}" if nxt else ""))
            open_case = next((x for x in existing if x["subject_ref"] == c["subject_ref"]
                              and x["status"] not in ("declined", "cancelled", "completed")), None)
            if open_case:
                st.info(f"Já encaminhado: caso `{open_case['case_id']}` — estado **{open_case['status']}** "
                        f"(versão {open_case['version']}).")
            elif st.button("Encaminhar para revisão pedagógica", key=f"fwd-{c['card_id']}"):
                body = {"school_id": school["school_id"], "subject_ref": c["subject_ref"],
                        "reason": f"{c['title']}. {c['what_we_see']}"[:1000],
                        "evidence_refs": [f"run:{run_id}", *c["evidence_refs"]][:20]}
                s1, case = _api("POST", "/v1/support-cases", PROPOSER["token"], body)
                if s1 != 201:
                    _api_error(s1, case)
                else:
                    s2, case = _api("POST", f"/v1/support-cases/{case['case_id']}/submit", PROPOSER["token"],
                                    {"expected_version": case["version"]})
                    if s2 != 200:
                        _api_error(s2, case)
                    else:
                        st.success(f"Caso `{case['case_id']}` criado por coord-bruno e enviado para revisão "
                                   f"(estado: {case['status']}). Ninguém aprova o próprio caso.")
    st.caption(f"Perfil que propõe (demo): {PROPOSER['label']} · API: {API_URL}")


def _review_tab():
    st.subheader("Revisão pedagógica (outra pessoa da coordenação)")
    st.caption(f"Perfil revisor (demo): {REVIEWER['label']}. A API recusa que alguém aprove o próprio caso e "
               "registra cada decisão na trilha de auditoria encadeada por hash.")
    status, cases = _api("GET", "/v1/support-cases", REVIEWER["token"])
    if status != 200:
        _api_error(status, cases)
        return
    pending = [c for c in cases if c["status"] == "under_review"]
    done = [c for c in cases if c["status"] != "under_review"]
    if not pending:
        st.info("Nenhum caso aguardando revisão. Encaminhe um ponto na aba anterior.")
    for c in pending:
        with st.container(border=True):
            st.markdown(f"**{c['case_id']}** · {c['school_id']} · `{c['subject_ref']}` · proposto por "
                        f"{c['created_by']}")
            st.markdown(c["reason"])
            st.caption("Evidências: " + ", ".join(json.loads(c["evidence_refs"]) if isinstance(c["evidence_refs"], str)
                                                  else c["evidence_refs"]))
            st.markdown("**Checklist de interpretação** (obrigatório para aprovar)")
            checks = [st.checkbox(t, key=f"chk-{c['case_id']}-{i}") for i, t in enumerate(CHECKLIST)]
            rationale = st.text_area("Justificativa (mín. 10 caracteres)", key=f"rat-{c['case_id']}")
            col1, col2, col3 = st.columns(3)
            ok_text = len(rationale.strip()) >= 10
            decision = None
            if col1.button("Aprovar planejamento de apoio", key=f"ap-{c['case_id']}",
                           disabled=not (all(checks) and ok_text)):
                decision = "approve"
            if col2.button("Pedir ajustes", key=f"rq-{c['case_id']}", disabled=not ok_text):
                decision = "request_changes"
            if col3.button("Não encaminhar", key=f"dc-{c['case_id']}", disabled=not ok_text):
                decision = "decline"
            if decision:
                body = {"decision": decision, "expected_version": c["version"],
                        "rationale": f"{rationale.strip()} [checklist {sum(checks)}/{len(CHECKLIST)}]"[:2000]}
                s, res = _api("POST", f"/v1/support-cases/{c['case_id']}/reviews", REVIEWER["token"], body)
                if s == 200:
                    st.success(f"Decisão registrada: {res['status']} (versão {res['version']}).")
                    st.rerun()
                else:
                    _api_error(s, res)
    if done:
        st.markdown("**Histórico**")
        st.dataframe(pd.DataFrame(done)[["case_id", "school_id", "subject_ref", "status", "version", "created_by",
                                         "updated_at"]], hide_index=True, use_container_width=True)


def _how_tab(view: dict, run_dir: Path, root: Path):
    st.subheader("Como o modelo chegou aqui?")
    st.caption("Cada passo abaixo cita o artefato do run que o sustenta. Nenhuma explicação é gerada por LLM.")
    dq = _read_json(run_dir / "data_quality.json") or {}
    ev = _read_json(run_dir / "evidence_report.json") or {}
    prov = view["provenance"]
    steps = [
        ("1. Dados validados", f"{dq.get('n_accepted', '—'):,} respostas aceitas; {dq.get('n_quarantined', '—')} em "
                               "quarentena com motivo (data_quality.json)." if dq else "data_quality.json ausente"),
        ("2. Calibração", f"{prov['model']}; convergiu: {'sim' if prov['calibration_converged'] else 'NÃO'}; itens por "
                          f"eixo: {prov['n_items_by_axis']} (item_parameters_math6.csv)."),
        ("3. Medida", view["method"]["measure"]),
        ("4. Sinal por eixo", view["method"]["axis_signal"] + f" Neste run: {view['axis_flag_summary']['n_flagged']} "
                                                              f"de {view['axis_flag_summary']['n_tests']} "
                                                              "combinações escola × eixo com sinal."),
        ("5. Frequência", view["method"]["attendance"]),
        ("6. Risco", view["method"]["risk"] + " " + view["risk_model"]["message"]),
    ]
    for t, d in steps:
        st.markdown(f"**{t}** — {d}")
    if ev:
        st.markdown("**Mapa de evidências do instrumento** (status por seção; não existe 'score de validade')")
        st.dataframe(pd.DataFrame([{"seção": s, "status": ev[s]["status"], "resumo": ev[s]["summary"]}
                                   for s in ("content_review", "dimensionality", "ctt", "irt", "precision", "dif",
                                             "structure_invariance") if ev.get(s)]),
                     hide_index=True, use_container_width=True)
    study = _read_json(root / "reports" / "ai4good2027" / "educator_signal_study.json")
    if study:
        st.markdown("**O sinal por eixo funciona? Estudo Monte Carlo com gabarito conhecido** "
                    "(`reports/ai4good2027/educator_signal_study.json`)")
        rows = []
        for name, c in study["conditions"].items():
            s = c["summary"]
            rows.append({"condição": name, "réplicas": s["n_reps"],
                         "poder (efeito plantado detectado)": f"{100 * s['power_overall']:.0f}%"
                         if "power_overall" in s else "—",
                         "falso positivo por teste": f"{100 * s['false_flag_rate_per_test']:.2f}%",
                         "réplicas com ≥1 falso positivo": f"{100 * s['reps_with_any_false_flag']:.0f}%"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _transparency_tab(view: dict, school: dict, run_dir: Path, root: Path):
    st.subheader("Transparência")
    manifest = _read_json(run_dir / "manifest.json") or {}
    ev = _read_json(run_dir / "evidence_report.json") or {}
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**Fonte e proveniência dos dados**")
        st.markdown(f"- origem: **{view['data_origin']}** (cenário `{view['scenario_id']}`, gerador com seed "
                    f"{manifest.get('seed', '—')})\n"
                    f"- run: `{view['run_id']}`\n- commit do código: `{str(manifest.get('code_commit', '—'))[:12]}`\n"
                    f"- hash do conjunto de dados: `{str(manifest.get('dataset_hash', '—'))[:16]}…`\n"
                    f"- estado de liberação da calibração: `{manifest.get('release_status', '—')}`")
    with c2.container(border=True):
        st.markdown("**Critérios de equidade**")
        dif = ev.get("dif", {})
        st.markdown(f"- DIF (funcionamento diferencial do item) entre grupos de auditoria **artificiais** A/B: "
                    f"{dif.get('summary', 'não avaliado')}\n"
                    "- itens sinalizados vão para revisão humana; nenhum é removido automaticamente;\n"
                    "- ranking por atributo sensível é proibido; não há atributo demográfico real nesta demo;\n"
                    "- disparidades entre grupos reais só serão avaliadas se a avaliação for válida, legal e ética.")
    with st.container(border=True):
        st.markdown("**Controle humano e contestação**")
        st.markdown("- encaminhar exige perfil de coordenação com acesso à escola (RBAC pela identidade do token, "
                    "nunca pelo corpo da requisição);\n- quem propõe não pode aprovar (segregação de funções);\n"
                    "- cada transição fica na auditoria encadeada por hash; decisões podem ser revistas ou "
                    "contestadas por profissional autorizado;\n- o modelo nunca cria casos sozinho.")
    with st.container(border=True):
        st.markdown("**Limitações e usos proibidos**")
        bank = yaml.safe_load((root / "configs" / "item_bank.yaml").read_text(encoding="utf-8"))
        prohibited = sorted({u for ins in bank["instruments"] for u in ins.get("prohibited_uses", [])})
        st.markdown("\n".join(f"- {x}" for x in view["limitations"]))
        st.markdown("**Usos proibidos do instrumento:** " + "; ".join(prohibited) + ".")
    st.markdown("**Exportar resumo de uma página** (agregados, aviso sintético e ressalvas; sem dados pessoais)")
    html_doc = render_school_summary_html(view, school["school_id"], manifest)
    st.download_button("Baixar resumo (HTML)", html_doc.encode("utf-8"),
                       file_name=f"edumetria_social_resumo_{school['school_id']}_SINTETICO.html", mime="text/html")


# --------------------------------------------------------------------------- entrada
def render(run_dir: Path, root: Path):
    view = _read_json(run_dir / "educator_view.json")
    st.title("EduMetria Social · Visão do Educador")
    st.markdown("Inteligência artificial e psicometria responsável para apoiar educadores na identificação de "
                "dificuldades de aprendizagem e na priorização de apoio pedagógico.")
    _banner()
    if not view:
        st.info("Este run não tem `educator_view.json` (gerado a partir da v0.4.0). Rode "
                "`python -m edumetria.cli analyze --scenario s12` e selecione o novo run.")
        return
    _tutorial()
    schools = [s["school_id"] for s in view["schools"]]
    sid = st.sidebar.selectbox("Escola fictícia", schools, index=schools.index("SCH01") if "SCH01" in schools else 0,
                               format_func=lambda s: f"{s} · 6º ano (fictícia)")
    school = next(s for s in view["schools"] if s["school_id"] == sid)
    tabs = st.tabs(["1 · O problema", "2 · Escola fictícia", "3 · Pontos para revisão", "4 · Revisão pedagógica",
                    "5 · Como chegamos aqui", "6 · Transparência"])
    with tabs[0]:
        _problem_tab(view, school)
    with tabs[1]:
        _school_tab(view, school)
    with tabs[2]:
        _cards_tab(view, school, view["run_id"])
    with tabs[3]:
        _review_tab()
    with tabs[4]:
        _how_tab(view, run_dir, root)
    with tabs[5]:
        _transparency_tab(view, school, run_dir, root)
    st.caption(f"{view['label']} · {view['schema']} · run {view['run_id']}")
