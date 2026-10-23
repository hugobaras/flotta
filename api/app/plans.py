"""Construction, calcul, modification et lecture des plans de tournées."""
import logging

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import conduite, matrices, optimisation as opt, planning, routage
from . import regulations as reg
from .models import Depot, Driver, Order, Plan, PlanSnapshot, Route, RouteStop, Vehicle

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
    """Plan non calculable : le message est montré tel quel à l'utilisateur."""


class ModificationRefusee(Exception):
    """Modification manuelle refusée (verrou, élément inconnu...)."""

    def __init__(self, message: str, statut: int = 409):
        super().__init__(message)
        self.statut = statut


# ---------------------------------------------------------------- calcul initial et réoptimisation


def executer(db: Session, plan_id: int) -> Plan:
    """Calcule le plan. Toute erreur est consignée dans le plan, jamais perdue."""
    plan = db.get(Plan, plan_id)
    if not plan or plan.statut in ("termine", "en_cours"):
        return plan
    reopt = bool(plan.parametres.get("reoptimiser"))
    try:
        _reoptimiser(db, plan) if reopt else _executer(db, plan)
    except PlanImpossible as e:
        _echec(db, plan_id, str(e), reopt)
    except routage.RouteurIndisponible:
        _echec(db, plan_id, "Le service de routage poids lourd est indisponible : le plan n'a pas pu être calculé (aucune estimation inventée). Réessayez plus tard.", reopt)
    except Exception:  # noqa: BLE001 : on garde la trace dans le plan
        log.exception("Plan %s : erreur inattendue", plan_id)
        _echec(db, plan_id, "Erreur inattendue pendant le calcul. L'équipe technique peut la retrouver dans les journaux.", reopt)
    return db.get(Plan, plan_id)


def _echec(db: Session, plan_id: int, message: str, reopt: bool):
    db.rollback()
    plan = db.get(Plan, plan_id)
    plan.message, plan.progression = message, 100
    plan.statut = "termine" if reopt else "echec"  # une réoptimisation ratée laisse le plan précédent intact
    plan.parametres = {k: v for k, v in plan.parametres.items() if k != "reoptimiser"}
    db.commit()


def _depot(db: Session, plan: Plan) -> Depot:
    p = plan.parametres
    depot = (db.get(Depot, p["depot_id"]) if p.get("depot_id")
             else db.scalar(select(Depot).where(Depot.company_id == plan.company_id, Depot.par_defaut.is_(True))))
    if not depot or depot.company_id != plan.company_id or depot.lat is None:
        raise PlanImpossible("Aucun dépôt localisé : ajoutez un dépôt avec une adresse trouvée avant de planifier.")
    return depot


