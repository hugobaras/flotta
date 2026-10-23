import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .checklists import CHECKLIST
from .db import Base, SessionLocal, engine, get_db
from .models import Check, Company, Vehicle

DEMO_TOKEN = "demo"


def seed_demo():
    with SessionLocal() as db:
        if db.scalar(select(Company)):
            return
        # Clé de démo : à surcharger via l'environnement hors développement.
        company = Company(nom="Société démo", api_key=os.getenv("DEMO_API_KEY", "dev-demo-key"))
        db.add(company)
        db.flush()
        db.add(Vehicle(company_id=company.id, plaque="AB-123-CD", token=DEMO_TOKEN))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Provisoire : create_all sera remplacé par Alembic à l'étape 1.
    Base.metadata.create_all(engine)
    seed_demo()
    yield


app = FastAPI(title="Transport SaaS", lifespan=lifespan)


def current_company(x_api_key: str = Header(), db: Session = Depends(get_db)) -> Company:
    company = db.scalar(select(Company).where(Company.api_key == x_api_key))
    if not company:
        raise HTTPException(401, "Clé API invalide")
    return company


def vehicle_by_token(token: str, db: Session) -> Vehicle:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.token == token))
    if not vehicle:
        raise HTTPException(404, "Véhicule inconnu")
    return vehicle


@app.get("/api/health")
def health():
    return {"ok": True}


# --- Routes chauffeur : pas de compte, le jeton du QR code fait foi ---


@app.get("/api/controle/{token}")
def get_controle(token: str, db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    return {"plaque": v.plaque, "bloque": v.bloque, "checklist": CHECKLIST}


class Reponse(BaseModel):
    id: str
    ok: bool
    commentaire: str = ""


class ControleIn(BaseModel):
    conducteur: str
    reponses: list[Reponse]


@app.post("/api/controle/{token}", status_code=201)
def post_controle(token: str, body: ControleIn, db: Session = Depends(get_db)):
    v = vehicle_by_token(token, db)
    critiques = {i["id"] for i in CHECKLIST if i["critique"]}
    answered = {r.id for r in body.reponses}
    if answered != {i["id"] for i in CHECKLIST}:
        raise HTTPException(422, "Tous les points de la checklist doivent être renseignés")
    defaut = any(not r.ok and r.id in critiques for r in body.reponses)
    check = Check(
        company_id=v.company_id,
        vehicle_id=v.id,
        conducteur=body.conducteur,
        reponses=[r.model_dump() for r in body.reponses],
        defaut_critique=defaut,
    )
    db.add(check)
    if defaut:
        v.bloque = True
    db.commit()
    return {"id": check.id, "defaut_critique": defaut, "bloque": v.bloque}


# --- Routes exploitant : toujours filtrées par company_id ---


@app.get("/api/admin/vehicules")
def list_vehicules(company: Company = Depends(current_company), db: Session = Depends(get_db)):
    rows = db.scalars(select(Vehicle).where(Vehicle.company_id == company.id))
    return [{"id": v.id, "plaque": v.plaque, "token": v.token, "bloque": v.bloque} for v in rows]


@app.get("/api/admin/controles")
def list_controles(company: Company = Depends(current_company), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Check).where(Check.company_id == company.id).order_by(Check.created_at.desc())
    )
    return [
        {"id": c.id, "vehicle_id": c.vehicle_id, "conducteur": c.conducteur,
         "defaut_critique": c.defaut_critique, "created_at": c.created_at}
        for c in rows
    ]


@app.post("/api/admin/vehicules/{vehicle_id}/debloquer")
def debloquer(vehicle_id: int, company: Company = Depends(current_company),
              db: Session = Depends(get_db)):
    v = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.company_id == company.id))
    if not v:
        raise HTTPException(404, "Véhicule inconnu")
    v.bloque = False
    db.commit()
    return {"id": v.id, "bloque": v.bloque}
