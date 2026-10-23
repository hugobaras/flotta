import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import webhooks, livraisons, notifications, photos
from .auth import current_user
from .db import get_db
from .models import Driver, LivraisonEvenement, LivraisonPhoto, Order, Plan, PlanLien, Route, RouteStop, User, Vehicle

log = logging.getLogger(__name__)
admin = APIRouter(prefix="/api/admin/plans")
chauffeur = APIRouter(prefix="/api/tournee")


def _plan(db: Session, user: User, plan_id: int) -> Plan:
    p = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.company_id == user.company_id))
    if not p:
        raise HTTPException(404, "Plan inconnu")
    return p


def _liens(db: Session, plan: Plan) -> list[dict]:
    base = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    plaques = {v.id: v for v in db.scalars(select(Vehicle).where(Vehicle.company_id == plan.company_id))}
    noms = {r.vehicle_id: r.conducteur_id for r in db.scalars(select(Route).where(Route.plan_id == plan.id))}
    drivers = {d.id: d for d in db.scalars(select(Driver).where(Driver.company_id == plan.company_id))}
    sortie = []
    for lien in db.scalars(select(PlanLien).where(PlanLien.plan_id == plan.id).order_by(PlanLien.vehicle_id)):
        d = drivers.get(noms.get(lien.vehicle_id))
        sortie.append({"vehicle_id": lien.vehicle_id, "plaque": plaques[lien.vehicle_id].plaque, "token": lien.token, "url": f"{base}/t/{lien.token}",
                       "conducteur": d.nom if d else None, "email": d.email if d else None})
    return sortie


