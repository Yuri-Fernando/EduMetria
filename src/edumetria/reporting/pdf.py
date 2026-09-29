"""Relatório técnico em PDF (reportlab) — mesma fonte de dados do HTML.

Primeira página: aviso de dados sintéticos, propósito, mapa de evidências e
limitações; páginas seguintes: figuras do run. Nenhum valor digitado à mão.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_CANDIDATES = [("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
                   ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
FALLBACK = {"θ": "theta", "α": "alfa", "−": "-", "Δ": "Delta", "×": "x", "≤": "<=", "≥": ">="}


def _font() -> str | None:
    """Fonte TTF com glifos gregos (θ, α, −); None → substitui por texto."""
    if "EduSans" in pdfmetrics.getRegisteredFontNames():
        return "EduSans"
    for reg, bold in FONT_CANDIDATES:
        if Path(reg).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("EduSans", reg))
            pdfmetrics.registerFont(TTFont("EduSans-Bold", bold))
            pdfmetrics.registerFontFamily("EduSans", normal="EduSans", bold="EduSans-Bold")
            return "EduSans"
    return None


def _txt(s: str, has_font: bool) -> str:
    if has_font:
        return s
    for k, v in FALLBACK.items():
        s = s.replace(k, v)
    return s


def write_pdf(out: Path, ctx: dict) -> Path:
    ev = ctx["evidence"]
    path = out / "technical_report.pdf"
    ss = getSampleStyleSheet()
    font = _font()
    if font:
        for st in ss.byName.values():
            st.fontName = "EduSans-Bold" if "Heading" in st.name or st.name == "Title" else "EduSans"
    T = lambda x: _txt(str(x), font is not None)  # noqa: E731
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.4 * cm, bottomMargin=1.4 * cm, title="EduMetria — relatório técnico")
    warn = Table([[Paragraph("<b>DADOS SINTÉTICOS — PoC experimental.</b> Nenhum resultado se refere a estudantes, "
                             "escolas ou redes reais.", ss["BodyText"])]], colWidths=[17.5 * cm])
    warn.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fde7c8")),
                              ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9a5b00"))]))
    story = [Paragraph("EduMetria — relatório técnico", ss["Title"]), warn, Spacer(1, 8),
             Paragraph(f"run <b>{ctx['run_id']}</b> · cenário <b>{ctx['scenario']['scenario_id']}</b> — "
                       f"{ctx['scenario']['description']}", ss["BodyText"]),
             Paragraph(f"<b>Estado:</b> {ev.approval_state}", ss["BodyText"]), Spacer(1, 6),
             Paragraph(f"<b>Propósito.</b> {ev.population_and_purpose}", ss["BodyText"]), Spacer(1, 8),
             Paragraph("Mapa de evidências", ss["Heading2"])]
    secs = ["content_review", "response_process", "dimensionality", "ctt", "irt", "precision", "dif",
            "external_relations", "structure_invariance"]
    rows = [["seção", "status", "resumo"]]
    for s in secs:
        sec = getattr(ev, s, None)
        if sec is not None:
            rows.append([s, sec.status.value, Paragraph(T(sec.summary), ss["BodyText"])])
    t = Table(rows, colWidths=[3.4 * cm, 2.4 * cm, 11.7 * cm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f5d8a")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("FONTNAME", (0, 0), (-1, -1), font or "Helvetica")]))
    story += [t, Spacer(1, 8), Paragraph("Limitações", ss["Heading2"])]
    story += [Paragraph(T(f"• {x}"), ss["BodyText"]) for x in ev.limitations]
    story += [Paragraph(f"<b>Usos proibidos:</b> {'; '.join(ev.prohibited_uses)}", ss["BodyText"]), PageBreak()]
    for fig, cap in (("ctt_math6.png", "TCT — dificuldade × discriminação"), ("icc_math6.png", "Curvas características (2PL)"),
                     ("information_math6.png", "Informação do teste"), ("theta_uncertainty_math6.png", "θ × incerteza"),
                     ("dif_math6.png", "DIF Mantel-Haenszel"), ("obs_exp_worst_item.png", "Observado × esperado")):
        f = out / "figures" / fig
        if f.exists():
            story += [Paragraph(cap, ss["Heading3"]), Image(str(f), width=15 * cm, height=9 * cm), Spacer(1, 6)]
    doc.build(story)
    return path