def _executer(db: Session, plan: Plan):
    p = plan.parametres
    _progres(db, plan, 5, "Préparation des données")
    depot = _depot(db, plan)
    non_affectees, commandes = [], []
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

    ouverture = _minutes(depot.ouverture)
    affectes = _affectations(db, plan, vehicules)
    compt = {d: conduite.compteurs(db, d, plan.jour, ouverture) for d in set(affectes.values())}
    minuit = conduite.minuit(plan.jour)

    _progres(db, plan, 15, "Calcul des temps de trajet")
    locations = [(depot.lat, depot.lng)] + [(o.lat, o.lng) for o in commandes]
    profils = {_cle_profil(v): routage.options_camion(v) for v in vehicules}
    mats = matrices.fournisseur(locations, profils)
    plan.matrices = {"commandes": [0] + [o.id for o in commandes],
                     "profils": {k: {"vehicle_ids": [v.id for v in vehicules if _cle_profil(v) == k], **m} for k, m in mats.items()}}

    _progres(db, plan, 40, "Optimisation des tournées")
    solution = opt.optimiser(opt.Probleme(
        vehicules=[_veh_opt(v, compt.get(affectes.get(v.id)), minuit) for v in vehicules],
        commandes=[_cmd_opt(o) for o in commandes], matrices={k: m["durations"] for k, m in mats.items()},
        ouverture_min=_minutes(depot.ouverture), fermeture_min=_minutes(depot.fermeture),
        duree_max_min=p.get("duree_max_min", 600), temps_calcul_s=p.get("temps_max_s", 10),
        rotations_max=p.get("rotations_max", 1), rechargement_min=p.get("rechargement_min", 45)))

    _progres(db, plan, 90, "Enregistrement du plan")
    par_vehicule = {r.vehicule_id: r for r in solution.routes}
    etat = {"routes": [{"vehicle_id": v.id, "verrouille": False, "conducteur_id": affectes.get(v.id),
                        "arrets": [{"order_id": a.commande_id, "verrouille": False, "rotation": a.rotation} for a in par_vehicule[v.id].arrets] if v.id in par_vehicule else []}
                       for v in vehicules],
            "non_affectees": non_affectees + [{"order_id": c, "raison": r} for c, r in solution.non_affectees]}
    plan.resume = {"vehicules_exclus": exclus}
    db.execute(delete(PlanSnapshot).where(PlanSnapshot.plan_id == plan.id))
    plan.curseur = -1
    pousser(db, plan, etat, "Plan optimisé")
    plan.statut, plan.progression, plan.message = "termine", 100, None
    archiver_anciens(db, plan)
    db.commit()


def archiver_anciens(db: Session, plan: Plan):
    """Un calcul réussi remplace les calculs précédents du même jour : ils sont archivés (rangés, pas supprimés).
    Sont protégés : les plans publiés aux chauffeurs et les versions enregistrées sous un nom."""
    db.execute(update(Plan).where(Plan.company_id == plan.company_id, Plan.jour == plan.jour, Plan.id != plan.id, Plan.statut == "termine",
                                  Plan.publie_le.is_(None), Plan.nom.is_(None), Plan.archive_le.is_(None)).values(archive_le=datetime.now(timezone.utc)))


def _affectations(db: Session, plan: Plan, vehicules: list[Vehicle]) -> dict[int, int]:
    """Conducteur de chaque véhicule : choix explicite du plan, sinon conducteur actif dont c'est le véhicule habituel."""
    explicites = {int(k): v for k, v in (plan.parametres.get("affectations") or {}).items() if v}
    habituels: dict[int, int] = {}
    for d in db.scalars(select(Driver).where(Driver.company_id == plan.company_id, Driver.actif.is_(True)).order_by(Driver.id)):
        if d.vehicule_habituel_id and d.vehicule_habituel_id not in habituels and d.id not in explicites.values():
            habituels[d.vehicule_habituel_id] = d.id
    res = {}
    for v in vehicules:
        d = explicites.get(v.id) or habituels.get(v.id)
        if d and d not in res.values():
            res[v.id] = d
    return res


def _veh_opt(v: Vehicle, restant: "reg.Restant | None", minuit: float) -> opt.VehiculeOpt:
    """Véhicule pour l'optimiseur : plafond de conduite et heure de départ au plus tôt issus du conducteur affecté."""
    o = opt.VehiculeOpt(v.id, _cle_profil(v), v.capacite_kg, v.capacite_m3, v.palettes, v.frigo, v.adr)
    if restant:
        o.conduite_max_min = max(0.0, min(restant.conduite_jour_normale, restant.conduite_semaine))
        o.debut_min = max(0, int(restant.debut_possible - minuit + 0.999))
    return o


def _cmd_opt(o: Order, impose: int | None = None) -> opt.CommandeOpt:
    return opt.CommandeOpt(o.id, o.poids_kg, o.volume_m3, o.palettes, _minutes(o.fenetre_debut), _minutes(o.fenetre_fin),
                           o.duree_service_min, o.frigo, o.adr, impose)


