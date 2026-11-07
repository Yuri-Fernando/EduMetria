#!/usr/bin/env python
"""Percorre a jornada do educador no painel REAL e salva capturas + o resumo exportado.

Pré-requisitos (processos reais, modo demo):
    uvicorn apps.api.main:app --port 8000          (banco limpo: EDUMETRIA_DB=<arquivo novo>)
    streamlit run apps/dashboard/app.py --server.port 8501 --server.headless true

    python scripts/capture_ai4good_screens.py [--url http://localhost:8501]
→ docs/images/ai4good_*.png e docs/ai4good2027/exemplo_resumo_SCH01_SINTETICO.html

O script clica nos mesmos botões que uma pessoa clicaria: encaminha um ponto (perfil
coord-bruno) e aprova com checklist (perfil coord-clara). Nada é simulado na captura.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs" / "images"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    args = ap.parse_args()
    IMG.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1500}, accept_downloads=True)
        page.goto(args.url, wait_until="networkidle")
        page.get_by_text("EduMetria Social · Visão do Educador").wait_for(timeout=60000)
        page.wait_for_timeout(2500)

        def tab(name: str, shot: str | None = None, wait: int = 2000):
            page.get_by_role("tab", name=name).click()
            page.wait_for_timeout(wait)
            if shot:
                page.screenshot(path=str(IMG / shot))

        page.screenshot(path=str(IMG / "ai4good_1_problema.png"))
        tab("2 · Escola fictícia", "ai4good_2_escola.png", 3500)
        tab("3 · Pontos para revisão", None, 2500)
        page.get_by_role("button", name="Encaminhar para revisão pedagógica").first.click()
        page.get_by_text("enviado para revisão").wait_for(timeout=30000)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(IMG / "ai4good_3_pontos_encaminhado.png"))
        tab("4 · Revisão pedagógica", None, 3000)
        for box in page.get_by_role("checkbox").all():
            if box.is_visible():
                box.check(force=True)
                page.wait_for_timeout(400)
        page.get_by_label("Justificativa (mín. 10 caracteres)").first.fill(
            "Sinal além da margem de erro no eixo; planejar revisão do conteúdo com a docente de referência.")
        page.keyboard.press("Tab")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(IMG / "ai4good_4_revisao_checklist.png"))
        page.get_by_role("button", name="Aprovar planejamento de apoio").first.click()
        page.wait_for_timeout(3500)
        page.screenshot(path=str(IMG / "ai4good_4b_revisao_aprovada.png"))
        tab("5 · Como chegamos aqui", "ai4good_5_como_chegamos.png", 2500)
        tab("6 · Transparência", "ai4good_6_transparencia.png", 2500)
        with page.expect_download() as dl:
            page.get_by_role("button", name="Baixar resumo (HTML)").click()
        dl.value.save_as(str(ROOT / "docs" / "ai4good2027" / "exemplo_resumo_SCH01_SINTETICO.html"))
        browser.close()
    print("capturas em", IMG)


if __name__ == "__main__":
    main()
