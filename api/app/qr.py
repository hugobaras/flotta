import io

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

COLONNES, LIGNES = 2, 3  # 6 QR codes par page


def _qr_image(url: str) -> ImageReader:
    buf = io.BytesIO()
    qrcode.make(url, box_size=10, border=2).save(buf, "PNG")
    buf.seek(0)
    return ImageReader(buf)


def planche_qr(vehicules: list[tuple[str, str]], base_url: str) -> bytes:
    """PDF A4, 6 QR codes par page avec la plaque. `vehicules` = [(plaque, jeton)]."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    largeur, hauteur = A4
    marge = 12 * mm
    cw, ch = (largeur - 2 * marge) / COLONNES, (hauteur - 2 * marge) / LIGNES
    for n, (plaque, jeton) in enumerate(vehicules):
        pos = n % (COLONNES * LIGNES)
        if n and pos == 0:
            c.showPage()
        x = marge + (pos % COLONNES) * cw
        y = hauteur - marge - (pos // COLONNES + 1) * ch
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setDash(2, 3)
        c.rect(x + 3 * mm, y + 3 * mm, cw - 6 * mm, ch - 6 * mm)
        c.setDash()
        c.setFillColorRGB(0, 0, 0)
        taille = 62 * mm
        c.drawImage(_qr_image(f"{base_url.rstrip('/')}/c/{jeton}"), x + (cw - taille) / 2, y + ch - 12 * mm - taille, taille, taille)
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(x + cw / 2, y + 22 * mm, plaque)
        c.setFont("Helvetica", 9)
        c.drawCentredString(x + cw / 2, y + 14 * mm, "Scannez pour le contrôle avant départ")
    c.save()
    return buf.getvalue()