def _reoptimiser(db: Session, plan: Plan):
    """Réoptimise sans toucher aux tournées verrouillées ; les arrêts verrouillés restent sur leur camion."""
    p = plan.parametres
    _progres(db, plan, 20, "Préparation de la réoptimisation")
    etat, ctx = charger_etat(db, plan), contexte(db, plan)
    libres = [r for r in etat["routes"] if not r["verrouille"]]
    fixes = [r for r in etat["routes"] if r["verrouille"]]
    if not libres:
        raise PlanImpossible("Toutes les tournées sont verrouillées : rien à réoptimiser.")
    impose = {a["order_id"]: r["vehicle_id"] for r in libres for a in r["arrets"] if a["verrouille"]}
    ids = [a["order_id"] for r in libres for a in r["arrets"]] + [n["order_id"] for n in etat["non_affectees"] if n["order_id"] in ctx.ligne]
    gardees = [n for n in etat["non_affectees"] if n["order_id"] not in ctx.ligne]
    commandes = {o.id: o for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(ids)))}
    rows = [0] + [ctx.ligne[i] for i in ids]
    vehicules = [ctx.vehicules[r["vehicle_id"]] for r in libres]
    conducteurs = {r["vehicle_id"]: r.get("conducteur_id") for r in libres}
    profils = sorted({v.profil for v in vehicules})
    _progres(db, plan, 40, "Optimisation des tournées")
    solution = opt.optimiser(opt.Probleme(
        vehicules=[_veh_opt_ctx(v, ctx, conducteurs.get(v.id)) for v in vehicules],
        commandes=[_cmd_opt(commandes[i], impose.get(i)) for i in ids],
        matrices={k: [[ctx.durees[k][a][b] for b in rows] for a in rows] for k in profils},
        ouverture_min=ctx.ouverture_min, fermeture_min=ctx.fermeture_min, duree_max_min=ctx.duree_max_min,
        temps_calcul_s=p.get("temps_max_s", 10), rotations_max=p.get("rotations_max", 1), rechargement_min=p.get("rechargement_min", 45)))
    _progres(db, plan, 90, "Enregistrement du plan")
    par_vehicule = {r.vehicule_id: r for r in solution.routes}
    nouvelles = {r["vehicle_id"]: {"vehicle_id": r["vehicle_id"], "verrouille": False, "conducteur_id": r.get("conducteur_id"),
                                   "arrets": [{"order_id": a.commande_id, "verrouille": impose.get(a.commande_id) == r["vehicle_id"], "rotation": a.rotation}
                                              for a in par_vehicule[r["vehicle_id"]].arrets] if r["vehicle_id"] in par_vehicule else []}
                 for r in libres}
    etat_nouveau = {"routes": [r if r["verrouille"] else nouvelles[r["vehicle_id"]] for r in etat["routes"]],
                    "non_affectees": gardees + [{"order_id": c, "raison": raison} for c, raison in solution.non_affectees]}
    plan.parametres = {k: v for k, v in p.items() if k != "reoptimiser"}
    pousser(db, plan, etat_nouveau, "Réoptimisation")
    plan.statut, plan.progression, plan.message = "termine", 100, None
    db.commit()


def _veh_opt_ctx(v: planning.VehiculeInfo, ctx: planning.Contexte, conducteur_id: int | None) -> opt.VehiculeOpt:
    o = opt.VehiculeOpt(v.id, v.profil, v.capacite_kg, v.capacite_m3, v.palettes, v.frigo, v.adr)
    restant = ctx.compteurs.get(conducteur_id) if conducteur_id else None
    if restant:
        o.conduite_max_min = max(0.0, min(restant.conduite_jour_normale, restant.conduite_semaine))
        o.debut_min = max(0, int(restant.debut_possible - ctx.minuit + 0.999))
    return o


# ---------------------------------------------------------------- état, historique, recalcul


