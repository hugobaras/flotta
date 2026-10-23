"""Construction, calcul et lecture des plans de tournées."""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import matrices, optimisation as opt, routage
from .models import Depot, Order, Plan, Route, RouteStop, Vehicle

log = logging.getLogger(__name__)


def _minutes(hhmm: str | None) -> int | None:
    return None if not hhmm else int(hhmm[:2]) * 60 + int(hhmm[3:5])


def _cle_profil(v: Vehicle) -> str:
    return f"{v.hauteur_m}|{v.largeur_m}|{v.longueur_m}|{v.ptac_kg}|{v.essieux}|{int(bool(v.adr))}"


def _progres(db: Session, plan: Plan, pct: int, message: str | None = None):
    plan.progression, plan.statut = pct, "en_cours" if pct < 100 else plan.statut
    if message:
        plan.message = message
    db.commit()


class PlanImpossible(Exception):
    pass


def executer(db: Session, plan_id: int) -> Plan:
    """Calcule le plan et enregistre tournées et arrêts. Toute erreur est consignée dans le plan, jamais perdue."""
    plan = db.get(Plan, plan_id)
    if not plan or plan.statut in ("termine", "en_cours"):
        return plan
    try:
        _executer(db, plan)
    except PlanImpossible as e:
        db.rollback()
        plan = db.get(Plan, plan_id)
        plan.statut, plan.message, plan.progression = "echec", str(e), 100
        db.commit()
    except routage.RouteurIndisponible:
        db.rollback()
        plan = db.get(Plan, plan_id)
        plan.statut, plan.progression = "echec", 100
        plan.message = "Le service de routage poids lourd est indisponible : le plan n'a pas pu être calculé (aucune estimation inventée). Réessayez plus tard."
        db.commit()
    except Exception:  # noqa: BLE001 : on garde la trace dans le plan puis on relève pour les journaux
        log.exception("Plan %s : erreur inattendue", plan_id)
        db.rollback()
        plan = db.get(Plan, plan_id)
        plan.statut, plan.message, plan.progression = "echec", "Erreur inattendue pendant le calcul. L'équipe technique a été prévenue par les journaux.", 100
        db.commit()
    return db.get(Plan, plan_id)


