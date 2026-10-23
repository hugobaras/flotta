"""Génère les guides clients (une page chacun) : docs/client/*.md -> web/public/aide/*.pdf. Usage : api/.venv/bin/python scripts/guides_pdf.py"""
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

RACINE = Path(__file__).resolve().parent.parent
S = getSampleStyleSheet()
CORPS = ParagraphStyle("corps", parent=S["Normal"], fontSize=10, leading=14, spaceAfter=4)
LISTE = ParagraphStyle("liste", parent=CORPS, leftIndent=12, bulletIndent=2)


def inline(t: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(t))


def rendre(md: Path, pdf: Path):
    flux = []
    for ligne in md.read_text().splitlines():
        if not ligne.strip():
            flux.append(Spacer(1, 2 * mm))
        elif ligne.startswith("# "):
            flux += [Paragraph(inline(ligne[2:]), S["Title"]), Paragraph("Flotta, guide de prise en main", S["Italic"]), Spacer(1, 3 * mm)]
        elif ligne.startswith("## "):
            flux.append(Paragraph(inline(ligne[3:]), S["Heading3"]))
        elif ligne.startswith("- ") or re.match(r"\d+\. ", ligne):
            puce = "•" if ligne.startswith("- ") else ligne.split(".")[0] + "."
            flux.append(Paragraph(inline(re.sub(r"^(- |\d+\. )", "", ligne)), LISTE, bulletText=puce))
        else:
            flux.append(Paragraph(inline(ligne), CORPS))
    SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=16 * mm, bottomMargin=14 * mm, title=md.stem).build(flux)


if __name__ == "__main__":
    sortie = RACINE / "web" / "public" / "aide"
    sortie.mkdir(parents=True, exist_ok=True)
    for md in sorted((RACINE / "docs" / "client").glob("*.md")):
        rendre(md, sortie / f"{md.stem}.pdf")
        print(md.stem)
