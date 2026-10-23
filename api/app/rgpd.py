"""Droits des conducteurs (RGPD) : export de leurs données et effacement, sur demande, par un administrateur."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import photos
from .audit import journaliser
from .auth import current_user
from .db import get_db
from .models import ActiviteConducteur, Check, CheckPhoto, Driver, Route, User, Vehicle

router = APIRouter(prefix="/api/admin/conducteurs")


def _admin_driver(db: Session, user: User, driver_id: int) -> Driver:
    if user.role not in ("admin", "plateforme"):
        raise HTTPException(403, "Réservé aux administrateurs")
    d = db.scalar(select(Driver).where(Driver.id == driver_id, Driver.company_id == user.company_id))
    if not d:
        raise HTTPException(404, "Conducteur inconnu")
    return d


@router.get("/{driver_id}/export")
def exporter(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _admin_driver(db, user, driver_id)
    controles = db.execute(select(Check, Vehicle.plaque).join(Vehicle, Vehicle.id == Check.vehicle_id).where(Check.conducteur_id == d.id).order_by(Check.created_at))
    activites = db.scalars(select(ActiviteConducteur).where(ActiviteConducteur.conducteur_id == d.id).order_by(ActiviteConducteur.debut))
    journaliser(db, user, "export_conducteur", f"conducteur {d.id}")
    db.commit()
    return {"conducteur": {"id": d.id, "nom": d.nom, "email": d.email, "actif": d.actif},
            "controles": [{"date": c.created_at, "plaque": plaque, "reponses": c.reponses, "position": [c.lat, c.lng] if c.lat is not None else None,
                           "signature": c.signature is not None} for c, plaque in controles],
            "activites": [{"type": a.type, "debut": a.debut, "fin": a.fin} for a in activites]}


@router.delete("/{driver_id}/donnees", status_code=204)
def effacer(driver_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Efface le conducteur et ses données personnelles. Les contrôles restent (obligation de suivi du parc) mais sont anonymisés :
    nom remplacé, signature, position et photos supprimées."""
    d = _admin_driver(db, user, driver_id)
    ids = list(db.scalars(select(Check.id).where(Check.conducteur_id == d.id)))
    if ids:
        for p in db.scalars(select(CheckPhoto).where(CheckPhoto.check_id.in_(ids))):
            photos.path(user.company_id, p.fichier).unlink(missing_ok=True)
        db.execute(delete(CheckPhoto).where(CheckPhoto.check_id.in_(ids)))
        db.execute(update(Check).where(Check.id.in_(ids)).values(conducteur="Conducteur supprimé", conducteur_id=None, signature=None, lat=None, lng=None))
    db.execute(delete(ActiviteConducteur).where(ActiviteConducteur.conducteur_id == d.id))
    db.execute(update(Route).where(Route.conducteur_id == d.id).values(conducteur_id=None))
    journaliser(db, user, "effacement_conducteur", f"conducteur {d.id}")
    db.delete(d)
    db.commit()
    return Response(status_code=204)
