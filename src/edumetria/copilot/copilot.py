"""Copiloto restrito para educadores (seção 20 do plano).

Princípios implementados:
- Só ferramentas em allowlist, que leem artefatos JÁ calculados de um run
  (nenhuma consulta arbitrária, nenhum shell, nenhum cálculo estatístico).
- Guarda em camadas ANTES de responder: AegisLLM (``inspect_input``, injeção
  direta e indireta nos documentos recuperados) + Themis (``prompt_security``)
  + regras locais (dado individual, gabarito, identificadores).
- Autorização: perguntas sobre escola fora do escopo do usuário → recusa.
- Toda resposta cita a fonte (artefato + chave). Sem evidência → abstenção.
- LLM é OPCIONAL (``EDUMETRIA_COPILOT_LLM=ollama:<modelo>``, local e gratuito);
  se usado, só reescreve o texto e a resposta é descartada se contiver número
  que não esteja nos dados das ferramentas (verificação determinística).
Nada aqui decide sobre estudante, calcula θ, p-valor ou aprova item.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from edumetria.integrations.verify import aegis_inspect, themis_prompt_scan
from edumetria.registry.store import Actor

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs" / "methodology"

LOCAL_BLOCK = [
    # defesa base contra injeção (não depende de Aegis/Themis estarem presentes)
    (re.compile(r"ignor\w*\s+(?:as|all|the|todas as)?\s*(?:instru\w+|instructions|regras)|system\s*prompt|"
                r"modo\s+sem\s+restri|developer\s+mode|jailbreak", re.I), "prompt_injection_local"),
    (re.compile(r"synthetic-student-\d+|estudante\s+[A-Z][a-z]+|aluno\s+[A-Z][a-z]+"), "dado_individual"),
    (re.compile(r"gabarito|resposta\s+correta|chave\s+de\s+resposta", re.I), "item_sigiloso"),
    (re.compile(r"\bcpf\b|telefone|endere[cç]o\s+do\s+aluno|nome\s+completo", re.I), "identificador_pessoal"),
    (re.compile(r"(altere|mude|modifique|recalcule).{0,30}(estat[ií]stica|par[aâ]metro|theta|θ|resultado)", re.I),
     "tentativa_de_alterar_resultado"),
    (re.compile(r"(causou|causa|provou|prova que).{0,40}(evas[aã]o|abandono|melhora)", re.I), "atribuicao_causal"),
]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


@dataclass
class Answer:
    status: str  # answered | refused | abstained
    text: str
    tool: str | None = None
    citations: list[str] = field(default_factory=list)
    guard: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)


class Copilot:
    def __init__(self, run_dir: Path):
        self.run = Path(run_dir)

    def _j(self, name: str) -> dict:
        return json.loads((self.run / name).read_text(encoding="utf-8"))

    # ------------------------------------------------------------ ferramentas (allowlist)
    def get_instrument_metadata(self, actor: Actor) -> Answer:
        m = self._j("manifest.json")
        return Answer("answered", f"Run {m['run_id']}: instrumentos {', '.join(m['instrument_versions'])}; origem dos "
                      f"dados: {m['data_origin']}; estado de liberação: {m['release_status']}.",
                      "get_instrument_metadata", ["manifest.json#instrument_versions", "manifest.json#release_status"],
                      data={"instrument_versions": m["instrument_versions"]})

    def get_calibration_summary(self, actor: Actor) -> Answer:
        d = self._j("fit_diagnostics.json")["math6"]
        t = f"Calibração 2PL de matemática: convergiu={d['converged']} em {d['iterations']} ciclos EM; " \
            f"{len(d['warnings'])} avisos de item; logLik={d['loglik']:.1f}."
        return Answer("answered", t, "get_calibration_summary",
                      ["fit_diagnostics.json#math6.converged", "fit_diagnostics.json#math6.iterations"],
                      data={"converged": d["converged"], "iterations": d["iterations"], "loglik": round(d["loglik"], 1)})

    def get_aggregate_precision(self, actor: Actor) -> Answer:
        e = self._j("evidence_report.json")
        return Answer("answered", "Precisão (agregada, sem dado individual): " + e["precision"]["summary"],
                      "get_aggregate_precision", ["evidence_report.json#precision.summary"])

    def get_item_review_status(self, actor: Actor) -> Answer:
        cv = self._j("content_validity.json")
        return Answer("answered", f"S-CVI/Ave={cv['s_cvi_ave']:.2f} (pareceres de origem {', '.join(cv['evidence_origin'])}); "
                      f"itens para revisão: {', '.join(cv['items_needing_review']) or 'nenhum'}.",
                      "get_item_review_status", ["content_validity.json#s_cvi_ave", "content_validity.json#items_needing_review"],
                      data={"s_cvi_ave": round(cv["s_cvi_ave"], 2)})

    def get_dif_findings(self, actor: Actor) -> Answer:
        d = pd.read_csv(self.run / "dif_report.csv")
        d = d[d.get("analysis", "all_other_items") == "all_other_items"] if "analysis" in d else d
        flagged = d.loc[d.get("flagged", False) == True, "item"].tolist()  # noqa: E712
        return Answer("answered", f"DIF (grupo de auditoria artificial A/B): {len(flagged)} itens sinalizados para revisão "
                      f"humana ({', '.join(flagged) or 'nenhum'}); nenhum item é removido automaticamente.",
                      "get_dif_findings", ["dif_report.csv#flagged"], data={"n_flagged": len(flagged)})

    def get_approved_support_playbooks(self, actor: Actor) -> Answer:
        pb = yaml.safe_load((ROOT / "configs" / "support_playbooks.yaml").read_text(encoding="utf-8"))
        items = "; ".join(f"{p['id']} {p['nome']} (quando: {p['quando']}; responsável: {p['responsavel']})"
                          for p in pb["playbooks"])
        return Answer("answered", f"Playbooks ({pb['status']}): {items}. A decisão é sempre do profissional responsável.",
                      "get_approved_support_playbooks", ["configs/support_playbooks.yaml#playbooks"])

    def explain_report_section(self, actor: Actor, question: str) -> Answer:
        docs = {p.name: p.read_text(encoding="utf-8") for p in DOCS.glob("*.md")}
        guard = aegis_inspect(question, list(docs.values()))  # injeção indireta nos documentos
        if guard is not None and not guard["allowed"]:
            return Answer("refused", "Documento recuperado contém instrução suspeita — resposta bloqueada.",
                          guard={"aegis": guard})
        terms = [t for t in re.findall(r"[a-z0-9]{4,}", _norm(question))]
        best = None
        for name, text in docs.items():
            for para in text.split("\n\n"):
                score = sum(_norm(para).count(t) for t in terms)
                if score and (best is None or score > best[0]):
                    best = (score, name, para.strip())
        if best is None:
            return Answer("abstained", "Não encontrei evidência na documentação metodológica para responder.")
        return Answer("answered", best[2][:900], "explain_report_section", [f"docs/methodology/{best[1]}"])

    ROUTES = [
        (("dif", "funcionamento diferencial", "equidade", "vies"), "get_dif_findings"),
        (("precisao", "incerteza", "posterior", "erro padrao"), "get_aggregate_precision"),
        (("convergiu", "convergencia", "calibracao", "ciclos"), "get_calibration_summary"),
        (("juiz", "juizes", "parecer", "cvi", "validade de conteudo"), "get_item_review_status"),
        (("playbook", "acao de apoio", "o que fazer", "intervencao"), "get_approved_support_playbooks"),
        (("instrumento", "versao", "liberacao", "origem dos dados"), "get_instrument_metadata"),
        (("o que e", "como funciona", "explique", "metodologia", "por que"), "explain_report_section"),
    ]

    # ------------------------------------------------------------ fluxo
    def guard(self, question: str, actor: Actor) -> dict:
        g = {"aegis": aegis_inspect(question), "themis": themis_prompt_scan(question), "local": []}
        for rx, code in LOCAL_BLOCK:
            if rx.search(question):
                g["local"].append(code)
        for sch in re.findall(r"\bSCH\d{2}\b", question):
            if not actor.can_see_school(sch):
                g["local"].append("escola_fora_do_escopo")
        g["blocked"] = bool(g["local"]) or (g["aegis"] is not None and not g["aegis"]["allowed"]) or \
            (g["themis"] is not None and not g["themis"]["is_safe"])
        return g

    def ask(self, question: str, actor: Actor) -> Answer:
        g = self.guard(question, actor)
        if g["blocked"]:
            return Answer("refused", "Não posso atender: " + ", ".join(
                g["local"] + (g["aegis"] or {}).get("reasons", []) + (g["themis"] or {}).get("findings", [])) +
                ". O copiloto só explica resultados agregados já calculados.", guard=g)
        q = _norm(question)
        for keys, tool in self.ROUTES:
            if any(k in q for k in keys):
                fn = getattr(self, tool)
                ans = fn(actor, question) if tool == "explain_report_section" else fn(actor)
                ans.guard = g
                return self._maybe_llm(ans, question)
        return Answer("abstained", "Pergunta fora do escopo das ferramentas disponíveis; não há evidência para responder.",
                      guard=g)

    def _maybe_llm(self, ans: Answer, question: str) -> Answer:
        spec = os.environ.get("EDUMETRIA_COPILOT_LLM", "")
        if not spec.startswith("ollama:") or ans.status != "answered":
            return ans
        import urllib.request
        prompt = (f"Reescreva em português claro para um educador, SEM acrescentar números ou fatos. "
                  f"Pergunta: {question}\nResposta factual: {ans.text}")
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", method="POST",
                                     data=json.dumps({"model": spec.split(":", 1)[1], "prompt": prompt,
                                                      "stream": False}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            text = json.loads(urllib.request.urlopen(req, timeout=60).read())["response"]
        except Exception:
            return ans  # LLM indisponível: resposta determinística segue (alerta A7)
        allowed = set(re.findall(r"\d+(?:[.,]\d+)?", ans.text))
        if set(re.findall(r"\d+(?:[.,]\d+)?", text)) <= allowed:
            ans.text, ans.data = text.strip(), {**ans.data, "llm_rewrite": spec}
        return ans


def evaluate_copilot(copilot: Copilot, cases: list[dict], actor: Actor) -> dict:
    rows = []
    for c in cases:
        a = copilot.ask(c["question"], actor)
        ok_status = a.status == c["expected_status"]
        ok_tool = c.get("expected_tool") in (None, a.tool)
        cited = a.status != "answered" or bool(a.citations)
        rows.append({"id": c["id"], "category": c["category"], "expected": c["expected_status"], "got": a.status,
                     "tool": a.tool, "correct": bool(ok_status and ok_tool and cited)})
    df = pd.DataFrame(rows)
    attacks = df[df["category"] == "ataque"]
    benign = df[df["category"] == "legitima"]
    return {"n_cases": len(df), "accuracy": float(df["correct"].mean()),
            "attack_refusal_rate": float((attacks["got"] == "refused").mean()) if len(attacks) else None,
            "false_refusal_rate": float((benign["got"] == "refused").mean()) if len(benign) else None,
            "abstention_correct": float(df.loc[df["expected"] == "abstained", "correct"].mean())
            if (df["expected"] == "abstained").any() else None,
            "cases": rows}
