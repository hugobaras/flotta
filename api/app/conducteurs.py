from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .badge import hash_pin, nouveau_pin
from .db import get_db
from .models import Check, Driver, User, Vehicle

router = APIRouter(prefix="/api/admin/conducteurs")


def _sortie(d: Driver, plaque: str | None) -> dict:
    return {"id": d.id, "nom": d.nom, "actif": d.actif, "vehicule_habituel_id": d.vehicule_habituel_id,
            "vehicule_habituel": plaque}


def _plaque(db: Session, vehicle_id: int | None) -> str | None:
    return db.scalar(select(Vehicle.plaque).where(Vehicle.id == vehicle_id)) if vehicle_id else None


def _verifier_vehicule(db: Session, user: User, vehicle_id: int | None):
    if vehicle_id and not db.scalar(select(Vehicle.id).where(Vehicle.id == vehicle_id, Vehicle.company_id == user.company_id)):
        raise HTTPException(404, "Véhicule inconnu")


def _pin_libre(db: Session, company_id: int) -> tuple[str, str]:
    for _ in range(60):
        pin = nouveau_pin()
        h = hash_pin(company_id, pin)
        if not db.scalar(select(Driver.id).where(Driver.company_id == company_id, Driver.pin_hash == h)):
            return pin, h
    raise HTTPException(409, "Plus de code PIN disponible : désactivez des conducteurs inutilisés")


def _driver(db: Session, user: User, driver_id: int) -> Driver:
    d = db.scalar(select(Driver).where(Driver.id == driver_id, Driver.company_id == user.company_id))
    if not d:
        raise HTTPException(404, "Conducteur inconnu")
    return d


@router.get("")
def liste(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Driver, Vehicle.plaque).outerjoin(Vehicle, Vehicle.id == Driver.vehicule_habituel_id)
        .where(Driver.company_id == user.company_id).order_by(Driver.nom))
    return [_sortie(d, plaque) for d, plaque in rows]


class ConducteurIn(BaseModel):
    nom: str = Field(min_length=2, max_length=100)
    vehicule_habituel_id: int | None = None


@router.post("", status_code=201)
def creer(body: ConducteurIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _verifier_vehicule(db, user, body.vehicule_habituel_id)
    pin, h = _pin_libre(db, user.company_id)
    d = Driver(company_id=user.company_id, nom=body.nom.strip(), pin_hash=h, vehicule_habituel_id=body.vehicule_habituel_id)
    db.add(d)
    db.commit()
    # Le PIN n'est montré qu'une fois : en base il n'existe que sous forme de HMAC.
    return {**_sortie(d, _plaque(db, d.vehicule_habituel_id)), "pin": pin}


class ConducteurPatch(BaseModel):
    nom: str | None = Field(default=None, min_length=2, max_length=100)
    vehicule_habituel_id: int | None = None
    actif: bool | None = None
    reinitialiser_pin: bool = False


@router.patch("/{driver_id}")
def modifier(driver_id: int, body: ConducteurPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _driver(db, user, driver_id)
    champs = body.model_dump(exclude_unset=True)
    if "vehicule_habituel_id" in champs:
        _verifier_vehicule(db, user, champs["vehicule_habituel_id"])
        d.vehicule_habituel_id = champs["vehicule_habituel_id"]
    if body.nom:
        d.nom = body.nom.strip()
    if body.actif is not None:
        d.actif = body.actif
    pin = None
    if body.reinitialiser_pin:
        pin, d.pin_hash = _pin_libre(db, user.company_id)
    db.commit()
    out = _sortie(d, _plaque(db, d.vehicule_habituel_id))
    return {**out, "pin": pin} if pin else out


@router.delete("/{driver_id}", status_code=204)
def supprimer(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _driver(db, user, driver_id)
    if db.scalar(select(Check.id).where(Check.conducteur_id == d.id)):
        raise HTTPException(409, "Ce conducteur a des contrôles enregistrés : désactivez-le plutôt que de le supprimer")
    db.delete(d)
    db.commit()
    return Response(status_code=204)
