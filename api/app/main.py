from contextlib import asynccontextmanager

import logging
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user, router as auth_router
from . import photos
from .checklist_routes import router as checklist_router
from .checklists import active_items, create_default_template
from .db import SessionLocal, get_db
from .badge import hash_pin, lire_badge, signer_badge
from .conducteurs import router as conducteurs_router
from .exploitation import router as exploitation_router
from .flotte import router as flotte_router
from .models import Alert, Check, CheckPhoto, Company, Driver, User, Vehicle
from .worker import send_critical_alert

DEMO_TOKEN = "demo"
log = logging.getLogger(__name__)


def enqueue_alert(alert_id: int) -> None:
    try:
        send_critical_alert.apply_async(args=[alert_id], retry=False)
    except Exception:  # Redis indisponible : le chauffeur n'est pas concerné, le worker relancera plus tard
        log.exception("Alerte %s non mise en file", alert_id)


def seed_demo():
    with SessionLocal() as db:
        if db.scalar(select(Company)):
            return
        company = Company(nom="Société démo")
        db.add(company)
        db.flush()
        create_default_template(db, company.id)
        db.add(Vehicle(company_id=company.id, plaque="AB-123-CD", token=DEMO_TOKEN))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_demo()  # le schéma vient d'Alembic : `alembic upgrade head`
    yield


app = FastAPI(title="Transport SaaS", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(checklist_router)
app.include_router(exploitation_router)
app.include_router(flotte_router)
app.include_router(conducteurs_router)


def vehicle_by_token(token: str, db: Session) -> Vehicle:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.token == token, Vehicle.actif.is_(True)))
    if not vehicle:
        raise HTTPException(404, "Véhicule inconnu")
    return vehicle


@app.get("/api/health")
def health():
    return {"ok": True}


# --- Routes chauffeur : pas de compte, le jeton du QR code fait foi ---


def _items_or_409(db: Session, v: Vehicle):
    items = active_items(db, v.company_id, v.type)
    if not items:
        raise HTTPException(409, "Aucune checklist configurée pour ce véhicule")
    return items


