import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import conduite
from . import regulations as reg
from .audit import journaliser
from .auth import current_user
from .badge import hash_pin, nouveau_pin
from .db import get_db
from .offres import exige
from .models import ActiviteConducteur, Check, Driver, User, Vehicle

router = APIRouter(prefix="/api/admin/conducteurs")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)  # isolé pour pouvoir figer l'horloge dans les tests


def _sortie(d: Driver, plaque: str | None) -> dict:
    return {"id": d.id, "nom": d.nom, "actif": d.actif, "vehicule_habituel_id": d.vehicule_habituel_id,
            "vehicule_habituel": plaque, "email": d.email}


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


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(v: str | None) -> str | None:
    v = (v or "").strip().lower()
    if not v:
        return None
    if not EMAIL.match(v) or len(v) > 254:
        raise ValueError("Adresse email invalide")
    return v


class ConducteurIn(BaseModel):
    nom: str = Field(min_length=2, max_length=100)
    vehicule_habituel_id: int | None = None
    email: str | None = None

    @field_validator("email")
    @classmethod
    def email_valide(cls, v):
        return _email(v)


@router.post("", status_code=201)
def creer(body: ConducteurIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _verifier_vehicule(db, user, body.vehicule_habituel_id)
    pin, h = _pin_libre(db, user.company_id)
    d = Driver(company_id=user.company_id, nom=body.nom.strip(), pin_hash=h, vehicule_habituel_id=body.vehicule_habituel_id, email=body.email)
    db.add(d)
    db.commit()
    # Le PIN n'est montré qu'une fois : en base il n'existe que sous forme de HMAC.
    return {**_sortie(d, _plaque(db, d.vehicule_habituel_id)), "pin": pin}


class ConducteurPatch(BaseModel):
    nom: str | None = Field(default=None, min_length=2, max_length=100)
    vehicule_habituel_id: int | None = None
    actif: bool | None = None
    reinitialiser_pin: bool = False
    email: str | None = None

    @field_validator("email")
    @classmethod
    def email_valide(cls, v):
        return _email(v)


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
    if "email" in champs:
        d.email = body.email
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
    journaliser(db, user, "suppression_conducteur", f"conducteur {d.id}")
    db.delete(d)
    db.commit()
    return Response(status_code=204)


# --- Temps de conduite : activités déclarées et compteurs (règlement CE 561/2006) ---


class ActiviteIn(BaseModel):
    type: str
    debut: datetime
    fin: datetime

    @field_validator("type")
    @classmethod
    def type_valide(cls, v: str) -> str:
        if v not in reg.activites.TYPES:
            raise ValueError("Type inconnu : conduite, travail, disponibilite ou repos")
        return v

    @model_validator(mode="after")
    def coherente(self):
        if self.debut.tzinfo is None or self.fin.tzinfo is None:
            raise ValueError("Précisez le fuseau horaire (par exemple +01:00)")
        if self.fin <= self.debut:
            raise ValueError("La fin doit être après le début")
        if self.fin - self.debut > timedelta(hours=24):
            raise ValueError("Une activité dure 24 h au plus")
        self.debut, self.fin = self.debut.astimezone(timezone.utc), self.fin.astimezone(timezone.utc)  # tout est comparé en UTC
        return self


class ActivitesIn(BaseModel):
    activites: list[ActiviteIn] = Field(min_length=1, max_length=200)


def _sortie_activite(a: ActiviteConducteur) -> dict:
    return {"id": a.id, "type": a.type, "debut": a.debut, "fin": a.fin}


@router.get("/{driver_id}/activites")
def lister_activites(driver_id: int, jours: int = 15, user: User = Depends(exige("conduite")), db: Session = Depends(get_db)):
    d = _driver(db, user, driver_id)
    depuis = maintenant() - timedelta(days=max(1, min(jours, 60)))
    rows = db.scalars(select(ActiviteConducteur).where(ActiviteConducteur.conducteur_id == d.id, ActiviteConducteur.fin > depuis)
                      .order_by(ActiviteConducteur.debut))
    return [_sortie_activite(a) for a in rows]


@router.post("/{driver_id}/activites", status_code=201)
def declarer_activites(driver_id: int, body: ActivitesIn, user: User = Depends(exige("conduite")), db: Session = Depends(get_db)):
    d = _driver(db, user, driver_id)
    ref = maintenant()
    for a in body.activites:
        if a.debut < ref - timedelta(days=60) or a.fin > ref + timedelta(days=2):
            raise HTTPException(422, "Les activités doivent se situer dans les 60 derniers jours (ou demain au plus tard)")
    lot = sorted(body.activites, key=lambda a: a.debut)
    for x, y in zip(lot, lot[1:]):
        if y.debut < x.fin:
            raise HTTPException(409, "Deux activités déclarées se chevauchent")
    existantes = list(db.scalars(select(ActiviteConducteur).where(
        ActiviteConducteur.conducteur_id == d.id, ActiviteConducteur.fin > lot[0].debut, ActiviteConducteur.debut < lot[-1].fin)))
    for a in lot:
        for e in existantes:
            efin, edebut = e.fin.replace(tzinfo=e.fin.tzinfo or timezone.utc), e.debut.replace(tzinfo=e.debut.tzinfo or timezone.utc)
            if a.debut < efin and a.fin > edebut:
                raise HTTPException(409, "Une activité déclarée chevauche une activité déjà enregistrée")
    lignes = [ActiviteConducteur(company_id=user.company_id, conducteur_id=d.id, type=a.type, debut=a.debut, fin=a.fin) for a in lot]
    db.add_all(lignes)
    db.commit()
    return [_sortie_activite(a) for a in lignes]


@router.delete("/{driver_id}/activites/{activite_id}", status_code=204)
def supprimer_activite(driver_id: int, activite_id: int, user: User = Depends(exige("conduite")), db: Session = Depends(get_db)):
    d = _driver(db, user, driver_id)
    a = db.scalar(select(ActiviteConducteur).where(ActiviteConducteur.id == activite_id, ActiviteConducteur.conducteur_id == d.id))
    if not a:
        raise HTTPException(404, "Activité inconnue")
    db.delete(a)
    db.commit()
    return Response(status_code=204)


@router.get("/{driver_id}/compteurs")
def compteurs(driver_id: int, instant: datetime | None = None, user: User = Depends(exige("conduite")), db: Session = Depends(get_db)):
    """Temps de conduite restants du conducteur à l'instant donné (maintenant par défaut), et infractions de l'historique."""
    d = _driver(db, user, driver_id)
    if instant is not None and instant.tzinfo is None:
        raise HTTPException(422, "Précisez le fuseau horaire de l'instant (par exemple +01:00)")
    t = conduite.minutes(instant or maintenant())
    histo = conduite.historique(db, d.id, t)
    r = reg.restant(histo, t)
    analyse = reg.analyser(histo)
    return {
        "conduite_continue_min": round(r.conduite_continue), "pause_necessaire_min": round(r.pause_necessaire),
        "conduite_jour_min": round(r.conduite_jour), "conduite_jour_normale_min": round(r.conduite_jour_normale),
        "extensions_restantes": r.extensions_restantes, "conduite_semaine_min": round(r.conduite_semaine),
        "debut_possible": conduite.instant(r.debut_possible), "debut_possible_reduit": conduite.instant(r.debut_possible_reduit),
        "infractions": [{"code": i.code, "message": i.message, "debut": conduite.instant(i.debut), "fin": conduite.instant(i.fin)} for i in analyse.infractions],
        "notes": analyse.notes,
    }
