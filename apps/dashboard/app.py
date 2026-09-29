"""Painel EduMetria (Streamlit) — lê SOMENTE artefatos de runs reais.

A UI não recalcula estatísticas nem aprova nada (seção 16): escrita é da API.
Estados obrigatórios: vazio, falha, bloqueado, dados insuficientes e aviso de
dados sintéticos em todas as páginas.

Rodar:  PYTHONPATH=src streamlit run apps/dashboard/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from edumetria.integrations.adapters import INTEGRATIONS  # noqa: E402
from edumetria.registry.store import Actor, Store  # noqa: E402

RUNS = ROOT / "runs"
DEMO = ROOT / "reports" / "demo_runs"

st.set_page_config(page_title="EduMetria", layout="wide")
st.warning("**DADOS SINTÉTICOS — PoC experimental.** Nenhum valor descreve estudantes, escolas ou redes reais. "
           "Projeto autoral; não é produto oficial de nenhuma instituição.")


def _runs() -> list[Path]:
    found = sorted(list(RUNS.glob("run-*")) + list(DEMO.glob("run-*")), key=lambda p: p.name, reverse=True)
    return found


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


runs = _runs()
if not runs:
    st.info("Nenhum run encontrado. Execute `edumetria analyze --scenario s2` para gerar um run real.")
    st.stop()

run_dir = st.sidebar.selectbox("Run", runs, format_func=lambda p: p.name)
status = _read_json(run_dir / "run_status.json") or {"status": "unknown"}
st.sidebar.markdown(f"**Estado do run:** `{status['status']}`")
if status["status"] == "blocked_by_data_quality":
    st.error("Run bloqueado pela validação de dados (versão de item desconhecida). Nenhum resultado foi calculado.")
    dq = _read_json(run_dir / "data_quality.json")
    if dq:
        st.dataframe(pd.DataFrame(dq["findings"]))
    st.stop()
if status["status"] != "succeeded":
    st.error(f"Análise falhou ({status.get('error_code', 'sem código')}). Nada é exibido como resultado atual.")
    st.stop()

ev = _read_json(run_dir / "evidence_report.json")
manifest = _read_json(run_dir / "manifest.json")
tabs = st.tabs(["Visão geral", "Banco e revisão", "Dados e qualidade", "Laboratório psicométrico",
                "Equidade", "Acompanhamento", "Relatórios", "Operação e auditoria"])

with tabs[0]:
    st.subheader("Visão geral")
    c1, c2, c3, c4 = st.columns(4)
    dq = _read_json(run_dir / "data_quality.json")
    c1.metric("Linhas aceitas", f"{dq['n_accepted']:,}")
    c2.metric("Em quarentena", f"{dq['n_quarantined']:,}")
    c3.metric("Origem dos dados", manifest["data_origin"])
    c4.metric("Estado de liberação", manifest["release_status"])
    st.caption(f"Instrumentos: {', '.join(manifest['instrument_versions'])} · seed {manifest['seed']} · "
               f"commit {manifest['code_commit'][:12]}")
    st.markdown("**Mapa de evidências** (cada seção com status próprio — não existe 'score de validade')")
    st.dataframe(pd.DataFrame([{"seção": k, "status": ev[k]["status"], "resumo": ev[k]["summary"]}
                               for k in ("content_review", "response_process", "dimensionality", "ctt", "irt",
                                         "precision", "dif", "external_relations")]), use_container_width=True)

with tabs[1]:
    st.subheader("Matriz, banco de itens e comitê (pareceres SIMULADOS)")
    cv = _read_json(run_dir / "content_validity.json")
    st.caption(f"S-CVI/Ave = {cv['s_cvi_ave']:.2f} · origem: {cv['evidence_origin']} · conta como evidência "
               f"humana: {cv['counts_as_human_evidence']}")
    st.dataframe(pd.DataFrame(cv["items"])[["item_id", "n_judges", "i_cvi_relevance", "aiken_v_alignment",
                                            "needs_review", "evidence_origin"]], use_container_width=True)
    st.info("Itens para revisão: " + (", ".join(cv["items_needing_review"]) or "nenhum")
            + ". Limiar é configurável; nenhum item é 'validado' por ultrapassar número.")

with tabs[2]:
    st.subheader("Aplicações e qualidade dos dados")
    st.json(dq["omission_by_reason"])
    st.dataframe(pd.DataFrame(dq["findings"]) if dq["findings"] else pd.DataFrame([{"achados": "nenhum"}]))

with tabs[3]:
    st.subheader("Laboratório psicométrico")
    sub = st.tabs(["TCT", "TRI 2PL", "Precisão", "Diagnósticos", "GRM"])
    with sub[0]:
        st.image(str(run_dir / "figures" / "ctt_math6.png"))
        st.dataframe(pd.read_csv(run_dir / "ctt_items.csv"), use_container_width=True)
    with sub[1]:
        st.image(str(run_dir / "figures" / "icc_math6.png"))
        st.dataframe(pd.read_csv(run_dir / "item_parameters_math6.csv"), use_container_width=True)
    with sub[2]:
        st.image(str(run_dir / "figures" / "information_math6.png"))
        st.image(str(run_dir / "figures" / "theta_uncertainty_math6.png"))
    with sub[3]:
        diag = _read_json(run_dir / "fit_diagnostics.json")
        st.json({"convergiu": diag["math6"]["converged"], "ciclos": diag["math6"]["iterations"],
                 "avisos": diag["math6"]["warnings"], "Q3": diag["math6"]["q3_flags"][:10],
                 "dimensionalidade": diag["math6"]["dimensionality"],
                 "comparação 1PL×2PL": diag["math6"]["model_comparison"]})
        st.image(str(run_dir / "figures" / "obs_exp_worst_item.png"))
    with sub[4]:
        p = run_dir / "item_parameters_belong6.csv"
        st.dataframe(pd.read_csv(p)) if p.exists() else st.error("GRM não ajustado neste run.")

with tabs[4]:
    st.subheader("Equidade e comparabilidade — grupo de auditoria ARTIFICIAL A/B")
    st.image(str(run_dir / "figures" / "dif_math6.png"))
    dif = pd.read_csv(run_dir / "dif_report.csv")
    st.dataframe(dif, use_container_width=True)
    st.caption("DIF é condicionado ao escore; diferença de médias não é DIF. Achados vão para revisão humana; "
               "nenhum item é removido automaticamente. Ranking por atributo sensível é proibido.")

with tabs[5]:
    st.subheader("Acompanhamento escolar — medida, sinal e risco são objetos distintos")
    risk = _read_json(run_dir / "risk_evaluation.json")
    c1, c2 = st.columns(2)
    c1.markdown("**Risco preditivo (modelos)**")
    c1.dataframe(pd.DataFrame(risk["models"]).T[["roc_auc", "pr_auc", "brier", "precision_at_capacity",
                                                  "recall_at_capacity"]])
    c2.markdown("**Valor incremental B2 − B1 (bootstrap por escola)**")
    c2.json(risk["bootstrap"].get("B2_minus_B1_auc", {}))
    st.caption(risk["target_definition"] + ". " + risk["note"])
    st.markdown("**Equidade preditiva por grupo artificial**")
    st.dataframe(pd.DataFrame(risk.get("fairness_B2", [])))
    st.info("O modelo não decide quem recebe apoio. Casos são criados e aprovados por profissionais via API "
            "(`/v1/support-cases`), com revisão persistente e segregação de funções.")

with tabs[6]:
    st.subheader("Relatórios e evidências")
    for name in ("technical_report.html", "executive_report.html", "instrument_card.md", "model_card.md",
                 "dataset_card.md", "manifest.json"):
        p = run_dir / name
        if p.exists():
            st.download_button(f"Baixar {name}", p.read_bytes(), file_name=name)

with tabs[7]:
    st.subheader("Operação e auditoria")
    st.markdown("**Integrações** (estado declarado, nunca verde por import)")
    st.dataframe(pd.DataFrame(INTEGRATIONS).T)
    db = RUNS / "edumetria.db"
    if db.exists():
        store = Store(db)
        aud = Actor("dashboard-auditor", "demo-tenant", "auditor")
        st.metric("Hash-chain da auditoria íntegra", "sim" if store.verify_audit_chain() else "NÃO")
        st.dataframe(pd.DataFrame(store.list_audit(aud)))
        st.dataframe(pd.DataFrame(store.list_calibrations(aud)))
    else:
        st.info("Banco operacional ainda não criado (inicie a API e o worker para gerar jobs e auditoria).")
    st.json({"run_log": str(run_dir / "run.log"), "manifest_artifacts": len(manifest["artifacts"])})