@app.get("/api/controle/{token}")
def get_controle(token: str, db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    checklist = [{"id": i.id, "libelle": i.libelle, "critique": i.critique} for i in _items_or_409(db, v)]
    return {"plaque": v.plaque, "bloque": v.bloque, "checklist": checklist}


class Reponse(BaseModel):
    id: int
    ok: bool
    commentaire: str = ""


class ControleIn(BaseModel):
    conducteur: str | None = Field(default=None, min_length=1, max_length=100)  # saisi à la main (hors ligne)
    badge: str | None = Field(default=None, max_length=200)  # remis après identification par PIN
    reponses: list[Reponse]
    signature: str | None = Field(default=None, max_length=300_000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    client_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    fait_le: datetime | None = None  # heure réelle du contrôle si le téléphone était hors ligne

    @model_validator(mode="after")
    def check_extras(self):
        if self.signature and not self.signature.startswith("data:image/png;base64,"):
            raise ValueError("Signature : PNG attendu")
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Position incomplète")
        if not self.badge and not (self.conducteur and self.conducteur.strip()):
            raise ValueError("Conducteur : identifiez-vous avec votre code ou saisissez votre nom")
        return self


FAIT_LE_MAX_AGE = timedelta(days=7)
login_pin_echecs: dict[str, list[float]] = {}
PIN_MAX_ECHECS, PIN_FENETRE = 5, 15 * 60


class IdentifierIn(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")


@app.post("/api/controle/{token}/identifier")
def identifier(token: str, body: IdentifierIn, db: Session = Depends(get_db)):
    """Le chauffeur saisit son code PIN : renvoie son nom et un badge signé valable 12 h."""
    import time
    v = vehicle_by_token(token, db)
    maintenant = time.monotonic()
    recents = [t for t in login_pin_echecs.get(token, []) if maintenant - t < PIN_FENETRE]
    login_pin_echecs[token] = recents
    if len(recents) >= PIN_MAX_ECHECS:
        raise HTTPException(429, "Trop d'essais, réessayez dans quelques minutes")
    d = db.scalar(select(Driver).where(Driver.company_id == v.company_id, Driver.pin_hash == hash_pin(v.company_id, body.pin),
                                       Driver.actif.is_(True)))
    if not d:
        recents.append(maintenant)
        raise HTTPException(401, "Code inconnu")
    login_pin_echecs.pop(token, None)
    badge, expire = signer_badge(d.id, v.company_id)
    return {"nom": d.nom, "badge": badge, "expire": expire}


def _reponse_controle(check: Check, v: Vehicle) -> dict:
    return {"id": check.id, "defaut_critique": check.defaut_critique, "bloque": v.bloque}


@app.post("/api/controle/{token}", status_code=201)
def post_controle(token: str, body: ControleIn, background: BackgroundTasks, response: Response,
                  db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    if body.client_id:  # envoi rejoué (réseau coupé puis rétabli) : on renvoie le contrôle déjà enregistré
        deja = db.scalar(select(Check).where(Check.company_id == v.company_id, Check.client_id == body.client_id))
        if deja:
            response.status_code = 200
            return _reponse_controle(deja, v)
    items = {i.id: i for i in _items_or_409(db, v)}
    if sorted(r.id for r in body.reponses) != sorted(items):
        raise HTTPException(422, "Tous les points de la checklist doivent être renseignés")
    conducteur_id, nom = None, (body.conducteur or "").strip()
    if body.badge:
        conducteur_id = lire_badge(body.badge, v.company_id)
        d = db.get(Driver, conducteur_id) if conducteur_id else None
        if not d or d.company_id != v.company_id or not d.actif:
            raise HTTPException(401, "Badge invalide ou expiré : identifiez-vous à nouveau")
        nom = d.nom
    snapshot = [
        {"id": r.id, "libelle": items[r.id].libelle, "critique": items[r.id].critique,
         "ok": r.ok, "commentaire": r.commentaire}
        for r in body.reponses
    ]
    defaut = any(not r["ok"] and r["critique"] for r in snapshot)
    maintenant = datetime.now(timezone.utc)
    fait_le = body.fait_le
    if fait_le is not None:
        fait_le = fait_le.replace(tzinfo=timezone.utc) if fait_le.tzinfo is None else fait_le.astimezone(timezone.utc)
        if not (maintenant - FAIT_LE_MAX_AGE <= fait_le <= maintenant + timedelta(minutes=5)):
            fait_le = None  # horloge du téléphone aberrante : on retient l'heure d'arrivée
    check = Check(company_id=v.company_id, vehicle_id=v.id, conducteur=nom, conducteur_id=conducteur_id,
                  reponses=snapshot, defaut_critique=defaut, has_defaut=any(not r["ok"] for r in snapshot),
                  signature=body.signature, lat=body.lat, lng=body.lng, client_id=body.client_id,
                  recu_le=maintenant, created_at=fait_le or maintenant)
    db.add(check)
    alert = None
    if defaut:
        v.bloque = True
        db.flush()
        recipients = db.get(Company, v.company_id).alert_emails
        alert = Alert(company_id=v.company_id, check_id=check.id,
                      statut="en_attente" if recipients else "sans_destinataire")
        db.add(alert)
    try:
        db.commit()
    except IntegrityError:  # deux envois simultanés du même client_id : le second renvoie le premier
        db.rollback()
        deja = db.scalar(select(Check).where(Check.company_id == v.company_id, Check.client_id == body.client_id))
        if not deja:
            raise
        response.status_code = 200
        return _reponse_controle(deja, v)
    if alert and alert.statut == "en_attente":
        background.add_task(enqueue_alert, alert.id)  # après la réponse au chauffeur
    return _reponse_controle(check, v)


PHOTO_WINDOW = timedelta(hours=1)  # on ne peut ajouter des photos qu'au contrôle qu'on vient d'envoyer


@app.post("/api/controle/{token}/{check_id}/photos", status_code=201)
async def post_photo(token: str, check_id: int, photo: UploadFile = File(), db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    check = db.scalar(select(Check).where(Check.id == check_id, Check.vehicle_id == v.id))
    if not check:
        raise HTTPException(404, "Contrôle inconnu")
    created = check.recu_le.replace(tzinfo=timezone.utc) if check.recu_le.tzinfo is None else check.recu_le
    if datetime.now(timezone.utc) - created > PHOTO_WINDOW:
        raise HTTPException(403, "Délai d'ajout de photos dépassé")
    count = len(db.scalars(select(CheckPhoto.id).where(CheckPhoto.check_id == check.id)).all())
    if count >= photos.MAX_PER_CHECK:
        raise HTTPException(409, "Nombre maximal de photos atteint")
    data = await photo.read(photos.MAX_BYTES + 1)
    if len(data) > photos.MAX_BYTES:
        raise HTTPException(413, "Photo trop lourde (5 Mo maximum)")
    ext = photos.detect_ext(data)
    if not ext:
        raise HTTPException(415, "Format accepté : JPEG ou PNG")
    row = CheckPhoto(company_id=v.company_id, check_id=check.id, fichier=photos.save(v.company_id, data, ext))
    db.add(row)
    db.commit()
    return {"id": row.id}