def _executer(db: Session, plan: Plan):
    p = plan.parametres
    _progres(db, plan, 5, "Préparation des données")
    depot = (db.get(Depot, p["depot_id"]) if p.get("depot_id")
             else db.scalar(select(Depot).where(Depot.company_id == plan.company_id, Depot.par_defaut.is_(True))))
    if not depot or depot.company_id != plan.company_id or depot.lat is None:
        raise PlanImpossible("Aucun dépôt localisé : ajoutez un dépôt avec une adresse trouvée avant de planifier.")

    non_affectees = []
    commandes = []
    for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.date_livraison == plan.jour,
                                            Order.statut.in_(["a_planifier", "planifie"])).order_by(Order.id)):
        if o.lat is None:
            non_affectees.append({"order_id": o.id, "raison": "Adresse non localisée : corrigez-la sur la carte"})
        else:
            commandes.append(o)
    if not commandes and not non_affectees:
        raise PlanImpossible("Aucune commande à planifier ce jour-là.")

    req = select(Vehicle).where(Vehicle.company_id == plan.company_id, Vehicle.actif.is_(True)).order_by(Vehicle.plaque)
    if p.get("vehicle_ids"):
        req = req.where(Vehicle.id.in_(p["vehicle_ids"]))
    vehicules, exclus = [], []
    for v in db.scalars(req):
        if v.bloque:
            exclus.append({"vehicle_id": v.id, "plaque": v.plaque, "raison": "Camion bloqué"})
        elif routage.gabarit_manquant(v):
            exclus.append({"vehicle_id": v.id, "plaque": v.plaque, "raison": "Gabarit incomplet : " + ", ".join(routage.gabarit_manquant(v))})
        else:
            vehicules.append(v)
    if not vehicules:
        raise PlanImpossible("Aucun véhicule disponible : tous sont bloqués, inactifs ou sans gabarit complet.")
    if not commandes:
        raise PlanImpossible("Aucune commande localisée à planifier ce jour-là.")

    _progres(db, plan, 15, "Calcul des temps de trajet")
    locations = [(depot.lat, depot.lng)] + [(o.lat, o.lng) for o in commandes]
    profils = {_cle_profil(v): routage.options_camion(v) for v in vehicules}
    mats = matrices.fournisseur(locations, profils)

    _progres(db, plan, 40, "Optimisation des tournées")
    probleme = opt.Probleme(
        vehicules=[opt.VehiculeOpt(v.id, _cle_profil(v), v.capacite_kg, v.capacite_m3, v.palettes, v.frigo, v.adr) for v in vehicules],
        commandes=[opt.CommandeOpt(o.id, o.poids_kg, o.volume_m3, o.palettes, _minutes(o.fenetre_debut), _minutes(o.fenetre_fin),
                                   o.duree_service_min, o.frigo, o.adr) for o in commandes],
        matrices={k: m["durations"] for k, m in mats.items()},
        ouverture_min=_minutes(depot.ouverture), fermeture_min=_minutes(depot.fermeture),
        duree_max_min=p.get("duree_max_min", 600), temps_calcul_s=p.get("temps_max_s", 10))
    solution = opt.optimiser(probleme)

    _progres(db, plan, 90, "Enregistrement du plan")
    index = {o.id: i + 1 for i, o in enumerate(commandes)}
    par_id = {o.id: o for o in commandes}
    par_vehicule = {v.id: v for v in vehicules}
    km_total = duree_total = charge_totale_kg = 0
    for r in solution.routes:
        v = par_vehicule[r.vehicule_id]
        dist = mats[_cle_profil(v)]["distances"]
        ligne_prec, km = 0, 0.0
        for a in r.arrets:
            km += dist[ligne_prec][index[a.commande_id]]
            ligne_prec = index[a.commande_id]
        km += dist[ligne_prec][0]
        cmds = [par_id[a.commande_id] for a in r.arrets]
        route = Route(company_id=plan.company_id, plan_id=plan.id, vehicle_id=v.id, depart_min=r.depart_min, retour_min=r.retour_min,
                      trajet_s=r.trajet_s, distance_km=round(km, 1), charge_kg=sum(o.poids_kg for o in cmds),
                      charge_palettes=sum(o.palettes for o in cmds), charge_m3=round(sum(o.volume_m3 for o in cmds), 2))
        db.add(route)
        db.flush()
        for n, a in enumerate(r.arrets, start=1):
            db.add(RouteStop(company_id=plan.company_id, route_id=route.id, ordre=n, order_id=a.commande_id,
                             arrivee_min=a.arrivee_min, depart_min=a.depart_min, attente_min=a.attente_min))
            par_id[a.commande_id].statut = "planifie"
        km_total += km
        duree_total += r.retour_min - r.depart_min
        charge_totale_kg += route.charge_kg
    for commande_id, raison in solution.non_affectees:
        non_affectees.append({"order_id": commande_id, "raison": raison})
    capacite_kg = sum(v.capacite_kg for v in vehicules if v.capacite_kg)
    plan.non_affectees = non_affectees
    plan.resume = {"km": round(km_total, 1), "duree_min": round(duree_total), "nb_tournees": len(solution.routes),
                   "nb_commandes": len(commandes), "nb_non_affectees": len(non_affectees), "vehicules_exclus": exclus,
                   "remplissage_pct": round(100 * charge_totale_kg / capacite_kg) if capacite_kg and solution.routes else None}
    plan.matrices = {"commandes": [0] + [o.id for o in commandes], "profils": {k: {"vehicle_ids": [v.id for v in vehicules if _cle_profil(v) == k], **m} for k, m in mats.items()}}
    plan.statut, plan.progression, plan.message = "termine", 100, None
    db.commit()


def detail(db: Session, plan: Plan) -> dict:
    routes = list(db.scalars(select(Route).where(Route.plan_id == plan.id).order_by(Route.id)))
    plaques = {v.id: v.plaque for v in db.scalars(select(Vehicle).where(Vehicle.company_id == plan.company_id))}
    ids = {s.order_id for r in routes for s in db.scalars(select(RouteStop).where(RouteStop.route_id == r.id))} | {n["order_id"] for n in plan.non_affectees}
    commandes = {o.id: o for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(ids)))} if ids else {}

    def cmd(o: Order | None):
        return {"reference": o.reference, "client": o.client, "adresse": o.adresse, "lat": o.lat, "lng": o.lng} if o else {}

    sortie_routes = []
    for r in routes:
        arrets = list(db.scalars(select(RouteStop).where(RouteStop.route_id == r.id).order_by(RouteStop.ordre)))
        sortie_routes.append({
            "id": r.id, "vehicle_id": r.vehicle_id, "plaque": plaques.get(r.vehicle_id), "depart_min": r.depart_min, "retour_min": r.retour_min,
            "trajet_s": r.trajet_s, "distance_km": r.distance_km, "charge_kg": r.charge_kg, "charge_palettes": r.charge_palettes,
            "charge_m3": r.charge_m3, "verrouille": r.verrouille,
            "arrets": [{"id": s.id, "ordre": s.ordre, "order_id": s.order_id, "arrivee_min": s.arrivee_min, "depart_min": s.depart_min,
                        "attente_min": s.attente_min, "verrouille": s.verrouille, **cmd(commandes.get(s.order_id))} for s in arrets]})
    return {"id": plan.id, "jour": plan.jour, "statut": plan.statut, "progression": plan.progression, "message": plan.message,
            "parametres": plan.parametres, "resume": plan.resume, "created_at": plan.created_at, "routes": sortie_routes,
            "non_affectees": [{**n, **cmd(commandes.get(n["order_id"]))} for n in plan.non_affectees]}
