from contextlib import asynccontextmanager

from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user, router as auth_router
from . import photos
from .checklist_routes import router as checklist_router
from .checklists import active_items, create_default_template
from .db import SessionLocal, get_db
from .exploitation import router as exploitation_router
from .models import Check, CheckPhoto, Company, User, Vehicle

DEMO_TOKEN = "demo"


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


def vehicle_by_token(token: str, db: Session) -> Vehicle:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.token == token))
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
    conducteur: str
    reponses: list[Reponse]
    signature: str | None = Field(default=None, max_length=300_000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def check_extras(self):
        if self.signature and not self.signature.startswith("data:image/png;base64,"):
            raise ValueError("Signature : PNG attendu")
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Position incomplète")
        return self


@app.post("/api/controle/{token}", status_code=201)
def post_controle(token: str, body: ControleIn, db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    items = {i.id: i for i in _items_or_409(db, v)}
    if sorted(r.id for r in body.reponses) != sorted(items):
        raise HTTPException(422, "Tous les points de la checklist doivent être renseignés")
    snapshot = [
        {"id": r.id, "libelle": items[r.id].libelle, "critique": items[r.id].critique,
         "ok": r.ok, "commentaire": r.commentaire}
        for r in body.reponses
    ]
    defaut = any(not r["ok"] and r["critique"] for r in snapshot)
    check = Check(company_id=v.company_id, vehicle_id=v.id, conducteur=body.conducteur,
                  reponses=snapshot, defaut_critique=defaut, has_defaut=any(not r["ok"] for r in snapshot),
                  signature=body.signature, lat=body.lat, lng=body.lng)
    db.add(check)
    if defaut:
        v.bloque = True
    db.commit()
    return {"id": check.id, "defaut_critique": defaut, "bloque": v.bloque}


PHOTO_WINDOW = timedelta(hours=1)  # on ne peut ajouter des photos qu'au contrôle qu'on vient d'envoyer


@app.post("/api/controle/{token}/{check_id}/photos", status_code=201)
async def post_photo(token: str, check_id: int, photo: UploadFile = File(), db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    check = db.scalar(select(Check).where(Check.id == check_id, Check.vehicle_id == v.id))
    if not check:
        raise HTTPException(404, "Contrôle inconnu")
    created = check.created_at.replace(tzinfo=timezone.utc) if check.created_at.tzinfo is None else check.created_at
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


# --- Routes exploitant : toujours filtrées par company_id ---


@app.get("/api/admin/vehicules")
def list_vehicules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Vehicle).where(Vehicle.company_id == user.company_id))
    return [{"id": v.id, "plaque": v.plaque, "token": v.token, "bloque": v.bloque} for v in rows]
