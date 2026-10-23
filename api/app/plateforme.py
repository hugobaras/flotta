"""Back-office interne (rôle `plateforme`) : sociétés clientes, offres, devis et factures, suivi du MRR.
Seules routes volontairement inter-sociétés ; chacune exige le rôle `plateforme`."""
import io
import os
from datetime import date
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import offres
from .audit import journaliser
from .auth import current_user
from .checklists import create_default_template
from .db import get_db
from .models import Company, Facture, Subscription, User, Vehicle

router = APIRouter(prefix="/api/plateforme")
STYLES = getSampleStyleSheet()


def operateur(user: User = Depends(current_user)) -> User:
    if user.role != "plateforme":
        raise HTTPException(403, "Réservé à l'équipe Flotta")
    return user


class SocieteIn(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    offre: str = Field(pattern=r"^(essentiel|pro)$")
    camions_factures: int = Field(ge=1, le=10000)
    statut: str = Field(default="essai", pattern=r"^(essai|actif|suspendu)$")


class AbonnementPatch(BaseModel):
    offre: str | None = Field(default=None, pattern=r"^(essentiel|pro)$")
    camions_factures: int | None = Field(default=None, ge=1, le=10000)
    statut: str | None = Field(default=None, pattern=r"^(essai|actif|suspendu)$")


def _ligne(db: Session, c: Company, s: Subscription | None) -> dict:
    camions = db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.company_id == c.id, Vehicle.actif.is_(True)))
    utilisateurs = db.scalar(select(func.count()).select_from(User).where(User.company_id == c.id, User.role != "plateforme"))
    out = {"id": c.id, "nom": c.nom, "camions_actifs": camions, "utilisateurs": utilisateurs,
           "offre": s.offre if s else None, "camions_factures": s.camions_factures if s else None, "statut": s.statut if s else None}
    if s:
        out["mensuel_ht"] = offres.calculer(s.offre, s.camions_factures, "mensuel", 0, 0)["mensuel_ht"]
    return out


@router.get("/societes")
def societes(_: User = Depends(operateur), db: Session = Depends(get_db)):
    subs = {s.company_id: s for s in db.scalars(select(Subscription))}
    return [_ligne(db, c, subs.get(c.id)) for c in db.scalars(select(Company).order_by(Company.nom))]


@router.post("/societes", status_code=201)
def creer_societe(body: SocieteIn, _: User = Depends(operateur), db: Session = Depends(get_db)):
    c = Company(nom=body.nom)
    db.add(c)
    db.flush()
    create_default_template(db, c.id)
    s = Subscription(company_id=c.id, offre=body.offre, camions_factures=body.camions_factures, statut=body.statut)
    db.add(s)
    db.commit()
    return _ligne(db, c, s)


@router.patch("/societes/{company_id}/abonnement")
def modifier_abonnement(company_id: int, body: AbonnementPatch, user: User = Depends(operateur), db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "Société inconnue")
    s = offres.abonnement(db, company_id)
    if not s:
        s = Subscription(company_id=company_id)
        db.add(s)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(s, k, v)
    journaliser(db, user, "changement_abonnement", f"{c.nom} : {s.offre}, {s.camions_factures} camions, {s.statut}", company_id=c.id)
    db.commit()
    return _ligne(db, c, s)


@router.get("/tableau")
def tableau(_: User = Depends(operateur), db: Session = Depends(get_db)):
    """MRR = abonnements actifs uniquement (les essais et les suspendus ne sont pas facturés)."""
    subs = list(db.scalars(select(Subscription)))
    actifs = [s for s in subs if s.statut == "actif"]
    mrr = sum(offres.calculer(s.offre, s.camions_factures, "mensuel", 0, 0)["mensuel_ht"] for s in actifs)
    return {"mrr_ht": mrr, "camions_factures": sum(s.camions_factures for s in actifs),
            "clients_actifs": len(actifs), "clients_en_essai": sum(s.statut == "essai" for s in subs),
            "clients_suspendus": sum(s.statut == "suspendu" for s in subs)}


class DocumentIn(BaseModel):
    type: str = Field(pattern=r"^(devis|facture)$")
    periode: str = Field(default="mensuel", pattern=r"^(mensuel|annuel)$")
    remise_pct: float | None = Field(default=None, ge=0, le=100)  # défaut : remise annuelle de la configuration
    tva_pct: float | None = Field(default=None, ge=0, le=100)