def contexte(db: Session, plan: Plan, matrices_: dict | None = None) -> planning.Contexte:
    depot = _depot(db, plan)
    m = matrices_ if matrices_ is not None else (plan.matrices or {})
    ligne = {oid: i for i, oid in enumerate(m.get("commandes", [])) if i > 0}
    vehicules: dict[int, planning.VehiculeInfo] = {}
    for cle, prof in m.get("profils", {}).items():
        for vid in prof["vehicle_ids"]:
            v = db.get(Vehicle, vid)
            vehicules[vid] = planning.VehiculeInfo(v.id, v.plaque, cle, v.capacite_kg, v.capacite_m3, v.palettes, v.frigo, v.adr)
    commandes = {o.id: planning.CommandeInfo(o.id, o.reference, o.poids_kg, o.volume_m3, o.palettes, _minutes(o.fenetre_debut),
                                             _minutes(o.fenetre_fin), o.duree_service_min, o.frigo, o.adr)
                 for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(list(ligne))))} if ligne else {}
    ouverture = _minutes(depot.ouverture)
    positions = {o.id: o for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(list(ligne))))} if ligne else {}
    pilotes = list(db.scalars(select(Driver).where(Driver.company_id == plan.company_id, Driver.actif.is_(True)).order_by(Driver.nom)))
    return planning.Contexte(ouverture, _minutes(depot.fermeture), plan.parametres.get("duree_max_min", 600), commandes, vehicules,
                             ligne, {k: p["durations"] for k, p in m.get("profils", {}).items()},
                             {k: p["distances"] for k, p in m.get("profils", {}).items()},
                             compteurs={d.id: conduite.compteurs(db, d.id, plan.jour, ouverture) for d in pilotes},
                             noms_conducteurs={d.id: d.nom for d in pilotes}, minuit=conduite.minuit(plan.jour),
                             rechargement_min=plan.parametres.get("rechargement_min", 45),
                             positions={0: (depot.lat, depot.lng), **{ligne[o]: (c.lat, c.lng) for o, c in positions.items() if o in ligne}})


def charger_etat(db: Session, plan: Plan) -> dict:
    routes = []
    for r in db.scalars(select(Route).where(Route.plan_id == plan.id).order_by(Route.id)):
        arrets = db.scalars(select(RouteStop).where(RouteStop.route_id == r.id).order_by(RouteStop.ordre))
        routes.append({"vehicle_id": r.vehicle_id, "verrouille": r.verrouille, "conducteur_id": r.conducteur_id,
                       "arrets": [{"order_id": s.order_id, "verrouille": s.verrouille, "rotation": s.rotation} for s in arrets]})
    return {"routes": routes, "non_affectees": list(plan.non_affectees)}


def _calculer(ctx: planning.Contexte, etat: dict) -> list[planning.RouteCalculee]:
    return [planning.calculer_route(ctx, r["vehicle_id"], [a["order_id"] for a in r["arrets"]], r.get("conducteur_id"),
                                    [a.get("rotation", 1) for a in r["arrets"]]) for r in etat["routes"]]


def _capacite_totale(ctx: planning.Contexte, etat: dict) -> int | None:
    caps = [ctx.vehicules[r["vehicle_id"]].capacite_kg for r in etat["routes"]]
    if not all(caps):
        return None
    # Un camion qui fait deux rotations peut porter deux fois sa capacité dans la journée.
    return sum(c * max(1, len({a.get("rotation", 1) for a in r["arrets"]})) for c, r in zip(caps, etat["routes"]))


