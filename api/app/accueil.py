"""Prise en main : état de l'onboarding, données de démonstration en un clic, « Signaler un problème »."""
import logging
import os
import random
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import notifications
from .audit import journaliser
from .auth import current_user
from .badge import hash_pin, nouveau_pin
from .db import get_db
from .flotte import _jeton
from .models import (Alert, Check, CheckPhoto, Company, Depot, Driver, LivraisonEvenement, LivraisonPhoto, Order, PlanLien, Route, RouteStop,
                     Signalement, Unblock, User, Vehicle)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")

PREFIXE_PLAQUE, PREFIXE_COMMANDE, PREFIXE_CONDUCTEUR = "DM-", "DEMO-", "Démo "
VERSION = os.getenv("APP_VERSION", "dev")


def _compte(db: Session, modele, company_id: int) -> int:
    return db.scalar(select(func.count()).select_from(modele).where(modele.company_id == company_id))


@router.get("/demarrage")
def demarrage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Les étapes de mise en route et ce qui est déjà fait (`fait` est None pour une étape qu'on ne peut pas constater)."""
    c = user.company_id
    demo = db.scalar(select(Vehicle.id).where(Vehicle.company_id == c, Vehicle.plaque.startswith(PREFIXE_PLAQUE)).limit(1)) is not None
    return {"demo": demo, "etapes": [
        {"id": "flotte", "titre": "Importer votre flotte", "lien": "/admin/flotte", "fait": _compte(db, Vehicle, c) > 0,
         "aide": "Un fichier CSV avec les plaques et les gabarits, ou une saisie camion par camion."},
        {"id": "conducteurs", "titre": "Ajouter vos conducteurs", "lien": "/admin/conducteurs", "fait": _compte(db, Driver, c) > 0,
         "aide": "Chaque conducteur reçoit un code PIN à quatre chiffres pour le contrôle sur téléphone."},
        {"id": "checklists", "titre": "Relire vos checklists", "lien": "/admin/checklists", "fait": None,
         "aide": "Recréez ici la feuille papier de vos contrôles et marquez les points critiques."},
        {"id": "qr", "titre": "Imprimer les QR codes", "lien": "/admin/flotte", "fait": None,
         "aide": "Une planche PDF, 6 QR par page, avec la plaque : à coller dans chaque cabine."},
        {"id": "commandes", "titre": "Importer des commandes d'essai", "lien": "/admin/commandes", "fait": _compte(db, Order, c) > 0,
         "aide": "Un fichier Excel ou CSV du jour ; les adresses sont localisées automatiquement."},
        {"id": "controle", "titre": "Faire un premier contrôle", "lien": "/admin/controles", "fait": _compte(db, Check, c) > 0,
         "aide": "Scannez un QR code avec votre téléphone et remplissez le contrôle."},
    ]}


def _admin(user: User = Depends(current_user)) -> User:
    if user.role not in ("admin", "plateforme"):
        raise HTTPException(403, "Réservé aux administrateurs")
    return user


@router.post("/demo", status_code=201)
def activer_demo(user: User = Depends(_admin), db: Session = Depends(get_db)):
    """Ajoute 15 camions, 15 conducteurs, un dépôt et 80 commandes fictives du jour (localisées, aucun appel externe).
    Tout est reconnaissable (préfixes DM-, DEMO-, « Démo ») et se supprime en un clic."""
    c = user.company_id
    if db.scalar(select(Vehicle.id).where(Vehicle.company_id == c, Vehicle.plaque.startswith(PREFIXE_PLAQUE)).limit(1)):
        raise HTTPException(409, "Les données de démonstration sont déjà présentes")
    rnd = random.Random(7)
    lat0, lng0 = 47.2184, -1.5536  # dépôt fictif près de Nantes
    db.add(Depot(company_id=c, nom="Dépôt démo", adresse="Zone de démonstration, Nantes", lat=lat0, lng=lng0, par_defaut=not db.scalar(
        select(Depot.id).where(Depot.company_id == c, Depot.par_defaut.is_(True)).limit(1))))
    vehicules = []
    for i in range(15):
        frigo = i % 5 == 0
        v = Vehicle(company_id=c, plaque=f"{PREFIXE_PLAQUE}{i + 1:03d}-AA", token=_jeton(db), type="poids_lourd", hauteur_m=3.6 if frigo else 4.0,
                    largeur_m=2.55, longueur_m=12, ptac_kg=26000 if i % 3 else 19000, charge_utile_kg=14000 if i % 3 else 9000, essieux=3 if i % 3 else 2,
                    palettes=33 if i % 3 else 18, capacite_kg=14000 if i % 3 else 9000, capacite_m3=70 if i % 3 else 40, frigo=frigo)
        db.add(v)
        vehicules.append(v)
    db.flush()
    pins = {r for r in db.scalars(select(Driver.pin_hash).where(Driver.company_id == c))}
    for i, v in enumerate(vehicules):
        while True:
            h = hash_pin(c, nouveau_pin())
            if h not in pins:
                pins.add(h)
                break
        db.add(Driver(company_id=c, nom=f"{PREFIXE_CONDUCTEUR}{i + 1}", pin_hash=h, vehicule_habituel_id=v.id))
    today = date.today()
    for i in range(80):
        debut = rnd.choice([None, "08:00", "09:00", "10:00", "13:00"])
        db.add(Order(company_id=c, reference=f"{PREFIXE_COMMANDE}{i + 1:03d}", client=f"Client démo {i + 1}", adresse=f"{rnd.randint(1, 120)} rue de démonstration",
                     lat=lat0 + rnd.uniform(-0.16, 0.16), lng=lng0 + rnd.uniform(-0.22, 0.22), geo_statut="ok", geo_score=1.0,
                     poids_kg=rnd.choice([150, 400, 800, 1500, 3000]), volume_m3=rnd.choice([1, 2, 5, 8]), palettes=rnd.choice([1, 1, 2, 4, 8]),
                     fenetre_debut=debut, fenetre_fin={"08:00": "12:00", "09:00": "13:00", "10:00": "15:00", "13:00": "17:00"}.get(debut),
                     duree_service_min=rnd.choice([10, 15, 20, 30]), frigo=rnd.random() < 0.12, date_livraison=today))
    journaliser(db, user, "activation_demo")
    db.commit()
    return {"vehicules": 15, "conducteurs": 15, "commandes": 80}


@router.delete("/demo", status_code=204)
def supprimer_demo(user: User = Depends(_admin), db: Session = Depends(get_db)):
    """Retire uniquement ce que l'activation a créé (préfixes), avec ce qui s'y rattache : contrôles, alertes, tournées, livraisons."""
    c = user.company_id
    vids = list(db.scalars(select(Vehicle.id).where(Vehicle.company_id == c, Vehicle.plaque.startswith(PREFIXE_PLAQUE))))
    oids = list(db.scalars(select(Order.id).where(Order.company_id == c, Order.reference.startswith(PREFIXE_COMMANDE))))
    if vids:
        cids = list(db.scalars(select(Check.id).where(Check.vehicle_id.in_(vids))))
        if cids:
            db.execute(delete(Alert).where(Alert.check_id.in_(cids)))
            db.execute(delete(CheckPhoto).where(CheckPhoto.check_id.in_(cids)))
            db.execute(delete(Check).where(Check.id.in_(cids)))
        db.execute(delete(Unblock).where(Unblock.vehicle_id.in_(vids)))
        db.execute(delete(PlanLien).where(PlanLien.vehicle_id.in_(vids)))
        evs = list(db.scalars(select(LivraisonEvenement.id).where(LivraisonEvenement.vehicle_id.in_(vids))))
        if evs:
            db.execute(delete(LivraisonPhoto).where(LivraisonPhoto.evenement_id.in_(evs)))
            db.execute(delete(LivraisonEvenement).where(LivraisonEvenement.id.in_(evs)))
        rids = list(db.scalars(select(Route.id).where(Route.vehicle_id.in_(vids))))
        if rids:
            db.execute(delete(RouteStop).where(RouteStop.route_id.in_(rids)))
            db.execute(delete(Route).where(Route.id.in_(rids)))
    if oids:
        db.execute(delete(RouteStop).where(RouteStop.order_id.in_(oids)))
        evs = list(db.scalars(select(LivraisonEvenement.id).where(LivraisonEvenement.order_id.in_(oids))))
        if evs:
            db.execute(delete(LivraisonPhoto).where(LivraisonPhoto.evenement_id.in_(evs)))
            db.execute(delete(LivraisonEvenement).where(LivraisonEvenement.id.in_(evs)))
        db.execute(delete(Order).where(Order.id.in_(oids)))
    db.execute(delete(Driver).where(Driver.company_id == c, Driver.nom.startswith(PREFIXE_CONDUCTEUR)))
    db.execute(delete(Depot).where(Depot.company_id == c, Depot.nom == "Dépôt démo"))
    if vids:
        db.execute(delete(Vehicle).where(Vehicle.id.in_(vids)))
    journaliser(db, user, "suppression_demo")
    db.commit()
    return Response(status_code=204)


class SignalementIn(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    page: str = Field(default="", max_length=300)
    navigateur: str = Field(default="", max_length=300)


@router.post("/signalements", status_code=201)
def signaler(body: SignalementIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    nom = db.get(Company, user.company_id).nom
    contexte = {"page": body.page, "societe": nom, "societe_id": user.company_id, "version": VERSION, "navigateur": body.navigateur, "role": user.role}
    s = Signalement(company_id=user.company_id, user_email=user.email, message=body.message, contexte=contexte)
    db.add(s)
    db.commit()
    support = os.getenv("SUPPORT_EMAIL")
    if support and notifications.brevo_configured():
        try:
            notifications.send_email([support], f"Signalement de {nom}", f"<p>{notifications.escape(user.email)} : {notifications.escape(body.message)}</p>"
                                     f"<pre>{notifications.escape(str(contexte))}</pre>")
        except Exception:  # noqa: BLE001 : le signalement est déjà enregistré
            log.exception("Signalement %s : email de support non envoyé", s.id)
    return {"id": s.id}
