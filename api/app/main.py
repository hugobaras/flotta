from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user, router as auth_router
from .checklist_routes import router as checklist_router
from .checklists import active_items, create_default_template
from .db import SessionLocal, get_db
from .models import Check, Company, User, Vehicle

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
                  reponses=snapshot, defaut_critique=defaut)
    db.add(check)
    if defaut:
        v.bloque = True
    db.commit()
    return {"id": check.id, "defaut_critique": defaut, "bloque": v.bloque}


# --- Routes exploitant : toujours filtrées par company_id ---


@app.get("/api/admin/vehicules")
def list_vehicules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Vehicle).where(Vehicle.company_id == user.company_id))
    return [{"id": v.id, "plaque": v.plaque, "token": v.token, "bloque": v.bloque} for v in rows]


@app.get("/api/admin/controles")
def list_controles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Check).where(Check.company_id == user.company_id).order_by(Check.created_at.desc())
    )
    return [
        {"id": c.id, "vehicle_id": c.vehicle_id, "conducteur": c.conducteur,
         "defaut_critique": c.defaut_critique, "created_at": c.created_at, "reponses": c.reponses}
        for c in rows
    ]


@app.post("/api/admin/vehicules/{vehicle_id}/debloquer")
def debloquer(vehicle_id: int, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    v = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.company_id == user.company_id))
    if not v:
        raise HTTPException(404, "Véhicule inconnu")
    v.bloque = False
    db.commit()
    return {"id": v.id, "bloque": v.bloque}