def ecrire_etat(db: Session, plan: Plan, etat: dict):
    """Réécrit tournées et arrêts depuis l'état, avec heures et indicateurs recalculés."""
    ctx = contexte(db, plan)
    calculees = _calculer(ctx, etat)
    anciens = list(db.scalars(select(Route.id).where(Route.plan_id == plan.id)))
    if anciens:
        db.execute(delete(RouteStop).where(RouteStop.route_id.in_(anciens)))
        db.execute(delete(Route).where(Route.id.in_(anciens)))
    db.flush()
    en_route: set[int] = set()
    for r, c in zip(etat["routes"], calculees):
        route = Route(company_id=plan.company_id, plan_id=plan.id, vehicle_id=r["vehicle_id"], depart_min=c.depart_min, retour_min=c.retour_min,
                      trajet_s=c.trajet_s, distance_km=c.distance_km, charge_kg=c.charge_kg, charge_palettes=c.charge_palettes,
                      charge_m3=c.charge_m3, verrouille=r["verrouille"], conducteur_id=r.get("conducteur_id"),
                      conduite_min=c.conduite_min, pauses=[[a, b] for a, b in c.pauses])
        db.add(route)
        db.flush()
        for n, (a, calc) in enumerate(zip(r["arrets"], c.arrets), start=1):
            db.add(RouteStop(company_id=plan.company_id, route_id=route.id, ordre=n, order_id=a["order_id"], arrivee_min=calc.arrivee_min,
                             depart_min=calc.depart_min, attente_min=calc.attente_min, verrouille=a["verrouille"], rotation=calc.rotation))
            en_route.add(a["order_id"])
    plan.non_affectees = etat["non_affectees"]
    tous = en_route | {n["order_id"] for n in etat["non_affectees"]}
    for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(tous))):
        if o.statut not in ("livre", "echec"):  # une livraison déjà constatée ne revient jamais en arrière
            o.statut = "planifie" if o.id in en_route else "a_planifier"
    resume = dict(plan.resume or {})
    resume.update(planning.indicateurs(calculees, len(etat["non_affectees"]), _capacite_totale(ctx, etat)))
    resume["nb_commandes"] = len(tous)
    plan.resume = resume


def pousser(db: Session, plan: Plan, etat: dict, libelle: str):
    """Enregistre un nouvel état dans l'historique (en effaçant ce qui pouvait être rétabli) puis l'applique."""
    if plan.curseur >= 0 and not _snapshot(db, plan, plan.curseur):
        db.add(PlanSnapshot(plan_id=plan.id, seq=plan.curseur, libelle="Plan optimisé", etat=charger_etat(db, plan)))  # plan antérieur à l'historique
        db.flush()
    db.execute(delete(PlanSnapshot).where(PlanSnapshot.plan_id == plan.id, PlanSnapshot.seq > plan.curseur))
    plan.curseur += 1
    db.add(PlanSnapshot(plan_id=plan.id, seq=plan.curseur, libelle=libelle, etat=etat))
    ecrire_etat(db, plan, etat)
    db.flush()


def _snapshot(db: Session, plan: Plan, seq: int) -> PlanSnapshot | None:
    return db.scalar(select(PlanSnapshot).where(PlanSnapshot.plan_id == plan.id, PlanSnapshot.seq == seq))


def historique(db: Session, plan: Plan) -> tuple[bool, bool]:
    return (plan.curseur > 0, _snapshot(db, plan, plan.curseur + 1) is not None)


def annuler(db: Session, plan: Plan):
    prec = _snapshot(db, plan, plan.curseur - 1)
    if plan.curseur <= 0 or not prec:
        raise ModificationRefusee("Rien à annuler")
    plan.curseur -= 1
    ecrire_etat(db, plan, prec.etat)


def retablir(db: Session, plan: Plan):
    suiv = _snapshot(db, plan, plan.curseur + 1)
    if not suiv:
        raise ModificationRefusee("Rien à rétablir")
    plan.curseur += 1
    ecrire_etat(db, plan, suiv.etat)


def _copie(etat: dict) -> dict:
    return {"routes": [{**r, "arrets": [dict(a) for a in r["arrets"]]} for r in etat["routes"]], "non_affectees": [dict(n) for n in etat["non_affectees"]]}


def _renumeroter(route: dict):
    """Après une modification : rotations croissantes et sans trou (une rotation vidée disparaît)."""
    nums = planning.normaliser_rotations([a.get("rotation", 1) for a in route["arrets"]], len(route["arrets"]))
    for a, n in zip(route["arrets"], nums):
        a["rotation"] = n


