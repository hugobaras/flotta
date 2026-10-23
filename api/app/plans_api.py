import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import plans
from .auth import current_user
from .db import get_db
from .offres import exige
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
    affectations: dict[int, int] | None = None  # véhicule -> conducteur ; sinon le conducteur habituel du véhicule
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


class Affectation(BaseModel):
    vehicle_id: int
    conducteur_id: int | None = None


@router.post("/{plan_id}/affecter")
def affecter(plan_id: int, body: Affectation, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plan(db, user, plan_id)
    return _appliquer(db, p, lambda: plans.affecter(db, p, body.vehicle_id, body.conducteur_id))


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


# --- Suivi en direct et propositions de replanification (validation explicite requise) ---


@router.get("/{plan_id}/suivi")
def suivi_direct(plan_id: int, user: User = Depends(exige("temps_reel")), db: Session = Depends(get_db)):
    from . import livraisons, suivi
    p = _plan(db, user, plan_id)
    _terminé(p)
    return suivi.suivi(db, p, livraisons.maintenant())


class DemandePropositions(BaseModel):
    type: str = Field(pattern=r"^(retard|urgence|panne)$")
    order_id: int | None = None  # commande urgente
    vehicle_id: int | None = None  # camion en panne


def _commande_urgente(db: Session, user: User, p: Plan, order_id: int | None):
    from .models import Order
    if order_id is None:
        raise HTTPException(422, "Indiquez la commande urgente")
    o = db.scalar(select(Order).where(Order.id == order_id, Order.company_id == user.company_id))
    if not o:
        raise HTTPException(404, "Commande inconnue")
    if o.date_livraison != p.jour:
        raise HTTPException(409, "Cette commande n'est pas prévue le jour de ce plan")
    if o.lat is None:
        raise HTTPException(409, "L'adresse de cette commande n'est pas localisée : corrigez-la d'abord")
    if o.statut in ("livre", "echec", "annule"):
        raise HTTPException(409, "Cette commande est déjà clôturée")
    if any(a["order_id"] == o.id for r in plans.charger_etat(db, p)["routes"] for a in r["arrets"]):
        raise HTTPException(409, "Cette commande est déjà dans une tournée de ce plan")
    return o


@router.post("/{plan_id}/propositions")
def propositions(plan_id: int, body: DemandePropositions, user: User = Depends(exige("temps_reel")), db: Session = Depends(get_db)):
    """Propose 2 à 3 solutions chiffrées. Lecture seule : le plan n'est jamais modifié ici."""
    from . import livraisons, suivi
    from .routage import RouteurIndisponible
    p = _plan(db, user, plan_id)
    _terminé(p)
    order = _commande_urgente(db, user, p, body.order_id) if body.type == "urgence" else None
    if body.type == "panne":
        if body.vehicle_id is None or not any(r["vehicle_id"] == body.vehicle_id for r in plans.charger_etat(db, p)["routes"]):
            raise HTTPException(404, "Véhicule absent de ce plan")
    try:
        liste = suivi.proposer(db, p, body.type, livraisons.maintenant(), order, body.vehicle_id)
    except RouteurIndisponible:
        raise HTTPException(503, "Le service de routage est indisponible : impossible de chiffrer l'insertion d'une nouvelle commande.")
    return {"propositions": liste, "avertissement": "Rien n'est modifié tant que vous n'avez pas validé une proposition."}


class Action(BaseModel):
    order_id: int
    vehicle_id: int | None = None
    position: int | None = Field(default=None, ge=0)


class Validation(BaseModel):
    type: str = Field(pattern=r"^(retard|urgence|panne)$")
    actions: list[Action] = Field(min_length=1, max_length=100)
    order_id: int | None = None
    vehicle_id: int | None = None


@router.post("/{plan_id}/propositions/appliquer")
def appliquer_proposition(plan_id: int, body: Validation, user: User = Depends(exige("temps_reel")), db: Session = Depends(get_db)):
    """Applique une proposition validée par l'exploitant (une seule étape d'historique, annulable)."""
    from . import suivi
    from .routage import RouteurIndisponible
    p = _plan(db, user, plan_id)
    order = _commande_urgente(db, user, p, body.order_id) if body.type == "urgence" else None
    if body.type == "urgence" and not any(a.order_id == order.id for a in body.actions):
        raise HTTPException(422, "L'action doit placer la commande urgente")
    try:
        return _appliquer(db, p, lambda: suivi.appliquer(db, p, body.type, [a.model_dump() for a in body.actions], order, body.vehicle_id))
    except RouteurIndisponible:
        db.rollback()
        raise HTTPException(503, "Le service de routage est indisponible : impossible d'insérer une nouvelle commande.")
