"""Recalcul d'un plan à partir d'un état (ordre des arrêts par camion) : fonctions pures, sans base de données.

Utilisé après chaque modification manuelle pour recalculer les heures d'arrivée et les alertes sans relancer
toute l'optimisation. Les durées viennent des matrices conservées avec le plan.
"""
from dataclasses import dataclass, field


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


@dataclass
class Alerte:
    type: str  # retard | surcharge | duree | fermeture | incompatible
    message: str
    route_vehicle_id: int
    commande_id: int | None = None


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


def hhmm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def duree_txt(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def calculer_route(ctx: Contexte, vehicule_id: int, commande_ids: list[int]) -> RouteCalculee:
    v = ctx.vehicules[vehicule_id]
    cmds = [ctx.commandes[c] for c in commande_ids]
    if not cmds:
        return RouteCalculee(vehicule_id, ctx.ouverture_min, ctx.ouverture_min, 0, 0.0, 0, 0, 0.0)
    dur, dist = ctx.durees[v.profil], ctx.distances[v.profil]
    lignes = [0] + [ctx.ligne[c.id] for c in cmds]
    # Parcours au plus tôt, puis départ retardé pour supprimer l'attente avant le premier arrêt.
    t = ctx.ouverture_min * 60.0
    arrivees = []
    for k, c in enumerate(cmds, start=1):
        arrivee = t + dur[lignes[k - 1]][lignes[k]]
        if c.debut_min is not None:
            arrivee = max(arrivee, c.debut_min * 60)
        arrivees.append(arrivee)
        t = arrivee + c.service_min * 60
    depart_s = max(ctx.ouverture_min * 60, arrivees[0] - dur[0][lignes[1]])
    t, arrets, trajet, km = depart_s, [], 0, 0.0
    alertes: list[Alerte] = []
    for k, c in enumerate(cmds, start=1):
        trajet += dur[lignes[k - 1]][lignes[k]]
        km += dist[lignes[k - 1]][lignes[k]]
        arrivee = t + dur[lignes[k - 1]][lignes[k]]
        attente = 0.0
        if c.debut_min is not None and arrivee < c.debut_min * 60:
            attente, arrivee = c.debut_min * 60 - arrivee, c.debut_min * 60
        arrets.append(ArretCalcule(c.id, arrivee / 60, (arrivee + c.service_min * 60) / 60, attente / 60))
        if c.fin_min is not None and arrivee / 60 > c.fin_min + 1e-6:
            alertes.append(Alerte("retard", f"{c.reference} : arrivée à {hhmm(arrivee / 60)}, fenêtre close à {hhmm(c.fin_min)} (retard de {duree_txt(arrivee / 60 - c.fin_min)})", vehicule_id, c.id))
        if (c.frigo and not v.frigo) or (c.adr and not v.adr):
            besoin = " et ".join(n for n, on in (("frigo", c.frigo and not v.frigo), ("ADR", c.adr and not v.adr)) if on)
            alertes.append(Alerte("incompatible", f"{c.reference} exige {besoin}, absent de {v.plaque}", vehicule_id, c.id))
        t = arrivee + c.service_min * 60
    trajet += dur[lignes[-1]][0]
    km += dist[lignes[-1]][0]
    retour = (t + dur[lignes[-1]][0]) / 60
    depart = depart_s / 60
    charge_kg, charge_pal, charge_m3 = sum(c.poids_kg for c in cmds), sum(c.palettes for c in cmds), sum(c.volume_m3 for c in cmds)
    for nom, charge, cap, unite in (("poids", charge_kg, v.capacite_kg, "kg"), ("palettes", charge_pal, v.palettes, "palettes"),
                                    ("volume", charge_m3, v.capacite_m3, "m³")):
        if cap is not None and charge > cap + 1e-9:
            alertes.append(Alerte("surcharge", f"{v.plaque} en surcharge ({nom}) : {round(charge, 1):g} {unite} pour {cap:g} {unite}", vehicule_id))
    if retour - depart > ctx.duree_max_min + 1e-6:
        alertes.append(Alerte("duree", f"{v.plaque} : tournée de {duree_txt(retour - depart)}, maximum {duree_txt(ctx.duree_max_min)}", vehicule_id))
    if retour > ctx.fermeture_min + 1e-6:
        alertes.append(Alerte("fermeture", f"{v.plaque} : retour au dépôt à {hhmm(retour)}, après la fermeture ({hhmm(ctx.fermeture_min)})", vehicule_id))
    return RouteCalculee(vehicule_id, depart, retour, int(trajet), round(km, 1), charge_kg, charge_pal, round(charge_m3, 2), arrets, alertes)


def indicateurs(routes: list[RouteCalculee], nb_non_affectees: int, capacite_totale_kg: int | None) -> dict:
    utilisees = [r for r in routes if r.arrets]
    charge = sum(r.charge_kg for r in utilisees)
    return {"km": round(sum(r.distance_km for r in utilisees), 1),
            "duree_min": round(sum(r.retour_min - r.depart_min for r in utilisees)),
            "nb_tournees": len(utilisees),
            "remplissage_pct": round(100 * charge / capacite_totale_kg) if capacite_totale_kg and utilisees else None,
            "nb_alertes": sum(len(r.alertes) for r in routes), "nb_non_affectees": nb_non_affectees}