def deplacer_etat(etat: dict, order_id: int, vehicle_id: int | None, position: int | None, rotation: int | None = None) -> dict:
    """Déplace un arrêt dans un état (copie modifiée) : vers un camion à une position, ou hors du plan.
    Sans `rotation`, l'arrêt prend celle de son voisin ; avec `rotation`, il rejoint cette rotation (position dans la rotation, fin par défaut),
    et un numéro supérieur au dernier en ouvre une nouvelle."""
    etat = _copie(etat)
    source = next((r for r in etat["routes"] if any(a["order_id"] == order_id for a in r["arrets"])), None)
    non_aff = next((n for n in etat["non_affectees"] if n["order_id"] == order_id), None)
    if not source and not non_aff:
        raise ModificationRefusee("Commande absente de ce plan", 404)
    cible = None
    if vehicle_id is not None:
        cible = next((r for r in etat["routes"] if r["vehicle_id"] == vehicle_id), None)
        if not cible:
            raise ModificationRefusee("Véhicule absent de ce plan", 404)
    if source:
        arret = next(a for a in source["arrets"] if a["order_id"] == order_id)
        if source["verrouille"] or arret["verrouille"]:
            raise ModificationRefusee("Cet arrêt ou sa tournée est verrouillé : déverrouillez-le d'abord")
    if cible and cible["verrouille"]:
        raise ModificationRefusee("La tournée de destination est verrouillée : déverrouillez-la d'abord")
    if source:
        source["arrets"] = [a for a in source["arrets"] if a["order_id"] != order_id]
    else:
        etat["non_affectees"] = [n for n in etat["non_affectees"] if n["order_id"] != order_id]
    arret = {"order_id": order_id, "verrouille": False}
    if cible is None:
        etat["non_affectees"].append({"order_id": order_id, "raison": "Retirée du plan à la main"})
    else:
        _renumeroter(cible)
        arrets = cible["arrets"]
        if rotation is not None:
            derniere = max((a["rotation"] for a in arrets), default=1)
            rotation = min(rotation, derniere + 1)  # on n'ouvre qu'une rotation à la fois, à la suite des autres
            dans = [i for i, a in enumerate(arrets) if a["rotation"] == rotation]
            debut = dans[0] if dans else len(arrets)
            pos = debut + (len(dans) if position is None else max(0, min(position, len(dans))))
            arret["rotation"] = rotation
        else:
            pos = len(arrets) if position is None else max(0, min(position, len(arrets)))
            voisin = arrets[pos - 1] if pos else (arrets[0] if arrets else None)
            arret["rotation"] = voisin["rotation"] if voisin else 1
        arrets.insert(pos, arret)
        _renumeroter(cible)
    if source:
        _renumeroter(source)  # une rotation vidée disparaît
    return etat


def deplacer(db: Session, plan: Plan, order_id: int, vehicle_id: int | None, position: int | None, rotation: int | None = None):
    """Déplace un arrêt vers un autre camion (ou dans le même) à la position donnée, ou le rend non affecté."""
    etat = deplacer_etat(charger_etat(db, plan), order_id, vehicle_id, position, rotation)
    maxi = plan.parametres.get("rotations_max", 3)
    if any(a["rotation"] > maxi for r in etat["routes"] for a in r["arrets"]):
        raise ModificationRefusee(f"Ce plan autorise {maxi} rotation{'s' if maxi > 1 else ''} au plus par camion")
    pousser(db, plan, etat, "Déplacement d'un arrêt")


def verrouiller(db: Session, plan: Plan, vehicle_id: int | None, order_id: int | None, verrouille: bool):
    etat = _copie(charger_etat(db, plan))
    if order_id is not None:
        trouve = next((a for r in etat["routes"] for a in r["arrets"] if a["order_id"] == order_id), None)
        if not trouve:
            raise ModificationRefusee("Arrêt absent de ce plan", 404)
        trouve["verrouille"] = verrouille
    elif vehicle_id is not None:
        route = next((r for r in etat["routes"] if r["vehicle_id"] == vehicle_id), None)
        if not route:
            raise ModificationRefusee("Véhicule absent de ce plan", 404)
        route["verrouille"] = verrouille
    else:
        raise ModificationRefusee("Indiquez un arrêt ou un véhicule", 422)
    pousser(db, plan, etat, "Verrouillage" if verrouille else "Déverrouillage")


