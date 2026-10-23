"""Recalcul d'un plan à partir d'un état (ordre des arrêts par camion) : fonctions pures, sans base de données.

Utilisé après chaque modification manuelle pour recalculer les heures d'arrivée et les alertes sans relancer
toute l'optimisation. Les durées viennent des matrices conservées avec le plan.
"""
from dataclasses import dataclass, field

from . import regulations as reg


@dataclass
class CommandeInfo:
    id: int
    reference: str
    poids_kg: int = 0
    volume_m3: float = 0
    palettes: int = 0
    debut_min: int | None = None
    fin_min: int | None = None
    service_min: int = 15
    frigo: bool = False
    adr: bool = False


@dataclass
class VehiculeInfo:
    id: int
    plaque: str
    profil: str
    capacite_kg: int | None = None
    capacite_m3: float | None = None
    palettes: int | None = None
    frigo: bool = False
    adr: bool = False


@dataclass
class Contexte:
    ouverture_min: int
    fermeture_min: int
    duree_max_min: int
    commandes: dict[int, CommandeInfo]
    vehicules: dict[int, VehiculeInfo]
    ligne: dict[int, int]  # commande_id -> ligne des matrices (0 = dépôt)
    durees: dict[str, list[list[int]]]  # profil -> secondes
    distances: dict[str, list[list[float]]]  # profil -> km
    compteurs: dict[int, "reg.Restant"] = field(default_factory=dict)  # conducteur -> temps de conduite restants au départ
    noms_conducteurs: dict[int, str] = field(default_factory=dict)
    minuit: float = 0.0  # échelle de `regulations` du minuit du jour du plan (pour comparer avec les compteurs)
    positions: dict[int, tuple[float, float]] = field(default_factory=dict)  # ligne des matrices -> (lat, lng) ; 0 = dépôt


@dataclass
class Alerte:
    type: str  # retard | surcharge | duree | fermeture | incompatible | extension | conduite_jour | conduite_semaine
    message: str
    route_vehicle_id: int
    commande_id: int | None = None
    gravite: str = "avertissement"  # « infraction » : règlement sur les temps de conduite violé


@dataclass
class ArretCalcule:
    commande_id: int
    arrivee_min: float
    depart_min: float
    attente_min: float


@dataclass
class RouteCalculee:
    vehicule_id: int
    depart_min: float
    retour_min: float
    trajet_s: int
    distance_km: float
    charge_kg: int
    charge_palettes: int
    charge_m3: float
    arrets: list[ArretCalcule] = field(default_factory=list)
    alertes: list[Alerte] = field(default_factory=list)
    pauses: list[tuple[float, float]] = field(default_factory=list)  # pauses réglementaires insérées
    conduite_min: float = 0.0  # conduite effective, hors pauses
    plafond_conduite_min: float = 540.0  # limite appliquée à cette tournée
    conducteur_id: int | None = None
    activites: list = field(default_factory=list)  # activités datées (conduite, pauses, services) : sert à relire l'état du conducteur à un instant


def hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def duree_txt(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def _parcours(ctx: Contexte, cmds: list[CommandeInfo], lignes: list[int], dur, debut: float, chrono: "reg.Chrono"):
    """Parcourt la tournée à partir de `debut` (minutes) : trajets avec pauses obligatoires, attentes de fenêtre, services."""
    p = reg.demarrer(debut, chrono)
    arrets, attentes = [], []
    for k, c in enumerate(cmds, start=1):
        reg.conduire(p, dur[lignes[k - 1]][lignes[k]] / 60)
        attente = 0.0
        if c.debut_min is not None and p.t < c.debut_min:
            attente = c.debut_min - p.t
            reg.attendre(p, attente)
        arrivee = p.t
        reg.travailler(p, c.service_min)
        arrets.append(ArretCalcule(c.id, arrivee, p.t, attente))
        attentes.append(attente)
    reg.conduire(p, dur[lignes[-1]][0] / 60)
    return p, arrets


def calculer_route(ctx: Contexte, vehicule_id: int, commande_ids: list[int], conducteur_id: int | None = None) -> RouteCalculee:
    v = ctx.vehicules[vehicule_id]
    cmds = [ctx.commandes[c] for c in commande_ids]
    restant = ctx.compteurs.get(conducteur_id) if conducteur_id is not None else None
    plafond = restant.conduite_jour if restant else reg.constantes.CONDUITE_JOUR
    if not cmds:
        return RouteCalculee(vehicule_id, ctx.ouverture_min, ctx.ouverture_min, 0, 0.0, 0, 0, 0.0, plafond_conduite_min=plafond, conducteur_id=conducteur_id)
    dur, dist = ctx.durees[v.profil], ctx.distances[v.profil]
    lignes = [0] + [ctx.ligne[c.id] for c in cmds]

    def chrono():
        if not restant:
            return reg.Chrono()
        return reg.Chrono(conduite=reg.constantes.CONDUITE_CONTINUE_MAX - restant.conduite_continue, partie1=restant.pause_necessaire < reg.constantes.PAUSE)

    debut = float(ctx.ouverture_min)
    if restant:  # repos journalier à respecter avant de reprendre
        debut = max(debut, restant.debut_possible - ctx.minuit)
    p, arrets = _parcours(ctx, cmds, lignes, dur, debut, chrono())
    if arrets[0].attente_min > 0:  # départ retardé pour supprimer l'attente avant le premier arrêt (le reste de la journée ne change pas)
        debut += arrets[0].attente_min
        p, arrets = _parcours(ctx, cmds, lignes, dur, debut, chrono())
    alertes: list[Alerte] = []
    trajet = sum(dur[lignes[k]][lignes[k + 1]] for k in range(len(lignes) - 1)) + dur[lignes[-1]][0]
    km = sum(dist[lignes[k]][lignes[k + 1]] for k in range(len(lignes) - 1)) + dist[lignes[-1]][0]
    for a, c in zip(arrets, cmds):
        if c.fin_min is not None and a.arrivee_min > c.fin_min + 1e-6:
            alertes.append(Alerte("retard", f"{c.reference} : arrivée à {hhmm(a.arrivee_min)}, fenêtre close à {hhmm(c.fin_min)} (retard de {duree_txt(a.arrivee_min - c.fin_min)})", vehicule_id, c.id))
        if (c.frigo and not v.frigo) or (c.adr and not v.adr):
            besoin = " et ".join(n for n, on in (("frigo", c.frigo and not v.frigo), ("ADR", c.adr and not v.adr)) if on)
            alertes.append(Alerte("incompatible", f"{c.reference} exige {besoin}, absent de {v.plaque}", vehicule_id, c.id))
    retour, depart = p.t, debut
    charge_kg, charge_pal, charge_m3 = sum(c.poids_kg for c in cmds), sum(c.palettes for c in cmds), sum(c.volume_m3 for c in cmds)
    for nom, charge, cap, unite in (("poids", charge_kg, v.capacite_kg, "kg"), ("palettes", charge_pal, v.palettes, "palettes"),
                                    ("volume", charge_m3, v.capacite_m3, "m³")):
        if cap is not None and charge > cap + 1e-9:
            alertes.append(Alerte("surcharge", f"{v.plaque} en surcharge ({nom}) : {round(charge, 1):g} {unite} pour {cap:g} {unite}", vehicule_id))
    if retour - depart > ctx.duree_max_min + 1e-6:
        alertes.append(Alerte("duree", f"{v.plaque} : tournée de {duree_txt(retour - depart)}, maximum {duree_txt(ctx.duree_max_min)}", vehicule_id))
    if retour > ctx.fermeture_min + 1e-6:
        alertes.append(Alerte("fermeture", f"{v.plaque} : retour au dépôt à {hhmm(retour)}, après la fermeture ({hhmm(ctx.fermeture_min)})", vehicule_id))
    # Règlement CE 561/2006 : conduite journalière et hebdomadaire (les pauses de 4 h 30 sont insérées, donc jamais en défaut ici)
    conduite = p.conduite_totale
    qui = f" de {ctx.noms_conducteurs.get(conducteur_id, 'ce conducteur')}" if restant else ""
    limite = restant.conduite_jour if restant else reg.constantes.CONDUITE_JOUR_ETENDUE  # sans conducteur : on ne sait pas si une extension reste
    if conduite > limite + 1e-6:
        alertes.append(Alerte("conduite_jour", f"{v.plaque} : {duree_txt(conduite)} de conduite, au-delà de la limite journalière{qui} ({duree_txt(limite)})", vehicule_id, gravite="infraction"))
    elif conduite > reg.constantes.CONDUITE_JOUR + 1e-6:
        reste = (restant.extensions_restantes if restant else reg.constantes.EXTENSIONS_PAR_SEMAINE)
        alertes.append(Alerte("extension", f"{v.plaque} : {duree_txt(conduite)} de conduite, soit une extension à 10 h (deux par semaine au plus ; {reste} avant celle-ci)", vehicule_id))
    if restant and conduite > restant.conduite_semaine + 1e-6:
        alertes.append(Alerte("conduite_semaine", f"{v.plaque} : dépasse le temps de conduite hebdomadaire restant{qui} ({duree_txt(restant.conduite_semaine)})", vehicule_id, gravite="infraction"))
    return RouteCalculee(vehicule_id, depart, retour, int(trajet), round(km, 1), charge_kg, charge_pal, round(charge_m3, 2), arrets, alertes,
                         pauses=list(p.pauses), conduite_min=round(conduite, 1), plafond_conduite_min=plafond, conducteur_id=conducteur_id,
                         activites=list(p.activites))


def indicateurs(routes: list[RouteCalculee], nb_non_affectees: int, capacite_totale_kg: int | None) -> dict:
    utilisees = [r for r in routes if r.arrets]
    charge = sum(r.charge_kg for r in utilisees)
    return {"km": round(sum(r.distance_km for r in utilisees), 1),
            "duree_min": round(sum(r.retour_min - r.depart_min for r in utilisees)),
            "nb_tournees": len(utilisees),
            "remplissage_pct": round(100 * charge / capacite_totale_kg) if capacite_totale_kg and utilisees else None,
            "nb_alertes": sum(len(r.alertes) for r in routes), "nb_non_affectees": nb_non_affectees,
            "nb_infractions": sum(1 for r in routes for a in r.alertes if a.gravite == "infraction")}


def chrono_a(activites: list, instant: float) -> "reg.Chrono":
    """Compteur de conduite continue d'un conducteur qui a suivi l'activité prévue jusqu'à `instant` (les activités en cours sont tronquées)."""
    ch = reg.Chrono()
    for a in activites:
        if a.debut >= instant:
            break
        ch.appliquer(reg.Activite(a.type, a.debut, min(a.fin, instant)))
    return ch


@dataclass
class Simulation:
    arrets: list[ArretCalcule]
    retour_min: float
    distance_km: float
    pauses: list[tuple[float, float]]
    retards: list[tuple[int, float]]  # (commande_id, minutes de retard sur la fenêtre)
    apres_fermeture_min: float  # retour au dépôt après la fermeture (0 si respectée)


def simuler_depuis(ctx: Contexte, vehicule_id: int, restants: list[int], depuis_ligne: int, depuis_min: float,
                   chrono: "reg.Chrono | None" = None, ajustement=None) -> Simulation:
    """Simule la fin de tournée depuis la position et l'heure réelles. `ajustement(i, j)` peut renvoyer une durée (min) observée en direct."""
    v = ctx.vehicules[vehicule_id]
    dur, dist = ctx.durees[v.profil], ctx.distances[v.profil]
    cmds = [ctx.commandes[c] for c in restants]
    p = reg.demarrer(depuis_min, chrono or reg.Chrono())
    arrets, retards, km, prec = [], [], 0.0, depuis_ligne
    for c in cmds:
        ligne = ctx.ligne[c.id]
        trajet = ajustement(prec, ligne) if ajustement else None
        reg.conduire(p, (trajet if trajet is not None else dur[prec][ligne] / 60))
        km += dist[prec][ligne]
        attente = 0.0
        if c.debut_min is not None and p.t < c.debut_min:
            attente = c.debut_min - p.t
            reg.attendre(p, attente)
        arrivee = p.t
        reg.travailler(p, c.service_min)
        arrets.append(ArretCalcule(c.id, arrivee, p.t, attente))
        if c.fin_min is not None and arrivee > c.fin_min + 1e-6:
            retards.append((c.id, arrivee - c.fin_min))
        prec = ligne
    if cmds:
        trajet = ajustement(prec, 0) if ajustement else None
        reg.conduire(p, trajet if trajet is not None else dur[prec][0] / 60)
        km += dist[prec][0]
    return Simulation(arrets, p.t, round(km, 1), list(p.pauses), retards, max(0.0, p.t - ctx.fermeture_min) if cmds else 0.0)