@admin.post("/{plan_id}/publier")
def publier(plan_id: int, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Rend les tournées du plan visibles aux chauffeurs par un lien personnel ; envoie le lien par email aux conducteurs qui ont une adresse."""
    plan = _plan(db, user, plan_id)
    if plan.statut != "termine":
        raise HTTPException(409, "Le plan n'est pas encore calculé")
    routes = [r for r in db.scalars(select(Route).where(Route.plan_id == plan.id)) if db.scalar(select(RouteStop.id).where(RouteStop.route_id == r.id).limit(1))]
    if not routes:
        raise HTTPException(409, "Aucune tournée à publier : le plan ne contient aucun arrêt")
    for autre in db.scalars(select(Plan).where(Plan.company_id == plan.company_id, Plan.jour == plan.jour, Plan.id != plan.id, Plan.publie_le.is_not(None))):
        autre.publie_le = None  # un seul plan publié par jour : les anciens liens ne sont plus d'actualité
    plan.publie_le = livraisons.maintenant()
    existants = {l.vehicle_id for l in db.scalars(select(PlanLien).where(PlanLien.plan_id == plan.id))}
    for r in routes:
        if r.vehicle_id not in existants:
            db.add(PlanLien(token=secrets.token_urlsafe(24), company_id=plan.company_id, plan_id=plan.id, vehicle_id=r.vehicle_id))
    db.commit()
    liens = _liens(db, plan)
    webhooks.declencher(db, plan.company_id, "plan.publie", {"plan_id": plan.id, "jour": plan.jour.isoformat(), "nb_tournees": len(routes)})
    if notifications.brevo_configured():
        for l in liens:
            if l["email"]:
                background.add_task(_envoyer_lien, l["email"], l["plaque"], l["url"], plan.jour.strftime("%d/%m/%Y"))
    return {"publie_le": plan.publie_le, "liens": liens}


def _envoyer_lien(email: str, plaque: str, url: str, jour: str):
    try:
        notifications.send_email([email], f"Votre tournée du {jour} ({plaque})",
                                 f'<p>Bonjour, voici votre tournée du {jour} pour le camion <b>{notifications.escape(plaque)}</b> :</p>'
                                 f'<p><a href="{notifications.escape(url)}">{notifications.escape(url)}</a></p>'
                                 '<p>Faites d\'abord le contrôle avant départ de votre camion : la tournée s\'ouvre ensuite.</p>')
    except Exception:  # noqa: BLE001 : un email perdu ne doit pas empêcher la publication
        log.exception("Lien de tournée non envoyé à %s", email)


@admin.get("/{plan_id}/liens")
def liens(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id)
    return {"publie_le": plan.publie_le, "liens": _liens(db, plan) if plan.publie_le else []}


# --- Côté chauffeur : lien personnel, sans compte ---


def _contexte(db: Session, token: str):
    lien = db.get(PlanLien, token)
    if not lien:
        raise HTTPException(404, "Lien de tournée inconnu")
    plan = db.get(Plan, lien.plan_id)
    if not plan or plan.publie_le is None:
        raise HTTPException(410, "Cette tournée n'est plus d'actualité : un nouveau plan a été publié. Demandez le nouveau lien à votre exploitant.")
    return lien, plan, db.get(Vehicle, lien.vehicle_id)


def _arrets(db: Session, plan: Plan, vehicle_id: int):
    route = db.scalar(select(Route).where(Route.plan_id == plan.id, Route.vehicle_id == vehicle_id))
    if not route:
        return None, []
    rows = db.execute(select(RouteStop, Order).join(Order, Order.id == RouteStop.order_id).where(RouteStop.route_id == route.id).order_by(RouteStop.ordre))
    return route, list(rows)


@chauffeur.get("/{token}")
def lire(token: str, db: Session = Depends(get_db)):
    lien, plan, vehicle = _contexte(db, token)
    ok, raison = livraisons.controle_du_jour(db, vehicle, plan.jour)
    route, rows = _arrets(db, plan, vehicle.id)
    conducteur = db.get(Driver, route.conducteur_id).nom if route and route.conducteur_id else None
    base = {"plaque": vehicle.plaque, "jour": plan.jour, "conducteur": conducteur, "verrouillee": not ok, "raison": raison,
            "controle_token": vehicle.token, "jour_du_plan": plan.jour == livraisons.aujourdhui(), "motifs": livraisons.MOTIFS, "arrets": []}
    if not ok or not route:
        return base  # tournée verrouillée : aucun arrêt n'est communiqué avant le contrôle
    etat = livraisons.derniers_evenements(db, plan.id)
    base.update(depart_min=route.depart_min, retour_min=route.retour_min, distance_km=route.distance_km, pauses=route.pauses or [])
    base["arrets"] = [{
        "order_id": o.id, "ordre": s.ordre, "reference": o.reference, "client": o.client, "adresse": o.adresse, "lat": o.lat, "lng": o.lng,
        "arrivee_min": s.arrivee_min, "fenetre_debut": o.fenetre_debut, "fenetre_fin": o.fenetre_fin, "palettes": o.palettes, "poids_kg": o.poids_kg,
        "contact_nom": o.contact_nom, "contact_telephone": o.contact_telephone, "consignes": o.consignes,
        "statut": (etat.get(o.id) or {}).get("statut"), "motif": (etat.get(o.id) or {}).get("motif"),
    } for s, o in rows]
    return base


class EvenementIn(BaseModel):
    order_id: int
    statut: str = Field(pattern=r"^(arrive|livre|impossible)$")
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    fait_le: datetime | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    motif: str | None = None
    commentaire: str | None = Field(default=None, max_length=300)
    nom_destinataire: str | None = Field(default=None, max_length=100)
    signature: str | None = Field(default=None, max_length=300_000)

    @model_validator(mode="after")
    def coherent(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Position incomplète")
        if self.statut == "impossible" and self.motif not in livraisons.MOTIFS:
            raise ValueError("Précisez le motif : " + ", ".join(livraisons.MOTIFS))
        if self.signature and not self.signature.startswith("data:image/png;base64,"):
            raise ValueError("Signature : PNG attendu")
        return self


def _sortie_evenement(e: LivraisonEvenement) -> dict:
    return {"id": e.id, "statut": e.statut, "order_id": e.order_id, "fait_le": e.fait_le}


@chauffeur.post("/{token}/evenements", status_code=201)
def evenement(token: str, body: EvenementIn, response: Response, db: Session = Depends(get_db)):
    lien, plan, vehicle = _contexte(db, token)
    ok, raison = livraisons.controle_du_jour(db, vehicle, plan.jour)
    if not ok:
        raise HTTPException(409, raison)
    if body.client_id:  # rejeu d'un envoi après coupure réseau : on renvoie l'événement déjà enregistré
        deja = db.scalar(select(LivraisonEvenement).where(LivraisonEvenement.company_id == plan.company_id, LivraisonEvenement.client_id == body.client_id))
        if deja:
            response.status_code = 200
            return _sortie_evenement(deja)
    route, rows = _arrets(db, plan, vehicle.id)
    commande = next((o for _, o in rows if o.id == body.order_id), None)
    if commande is None:
        raise HTTPException(404, "Cet arrêt ne fait pas partie de cette tournée")
    courant = livraisons.derniers_evenements(db, plan.id).get(body.order_id, {}).get("statut")
    existant = db.scalar(select(LivraisonEvenement).where(LivraisonEvenement.plan_id == plan.id, LivraisonEvenement.order_id == body.order_id,
                                                          LivraisonEvenement.statut == body.statut).order_by(LivraisonEvenement.id.desc()))
    if courant in livraisons.FINAUX and courant != body.statut:
        raise HTTPException(409, "Cet arrêt est déjà clôturé")
    if existant is not None and (body.statut == "arrive" or courant == body.statut):
        response.status_code = 200
        return _sortie_evenement(existant)
    maintenant = livraisons.maintenant()
    fait_le = body.fait_le
    if fait_le is not None:
        fait_le = fait_le.replace(tzinfo=timezone.utc) if fait_le.tzinfo is None else fait_le.astimezone(timezone.utc)
        debut_plan = datetime.combine(plan.jour, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=1)
        if not (debut_plan <= fait_le <= maintenant + timedelta(minutes=5)):
            fait_le = None  # horloge du téléphone aberrante
    e = LivraisonEvenement(company_id=plan.company_id, plan_id=plan.id, order_id=body.order_id, vehicle_id=vehicle.id, statut=body.statut,
                           client_id=body.client_id, fait_le=fait_le or maintenant, recu_le=maintenant, lat=body.lat, lng=body.lng,
                           motif=body.motif if body.statut == "impossible" else None, commentaire=body.commentaire,
                           nom_destinataire=body.nom_destinataire, signature=body.signature if body.statut == "livre" else None)
    db.add(e)
    if body.statut == "livre":
        commande.statut = "livre"
    elif body.statut == "impossible":
        commande.statut = "echec"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        deja = db.scalar(select(LivraisonEvenement).where(LivraisonEvenement.company_id == plan.company_id, LivraisonEvenement.client_id == body.client_id))
        if not deja:
            raise
        response.status_code = 200
        return _sortie_evenement(deja)
    if body.statut == "livre":
        webhooks.declencher(db, plan.company_id, "arret.livre", {"plan_id": plan.id, "commande_id": commande.id, "reference": commande.reference,
                                                                "plaque": vehicle.plaque, "fait_le": e.fait_le.isoformat()})
    return _sortie_evenement(e)


PHOTO_FENETRE = timedelta(hours=1)
PHOTOS_MAX = 3


@chauffeur.post("/{token}/evenements/{evenement_id}/photos", status_code=201)
async def photo(token: str, evenement_id: int, photo: UploadFile = File(), db: Session = Depends(get_db)):
    lien, plan, vehicle = _contexte(db, token)
    e = db.scalar(select(LivraisonEvenement).where(LivraisonEvenement.id == evenement_id, LivraisonEvenement.plan_id == plan.id,
                                                   LivraisonEvenement.vehicle_id == vehicle.id))
    if not e:
        raise HTTPException(404, "Événement inconnu")
    recu = e.recu_le.replace(tzinfo=timezone.utc) if e.recu_le.tzinfo is None else e.recu_le
    if livraisons.maintenant() - recu > PHOTO_FENETRE:
        raise HTTPException(403, "Délai d'ajout de photos dépassé")
    if len(db.scalars(select(LivraisonPhoto.id).where(LivraisonPhoto.evenement_id == e.id)).all()) >= PHOTOS_MAX:
        raise HTTPException(409, "Nombre maximal de photos atteint")
    data = await photo.read(photos.MAX_BYTES + 1)
    if len(data) > photos.MAX_BYTES:
        raise HTTPException(413, "Photo trop lourde (5 Mo maximum)")
    ext = photos.detect_ext(data)
    if not ext:
        raise HTTPException(415, "Format accepté : JPEG ou PNG")
    row = LivraisonPhoto(company_id=plan.company_id, evenement_id=e.id, fichier=photos.save(plan.company_id, data, ext))
    db.add(row)
    db.commit()
    return {"id": row.id}


# --- Côté exploitant : preuves de livraison ---


@admin.get("/livraisons/photos/{photo_id}")
def photo_admin(photo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(LivraisonPhoto).where(LivraisonPhoto.id == photo_id, LivraisonPhoto.company_id == user.company_id))
    f = photos.path(user.company_id, p.fichier) if p else None
    if not f or not f.exists():
        raise HTTPException(404, "Photo inconnue")
    return FileResponse(f, media_type="image/png" if f.suffix == ".png" else "image/jpeg")


@admin.get("/livraisons/{evenement_id}/signature")
def signature_admin(evenement_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.scalar(select(LivraisonEvenement).where(LivraisonEvenement.id == evenement_id, LivraisonEvenement.company_id == user.company_id))
    if not e or not e.signature:
        raise HTTPException(404, "Signature inconnue")
    import base64
    return Response(base64.b64decode(e.signature.split(",", 1)[1]), media_type="image/png")