def affecter(db: Session, plan: Plan, vehicle_id: int, conducteur_id: int | None):
    etat = _copie(charger_etat(db, plan))
    route = next((r for r in etat["routes"] if r["vehicle_id"] == vehicle_id), None)
    if not route:
        raise ModificationRefusee("Véhicule absent de ce plan", 404)
    if route["verrouille"]:
        raise ModificationRefusee("Cette tournée est verrouillée : déverrouillez-la d'abord")
    if conducteur_id is not None:
        d = db.get(Driver, conducteur_id)
        if not d or d.company_id != plan.company_id or not d.actif:
            raise ModificationRefusee("Conducteur inconnu ou inactif", 404)
        autre = next((r for r in etat["routes"] if r.get("conducteur_id") == conducteur_id and r["vehicle_id"] != vehicle_id), None)
        if autre:
            raise ModificationRefusee("Ce conducteur est déjà affecté à une autre tournée de ce plan")
    route["conducteur_id"] = conducteur_id
    pousser(db, plan, etat, "Affectation d'un conducteur")


def creer_version(db: Session, plan: Plan, nom: str) -> Plan:
    copie = Plan(company_id=plan.company_id, jour=plan.jour, statut="termine", progression=100, parametres=dict(plan.parametres), resume=dict(plan.resume or {}),
                 non_affectees=list(plan.non_affectees), matrices=plan.matrices, nom=nom.strip(), parent_id=plan.id, curseur=-1)
    db.add(copie)
    db.flush()
    pousser(db, copie, charger_etat(db, plan), f"Version « {nom.strip()} »")
    return copie


def lancer_reoptimisation(db: Session, plan: Plan):
    if plan.statut != "termine":
        raise ModificationRefusee("Le plan n'est pas terminé")
    plan.statut, plan.progression, plan.message = "en_attente", 0, None
    plan.parametres = {**plan.parametres, "reoptimiser": True}
    db.commit()


# ---------------------------------------------------------------- lecture


