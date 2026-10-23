import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import plans
from .auth import current_user
from .db import get_db
from .models import Depot, Plan, PlanSnapshot, Route, RouteStop, User, Vehicle

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/plans")


def enqueue_plan(plan_id: int) -> None:
    from .worker import calculer_plan
    calculer_plan.apply_async(args=[plan_id], retry=False)


class PlanIn(BaseModel):
    jour: date
    vehicle_ids: list[int] | None = Field(default=None, max_length=200)
    depot_id: int | None = None
    temps_max_s: int = Field(default=10, ge=1, le=120)  # temps de calcul maximal
    duree_max_min: int = Field(default=600, ge=60, le=900)  # durée maximale d'une tournée


def _plan(db: Session, user: User, plan_id: int) -> Plan:
    p = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.company_id == user.company_id))
    if not p:
        raise HTTPException(404, "Plan inconnu")
    return p


@router.post("", status_code=202)
def creer(body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.vehicle_ids:
        n = len(db.scalars(select(Vehicle.id).where(Vehicle.company_id == user.company_id, Vehicle.id.in_(body.vehicle_ids))).all())
        if n != len(set(body.vehicle_ids)):
            raise HTTPException(404, "Véhicule inconnu")
    if body.depot_id and not db.scalar(select(Depot.id).where(Depot.id == body.depot_id, Depot.company_id == user.company_id)):
        raise HTTPException(404, "Dépôt inconnu")
    plan = Plan(company_id=user.company_id, jour=body.jour, parametres=body.model_dump(mode="json", exclude={"jour"}))
    db.add(plan)
    db.commit()
    try:
        enqueue_plan(plan.id)
    except Exception:  # noqa: BLE001 : Redis indisponible
        log.exception("Plan %s : file de tâches indisponible", plan.id)
        db.delete(plan)
        db.commit()
        raise HTTPException(503, "La file de calcul est indisponible : le plan n'a pas été lancé. Réessayez dans un instant.")
    return {"id": plan.id, "statut": plan.statut}


@router.get("")
def lister(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Plan).where(Plan.company_id == user.company_id).order_by(Plan.id.desc()).limit(50))
    return [{"id": p.id, "jour": p.jour, "statut": p.statut, "progression": p.progression, "resume": p.resume,
             "created_at": p.created_at} for p in rows]


@router.get("/{plan_id}")
def lire(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return plans.detail(db, _plan(db, user, plan_id))


@router.delete("/{plan_id}", status_code=204)
def supprimer(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    db.execute(delete(PlanSnapshot).where(PlanSnapshot.plan_id == p.id))
    for r in db.scalars(select(Route).where(Route.plan_id == p.id)):
        for s in db.scalars(select(RouteStop).where(RouteStop.route_id == r.id)):
            db.delete(s)
        db.delete(r)
    db.delete(p)
    db.commit()
    return Response(status_code=204)


# --- Modifications manuelles : recalcul immédiat des heures et des alertes, sans relancer l'optimisation ---


def _terminé(p: Plan):
    if p.statut != "termine":
        raise HTTPException(409, "Le plan n'est pas encore calculé")


def _appliquer(db: Session, p: Plan, action):
    _terminé(p)
    try:
        action()
        db.commit()
    except plans.ModificationRefusee as e:
        db.rollback()
        raise HTTPException(e.statut, str(e))
    return plans.detail(db, p)


class Deplacement(BaseModel):
    order_id: int
    vehicle_id: int | None = None  # None : devient non affectée
    position: int | None = Field(default=None, ge=0)


@router.post("/{plan_id}/deplacer")
def deplacer(plan_id: int, body: Deplacement, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    return _appliquer(db, p, lambda: plans.deplacer(db, p, body.order_id, body.vehicle_id, body.position))


class Verrou(BaseModel):
    vehicle_id: int | None = None
    order_id: int | None = None
    verrouille: bool = True


@router.post("/{plan_id}/verrouiller")
def verrouiller(plan_id: int, body: Verrou, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    return _appliquer(db, p, lambda: plans.verrouiller(db, p, body.vehicle_id, body.order_id, body.verrouille))


@router.post("/{plan_id}/annuler")
def annuler(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    return _appliquer(db, p, lambda: plans.annuler(db, p))


@router.post("/{plan_id}/retablir")
def retablir(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    return _appliquer(db, p, lambda: plans.retablir(db, p))


class VersionIn(BaseModel):
    nom: str = Field(min_length=1, max_length=100)


@router.post("/{plan_id}/versions", status_code=201)
def enregistrer_version(plan_id: int, body: VersionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    _terminé(p)
    copie = plans.creer_version(db, p, body.nom)
    db.commit()
    return plans.detail(db, copie)


@router.post("/{plan_id}/reoptimiser", status_code=202)
def reoptimiser(plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Réoptimise le plan sans toucher aux tournées verrouillées (calcul en tâche de fond, comme le plan initial)."""
    p = _plan(db, user, plan_id)
    try:
        plans.lancer_reoptimisation(db, p)
    except plans.ModificationRefusee as e:
        raise HTTPException(e.statut, str(e))
    try:
        enqueue_plan(p.id)
    except Exception:  # noqa: BLE001
        log.exception("Plan %s : file de tâches indisponible", p.id)
        p.statut = "termine"
        p.parametres = {k: v for k, v in p.parametres.items() if k != "reoptimiser"}
        db.commit()
        raise HTTPException(503, "La file de calcul est indisponible : la réoptimisation n'a pas été lancée.")
    return {"id": p.id, "statut": p.statut}
