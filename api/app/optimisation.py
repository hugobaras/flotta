"""Optimisation de tournées (OR-Tools) : fonctions pures, sans base de données ni appel réseau.

Les durées sont en secondes, les heures en minutes depuis minuit. L'indice 0 des matrices est le dépôt, l'indice i
correspond à la commande i - 1 de `Probleme.commandes`.
"""
from dataclasses import dataclass, field

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

INJOIGNABLE_S = 3 * 86400  # durée donnée par le service de routage aux trajets sans chemin
PENALITE_NON_AFFECTEE = 10_000_000


@dataclass
class VehiculeOpt:
    id: int
    profil: str  # clé de la matrice de ce véhicule (véhicules de même gabarit = même matrice)
    capacite_kg: int | None = None
    capacite_m3: float | None = None
    palettes: int | None = None
    frigo: bool = False
    adr: bool = False


@dataclass
class CommandeOpt:
    id: int
    poids_kg: int = 0
    volume_m3: float = 0
    palettes: int = 0
    debut_min: int | None = None
    fin_min: int | None = None
    service_min: int = 15
    frigo: bool = False
    adr: bool = False


@dataclass
class Probleme:
    vehicules: list[VehiculeOpt]
    commandes: list[CommandeOpt]
    matrices: dict[str, list[list[int]]]  # profil -> matrice des durées en secondes
    ouverture_min: int = 6 * 60
    fermeture_min: int = 19 * 60
    duree_max_min: int = 10 * 60
    temps_calcul_s: int = 10


@dataclass
class ArretOpt:
    commande_id: int
    arrivee_min: float
    depart_min: float
    attente_min: float


@dataclass
class RouteOpt:
    vehicule_id: int
    depart_min: float
    retour_min: float
    trajet_s: int
    arrets: list[ArretOpt] = field(default_factory=list)


@dataclass
class Solution:
    routes: list[RouteOpt]
    non_affectees: list[tuple[int, str]]  # (commande_id, raison probable)


def _compatibles(c: CommandeOpt, vehicules: list[VehiculeOpt]) -> list[VehiculeOpt]:
    return [v for v in vehicules if (not c.frigo or v.frigo) and (not c.adr or v.adr)]


def _tient(c: CommandeOpt, v: VehiculeOpt) -> bool:
    return ((v.capacite_kg is None or c.poids_kg <= v.capacite_kg) and (v.capacite_m3 is None or c.volume_m3 <= v.capacite_m3)
            and (v.palettes is None or c.palettes <= v.palettes))


def _hhmm(minutes: float) -> str:
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def _raison_infaisable(i: int, c: CommandeOpt, p: Probleme) -> str | None:
    """Raison pour laquelle la commande ne peut être livrée par aucun véhicule, même seule. None si elle est faisable."""
    compat = _compatibles(c, p.vehicules)
    if not compat:
        besoin = " et ".join(n for n, on in (("frigo", c.frigo), ("ADR", c.adr)) if on)
        return f"Aucun véhicule compatible ({besoin} requis)"
    compat = [v for v in compat if _tient(c, v)]
    if not compat:
        return "Capacité : la commande dépasse la capacité de tous les véhicules compatibles"
    meilleur = None
    for v in compat:
        m = p.matrices[v.profil]
        aller, retour = m[0][i], m[i][0]
        if aller >= INJOIGNABLE_S or retour >= INJOIGNABLE_S:
            continue
        meilleur = min(meilleur or 10**12, aller + retour)
        arrivee_min = max(p.ouverture_min * 60 + aller, (c.debut_min or 0) * 60) / 60
        if c.fin_min is not None and p.ouverture_min * 60 + aller > c.fin_min * 60:
            continue
        fin = arrivee_min + c.service_min + retour / 60
        if fin > p.fermeture_min or (aller + retour) / 60 + c.service_min > p.duree_max_min:
            continue
        return None
    if meilleur is None:
        return "Adresse inaccessible par la route avec le gabarit de la flotte"
    # Faisable matériellement mais pas dans les horaires : on précise lequel.
    v0 = min(compat, key=lambda v: p.matrices[v.profil][0][i])
    aller = p.matrices[v0.profil][0][i]
    if c.fin_min is not None and p.ouverture_min * 60 + aller > c.fin_min * 60:
        return f"Fenêtre horaire inaccessible : arrivée au plus tôt à {_hhmm(p.ouverture_min + aller / 60)}, fenêtre close à {_hhmm(c.fin_min)}"
    if (meilleur / 60) + c.service_min > p.duree_max_min:
        return "Durée maximale de tournée dépassée dès le premier arrêt"
    return "Retour au dépôt impossible avant la fermeture"