def detail(db: Session, plan: Plan) -> dict:
    routes = list(db.scalars(select(Route).where(Route.plan_id == plan.id).order_by(Route.id)))
    plaques = {v.id: v.plaque for v in db.scalars(select(Vehicle).where(Vehicle.company_id == plan.company_id))}
    ids = {s.order_id for r in routes for s in db.scalars(select(RouteStop).where(RouteStop.route_id == r.id))} | {n["order_id"] for n in plan.non_affectees}
    commandes = {o.id: o for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(ids)))} if ids else {}

    def cmd(o: Order | None):
        return {"reference": o.reference, "client": o.client, "adresse": o.adresse, "lat": o.lat, "lng": o.lng, "poids_kg": o.poids_kg,
                "palettes": o.palettes, "fenetre_debut": o.fenetre_debut, "fenetre_fin": o.fenetre_fin, "duree_service_min": o.duree_service_min} if o else {}

    from . import livraisons
    suivi = livraisons.derniers_evenements(db, plan.id) if plan.publie_le else {}
    sortie_routes = []
    for r in routes:
        arrets = list(db.scalars(select(RouteStop).where(RouteStop.route_id == r.id).order_by(RouteStop.ordre)))
        sortie_routes.append({
            "id": r.id, "vehicle_id": r.vehicle_id, "plaque": plaques.get(r.vehicle_id), "depart_min": r.depart_min, "retour_min": r.retour_min,
            "trajet_s": r.trajet_s, "distance_km": r.distance_km, "charge_kg": r.charge_kg, "charge_palettes": r.charge_palettes,
            "charge_m3": r.charge_m3, "verrouille": r.verrouille, "conducteur_id": r.conducteur_id, "conduite_min": r.conduite_min,
            "pauses": r.pauses or [],
            "arrets": [{"id": s.id, "ordre": s.ordre, "order_id": s.order_id, "arrivee_min": s.arrivee_min, "depart_min": s.depart_min,
                        "attente_min": s.attente_min, "verrouille": s.verrouille, "rotation": s.rotation, **cmd(commandes.get(s.order_id)),
                        "livraison": suivi.get(s.order_id),
                        "retard_min": livraisons.retard_min(s.arrivee_min, (suivi.get(s.order_id) or {}).get("statut"), plan.jour) if plan.publie_le else None}
                       for s in arrets]})
    out = {"id": plan.id, "jour": plan.jour, "statut": plan.statut, "progression": plan.progression, "message": plan.message, "nom": plan.nom,
           "parametres": plan.parametres, "resume": plan.resume, "created_at": plan.created_at, "routes": sortie_routes,
           "non_affectees": [{**n, **cmd(commandes.get(n["order_id"]))} for n in plan.non_affectees],
           "publie_le": plan.publie_le, "avancement": None,
           "alertes": [], "reference": None, "peut_annuler": False, "peut_retablir": False, "versions": [], "conducteurs": []}
    if plan.statut == "termine" and plan.matrices:
        ctx = contexte(db, plan)
        etat = charger_etat(db, plan)
        calculees = _calculer(ctx, etat)
        par_vehicule = {c.vehicule_id: c for c in calculees}
        out["alertes"] = [a.__dict__ for r in calculees for a in r.alertes]
        origine = _snapshot(db, plan, 0)
        if origine:
            ref = planning.indicateurs(_calculer(ctx, origine.etat), len(origine.etat["non_affectees"]), _capacite_totale(ctx, origine.etat))
            out["reference"] = ref
        out["peut_annuler"], out["peut_retablir"] = historique(db, plan)
        affectes = {r["conducteur_id"]: r["vehicle_id"] for r in etat["routes"] if r.get("conducteur_id")}
        out["conducteurs"] = [{"id": d, "nom": ctx.noms_conducteurs[d], "vehicle_id": affectes.get(d),
                               "conduite_jour_min": round(x.conduite_jour), "conduite_jour_normale_min": round(x.conduite_jour_normale),
                               "conduite_semaine_min": round(x.conduite_semaine), "extensions_restantes": x.extensions_restantes,
                               "debut_possible_min": round(max(0, x.debut_possible - ctx.minuit))} for d, x in ctx.compteurs.items()]
        for r in out["routes"]:
            c = par_vehicule.get(r["vehicle_id"])
            r["plafond_conduite_min"] = c.plafond_conduite_min if c else None
            r["conduite_restante_min"] = round(c.plafond_conduite_min - c.conduite_min) if c else None
            r["rotations"] = [x.__dict__ for x in c.rotations] if c else []
    if plan.publie_le:
        arrets = [a for r in out["routes"] for a in r["arrets"]]
        statut = lambda a: (a["livraison"] or {}).get("statut")  # noqa: E731
        out["avancement"] = {"total": len(arrets), "livrees": sum(1 for a in arrets if statut(a) == "livre"),
                             "impossibles": sum(1 for a in arrets if statut(a) == "impossible"),
                             "sur_place": sum(1 for a in arrets if statut(a) == "arrive"),
                             "en_retard": sum(1 for a in arrets if a["retard_min"])}
    autres = db.scalars(select(Plan).where(Plan.company_id == plan.company_id, Plan.jour == plan.jour, Plan.statut == "termine").order_by(Plan.id))
    out["versions"] = [{"id": p.id, "nom": p.nom, "created_at": p.created_at, "archive": p.archive_le is not None, "publie": p.publie_le is not None} for p in autres]
    out["archive"] = plan.archive_le is not None
    return out
