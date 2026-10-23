from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import geocodage
from .auth import current_user
from .db import get_db
from .models import Depot, User

router = APIRouter(prefix="/api/admin/depots")
HEURE = r"^([01]\d|2[0-3]):[0-5]\d$"


def _sortie(d: Depot) -> dict:
    return {"id": d.id, "nom": d.nom, "adresse": d.adresse, "lat": d.lat, "lng": d.lng, "ouverture": d.ouverture,
            "fermeture": d.fermeture, "par_defaut": d.par_defaut}


def _depot(db: Session, user: User, depot_id: int) -> Depot:
    d = db.scalar(select(Depot).where(Depot.id == depot_id, Depot.company_id == user.company_id))
    if not d:
        raise HTTPException(404, "Dépôt inconnu")
    return d


def _un_seul_defaut(db: Session, company_id: int, garder: Depot):
    for d in db.scalars(select(Depot).where(Depot.company_id == company_id, Depot.id != garder.id)):
        d.par_defaut = False


@router.get("")
def lister(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_sortie(d) for d in db.scalars(select(Depot).where(Depot.company_id == user.company_id).order_by(Depot.nom))]


class DepotIn(BaseModel):
    nom: str = Field(min_length=2, max_length=100)
    adresse: str = Field(min_length=3, max_length=300)
    ouverture: str = Field(default="06:00", pattern=HEURE)
    fermeture: str = Field(default="19:00", pattern=HEURE)
    par_defaut: bool = False
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


def _geo(db: Session, d: Depot):
    try:
        r = geocodage.geocoder_une(db, d.adresse)
        if r.lat is not None:
            d.lat, d.lng = r.lat, r.lng
    except geocodage.GeocodageIndisponible:
        pass  # position à renseigner plus tard


@router.post("", status_code=201)
def creer(body: DepotIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.ouverture >= body.fermeture:
        raise HTTPException(422, "La fermeture doit être après l'ouverture")
    premier = db.scalar(select(Depot.id).where(Depot.company_id == user.company_id)) is None
    d = Depot(company_id=user.company_id, nom=body.nom.strip(), adresse=body.adresse.strip(), ouverture=body.ouverture,
              fermeture=body.fermeture, par_defaut=body.par_defaut or premier, lat=body.lat, lng=body.lng)
    db.add(d)
    if d.lat is None:
        _geo(db, d)
    db.flush()
    if d.par_defaut:
        _un_seul_defaut(db, user.company_id, d)
    db.commit()
    return _sortie(d)


class DepotPatch(BaseModel):
    nom: str | None = Field(default=None, min_length=2, max_length=100)
    adresse: str | None = Field(default=None, min_length=3, max_length=300)
    ouverture: str | None = Field(default=None, pattern=HEURE)
    fermeture: str | None = Field(default=None, pattern=HEURE)
    par_defaut: bool | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


@router.patch("/{depot_id}")
def modifier(depot_id: int, body: DepotPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _depot(db, user, depot_id)
    champs = body.model_dump(exclude_unset=True)
    adresse_changee = "adresse" in champs and champs["adresse"] != d.adresse
    for k in ("nom", "adresse", "ouverture", "fermeture"):
        if champs.get(k) is not None:
            setattr(d, k, champs[k].strip() if k in ("nom", "adresse") else champs[k])
    if d.ouverture >= d.fermeture:
        raise HTTPException(422, "La fermeture doit être après l'ouverture")
    if champs.get("lat") is not None and champs.get("lng") is not None:
        d.lat, d.lng = champs["lat"], champs["lng"]
    elif adresse_changee:
        d.lat = d.lng = None
        _geo(db, d)
    if champs.get("par_defaut"):
        d.par_defaut = True
        _un_seul_defaut(db, user.company_id, d)
    elif champs.get("par_defaut") is False and d.par_defaut:
        raise HTTPException(409, "Choisissez un autre dépôt par défaut plutôt que de retirer celui-ci")
    db.commit()
    return _sortie(d)


@router.delete("/{depot_id}", status_code=204)
def supprimer(depot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _depot(db, user, depot_id)
    autres = list(db.scalars(select(Depot).where(Depot.company_id == user.company_id, Depot.id != d.id).order_by(Depot.nom)))
    if not autres:
        raise HTTPException(409, "Une société doit garder au moins un dépôt")
    if d.par_defaut:
        autres[0].par_defaut = True
    db.delete(d)
    db.commit()
    return Response(status_code=204)