def _raison_probable(c: CommandeOpt, p: Probleme, restantes: list[CommandeOpt]) -> str:
    """Commande faisable seule mais laissée de côté par le solveur : on propose la cause la plus probable."""
    demande_kg = sum(x.poids_kg for x in restantes)
    demande_pal = sum(x.palettes for x in restantes)
    cap_kg = sum(v.capacite_kg for v in p.vehicules if v.capacite_kg is not None)
    cap_pal = sum(v.palettes for v in p.vehicules if v.palettes is not None)
    if (p.vehicules and all(v.capacite_kg is not None for v in p.vehicules) and demande_kg > cap_kg) or \
       (all(v.palettes is not None for v in p.vehicules) and demande_pal > cap_pal):
        return "Capacité totale de la flotte insuffisante pour l'ensemble des commandes"
    if c.debut_min is not None or c.fin_min is not None:
        return "Fenêtre horaire incompatible avec les autres arrêts ou la durée maximale de tournée"
    return "Capacité ou durée de tournée insuffisante avec les autres commandes"


def optimiser(p: Probleme) -> Solution:
    if not p.vehicules:
        return Solution([], [(c.id, "Aucun véhicule disponible") for c in p.commandes])
    non_affectees: list[tuple[int, str]] = []
    faisables: list[int] = []  # indices (1-based) dans p.commandes
    for k, c in enumerate(p.commandes, start=1):
        raison = _raison_infaisable(k, c, p)
        if raison:
            non_affectees.append((c.id, raison))
        else:
            faisables.append(k)
    if not faisables:
        return Solution([], non_affectees)

    noeuds = [0] + faisables  # noeud n -> ligne noeuds[n] des matrices
    nv = len(p.vehicules)
    manager = pywrapcp.RoutingIndexManager(len(noeuds), nv, 0)
    routing = pywrapcp.RoutingModel(manager)
    commande = lambda n: p.commandes[noeuds[n] - 1]  # noqa: E731

    # Coût d'un arc = durée de trajet du véhicule ; durée de dimension = trajet + service à l'origine.
    profils = sorted({v.profil for v in p.vehicules})
    cb_cout, cb_temps = {}, {}
    for prof in profils:
        m = p.matrices[prof]
        cb_cout[prof] = routing.RegisterTransitCallback(
            lambda a, b, m=m: int(m[noeuds[manager.IndexToNode(a)]][noeuds[manager.IndexToNode(b)]]))
        cb_temps[prof] = routing.RegisterTransitCallback(
            lambda a, b, m=m: int(m[noeuds[manager.IndexToNode(a)]][noeuds[manager.IndexToNode(b)]])
            + (commande(manager.IndexToNode(a)).service_min * 60 if manager.IndexToNode(a) else 0))
    for v, veh in enumerate(p.vehicules):
        routing.SetArcCostEvaluatorOfVehicle(cb_cout[veh.profil], v)

    horizon = min(p.fermeture_min * 60, 86400)
    routing.AddDimensionWithVehicleTransits([cb_temps[v.profil] for v in p.vehicules], horizon, horizon, False, "Temps")
    temps = routing.GetDimensionOrDie("Temps")
    temps.SetGlobalSpanCostCoefficient(0)
    for v in range(nv):
        temps.CumulVar(routing.Start(v)).SetRange(p.ouverture_min * 60, horizon)
        temps.CumulVar(routing.End(v)).SetRange(p.ouverture_min * 60, horizon)
        temps.SetSpanUpperBoundForVehicle(p.duree_max_min * 60, v)
        temps.SetSpanCostCoefficientForVehicle(1, v)  # évite les attentes inutiles
    for n in range(1, len(noeuds)):
        c = commande(n)
        debut = (c.debut_min or 0) * 60
        fin = min((c.fin_min * 60) if c.fin_min is not None else horizon, horizon)
        temps.CumulVar(manager.NodeToIndex(n)).SetRange(max(debut, p.ouverture_min * 60), max(fin, debut))

    def capacite(nom, valeurs, echelle, getter):
        cb = routing.RegisterUnaryTransitCallback(lambda i: int(round(getter(commande(manager.IndexToNode(i))) * echelle)) if manager.IndexToNode(i) else 0)
        caps = [int(round(x * echelle)) if x is not None else 10**9 for x in valeurs]
        routing.AddDimensionWithVehicleCapacity(cb, 0, caps, True, nom)

    capacite("Poids", [v.capacite_kg for v in p.vehicules], 1, lambda c: c.poids_kg)
    capacite("Volume", [v.capacite_m3 for v in p.vehicules], 100, lambda c: c.volume_m3)
    capacite("Palettes", [v.palettes for v in p.vehicules], 1, lambda c: c.palettes)

    for n in range(1, len(noeuds)):
        idx = manager.NodeToIndex(n)
        autorises = [i for i, v in enumerate(p.vehicules) if v in _compatibles(commande(n), p.vehicules)]
        routing.VehicleVar(idx).SetValues(autorises + [-1])
        routing.AddDisjunction([idx], PENALITE_NON_AFFECTEE)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    # Petits problèmes : inutile d'attendre la limite complète ; le paramètre reste un maximum.
    params.time_limit.FromSeconds(max(1, min(int(p.temps_calcul_s), 1 + len(faisables) // 3)))
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return Solution([], non_affectees + [(p.commandes[k - 1].id, "Aucune solution trouvée dans le temps imparti") for k in faisables])

    routes: list[RouteOpt] = []
    servies: set[int] = set()
    for v, veh in enumerate(p.vehicules):
        idx = solution.Value(routing.NextVar(routing.Start(v)))
        if routing.IsEnd(idx):
            continue
        m = p.matrices[veh.profil]
        arrets, precedent, trajet = [], 0, 0
        arrivees = []
        while not routing.IsEnd(idx):
            n = manager.IndexToNode(idx)
            arrivees.append((n, solution.Min(temps.CumulVar(idx))))
            idx = solution.Value(routing.NextVar(idx))
        premier_n, premiere_arrivee = arrivees[0]
        depart_s = premiere_arrivee - m[0][noeuds[premier_n]]  # départ au plus tard : pas d'attente avant le premier arrêt
        t, prec = depart_s, 0
        for n, arrivee in arrivees:
            ligne = noeuds[n]
            trajet += m[prec][ligne]
            attente = max(0, arrivee - (t + m[prec][ligne]))
            c = commande(n)
            arrets.append(ArretOpt(c.id, arrivee / 60, (arrivee + c.service_min * 60) / 60, attente / 60))
            servies.add(c.id)
            t, prec = arrivee + c.service_min * 60, ligne
        trajet += m[prec][0]
        routes.append(RouteOpt(veh.id, depart_s / 60, (t + m[prec][0]) / 60, int(trajet), arrets))
    restantes = [commande(n) for n in range(1, len(noeuds))]
    for c in restantes:
        if c.id not in servies:
            non_affectees.append((c.id, _raison_probable(c, p, restantes)))
    return Solution(routes, non_affectees)
