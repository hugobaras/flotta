import base64
import io
from datetime import timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Check, Company, Vehicle

PARIS = ZoneInfo("Europe/Paris")
STYLES = getSampleStyleSheet()


def _image(source, max_w: float, max_h: float):
    """Image réduite à la boîte donnée ; une image illisible ne doit pas faire échouer tout le PDF."""
    try:
        data = source.read_bytes() if isinstance(source, Path) else source
        w, h = ImageReader(io.BytesIO(data)).getSize()
        scale = min(max_w / w, max_h / h, 1)
        return Image(io.BytesIO(data), w * scale, h * scale)
    except Exception:
        return Paragraph("(image illisible)", STYLES["Italic"])


def _signature_bytes(signature: str | None) -> bytes | None:
    if not signature:
        return None
    try:
        return base64.b64decode(signature.split(",", 1)[1], validate=True)
    except Exception:
        return None


def render_check_pdf(company: Company, vehicle: Vehicle, check: Check, photo_files: list[Path],
                     logo_file: Path | None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=f"Contrôle {vehicle.plaque}")
    p = lambda text, style="BodyText": Paragraph(escape(text), STYLES[style])  # noqa: E731
    when = check.created_at
    when = (when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when).astimezone(PARIS)

    head = [[_image(logo_file, 40 * mm, 20 * mm) if logo_file else "", p(company.nom, "Title")]]
    story = [Table(head, colWidths=[45 * mm, None], style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
             Spacer(1, 6 * mm),
             p(f"Contrôle avant départ : {vehicle.plaque}", "Heading2"),
             p(f"Conducteur : {check.conducteur}"),
             p(f"Date : {when:%d/%m/%Y à %H:%M} (heure de Paris)")]
    if check.lat is not None:
        story.append(p(f"Position : {check.lat:.5f}, {check.lng:.5f}"))
    story.append(p("Défaut critique : le véhicule a été bloqué" if check.defaut_critique else "Aucun défaut critique"))
    story.append(Spacer(1, 4 * mm))

    rows = [["Point", "Résultat"]]
    for r in check.reponses:
        label = r["libelle"] + (" (critique)" if r.get("critique") else "")
        if r.get("commentaire"):
            label += f" : {r['commentaire']}"
        rows.append([Paragraph(escape(label), STYLES["BodyText"]), "OK" if r["ok"] else "DÉFAUT"])
    table = Table(rows, colWidths=[None, 25 * mm], repeatRows=1)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]
    style += [("TEXTCOLOR", (1, i), (1, i), colors.red) for i, r in enumerate(check.reponses, 1) if not r["ok"]]
    table.setStyle(TableStyle(style))
    story.append(table)

    if photo_files:
        story += [Spacer(1, 6 * mm), p("Photos", "Heading3")]
        cells = [_image(f, 80 * mm, 60 * mm) for f in photo_files]
        cells += [""] * (len(cells) % 2)
        story.append(Table([cells[i:i + 2] for i in range(0, len(cells), 2)], colWidths=[85 * mm, 85 * mm]))
    sig = _signature_bytes(check.signature)
    if sig:
        story += [Spacer(1, 6 * mm), p("Signature du conducteur", "Heading3"), _image(sig, 70 * mm, 30 * mm)]
    doc.build(story)
    return buf.getvalue()