@router.post("/societes/{company_id}/documents", status_code=201)
def emettre(company_id: int, body: DocumentIn, _: User = Depends(operateur), db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    s = offres.abonnement(db, company_id)
    if not c or not s:
        raise HTTPException(404, "Société ou abonnement inconnu")
    remise = body.remise_pct if body.remise_pct is not None else offres.remise_annuelle_pct()
    tva = body.tva_pct if body.tva_pct is not None else offres.tva_pct()
    montants = offres.calculer(s.offre, s.camions_factures, body.periode, remise, tva)
    today = date.today()
    prefixe = ("FA" if body.type == "facture" else "DE") + f"-{today.year}-"
    # Numérotation continue sans trou : le prochain numéro suit le plus grand déjà émis (unicité garantie par la base).
    dernier = db.scalar(select(func.max(Facture.numero)).where(Facture.numero.like(prefixe + "%")))
    n = int(dernier.rsplit("-", 1)[1]) + 1 if dernier else 1
    f = Facture(numero=f"{prefixe}{n:04d}", company_id=company_id, type=body.type, emise_le=today, detail={
        "offre": s.offre, "camions": s.camions_factures, "periode": body.periode, "remise_pct": remise if body.periode == "annuel" else 0,
        "tva_pct": tva, "client": c.nom, **montants})
    db.add(f)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Numéro déjà attribué, réessayez")
    return {"id": f.id, "numero": f.numero, **f.detail}


def eur(centimes: int) -> str:
    return f"{centimes / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _vendeur() -> list[str]:
    """Identité du vendeur lue dans l'environnement : à renseigner avant toute émission réelle."""
    e = os.getenv
    return [e("VENDEUR_NOM", "[VENDEUR_NOM à renseigner]"), e("VENDEUR_ADRESSE", "[VENDEUR_ADRESSE à renseigner]"),
            f"SIREN {e('VENDEUR_SIREN', '[à renseigner]')} · TVA {e('VENDEUR_TVA', '[à renseigner]')}"]


def pdf_document(f: Facture) -> bytes:
    d = f.detail
    nom_offre = offres.grille()[d["offre"]]["nom"]
    titre = "Devis" if f.type == "devis" else "Facture"
    periode = "12 mois (paiement annuel)" if d["periode"] == "annuel" else "1 mois"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                            title=f"{titre} {f.numero}")
    p = lambda t, st="Normal": Paragraph(escape(t), STYLES[st])
    lignes = [["Désignation", "Quantité", "Montant HT"],
              [f"Abonnement Flotta {nom_offre} — {periode}, {d['camions']} camion(s) facturé(s)", d["mois"] * d["camions"], eur(d["brut_ht"])]]
    if d["mensuel_ht"] > d["camions"] * round(offres.grille()[d["offre"]]["prix_eur"] * 100):
        lignes.append([f"Minimum de facturation appliqué ({eur(d['mensuel_ht'])} par mois)", "", ""])
    if d["remise"]:
        lignes.append([f"Remise de paiement annuel ({d['remise_pct']:g} %)", "", "- " + eur(d["remise"])])
    lignes += [["", "Total HT", eur(d["ht"])], ["", f"TVA {d['tva_pct']:g} %", eur(d["tva"])], ["", "Total TTC", eur(d["ttc"])]]
    t = Table(lignes, colWidths=[100 * mm, 30 * mm, 40 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, 1), 0.4, colors.grey), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    mentions = ["Paiement par virement bancaire." + (f" IBAN : {os.getenv('VENDEUR_IBAN', '[IBAN à renseigner]')}." if f.type == "facture" else ""),
                "Pénalités de retard : trois fois le taux d'intérêt légal, exigibles sans rappel. Indemnité forfaitaire pour frais de recouvrement : 40 €. Pas d'escompte pour paiement anticipé."]
    if f.type == "devis":
        mentions.insert(0, "Devis valable 30 jours à compter de sa date d'émission. Bon pour accord : date, signature.")
    doc.build([p(titre.upper() + f" {f.numero}", "Title"), p(f"Émis le {f.emise_le.strftime("%d/%m/%Y")}"), Spacer(1, 6 * mm),
               *[p(x) for x in _vendeur()], Spacer(1, 6 * mm), p("Client : " + d["client"], "Heading3"), Spacer(1, 6 * mm), t, Spacer(1, 8 * mm),
               *[p(m, "Italic") for m in mentions]])
    return buf.getvalue()


@router.get("/documents/{facture_id}/pdf")
def telecharger(facture_id: int, _: User = Depends(operateur), db: Session = Depends(get_db)):
    f = db.get(Facture, facture_id)
    if not f:
        raise HTTPException(404, "Document inconnu")
    return Response(pdf_document(f), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{f.numero}.pdf"'})
