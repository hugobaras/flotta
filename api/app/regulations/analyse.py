"""Analyse d'un historique d'activités et calcul des temps restants (fonctions pures)."""
from dataclasses import dataclass, field

from . import constantes as c
from .activites import CONDUITE, REPOS, Activite, Infraction, normaliser
from .chrono import Chrono


@dataclass
class Jour:
    debut: float
    fin: float  # début du repos journalier qui clôt la journée (ou fin de l'historique)
    conduite: float
    repos_apres: float | None  # durée du repos qui suit, None si la journée est en cours
    type_repos: str | None  # normal | reduit | fractionne | hebdomadaire


@dataclass
class Analyse:
    infractions: list[Infraction] = field(default_factory=list)
    jours: list[Jour] = field(default_factory=list)
    conduite_par_semaine: dict[int, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # informations non bloquantes (repos hebdomadaire réduit à compenser...)
    chrono: Chrono = field(default_factory=Chrono)


def _fusionner_repos(tl: list[Activite]) -> list[tuple[float, float]]:
    repos: list[tuple[float, float]] = []
    for a in tl:
        if a.type != REPOS:
            continue
        if repos and abs(repos[-1][1] - a.debut) < 1e-9:
            repos[-1] = (repos[-1][0], a.fin)
        else:
            repos.append((a.debut, a.fin))
    return repos


def _conduite_entre(tl: list[Activite], debut: float, fin: float) -> float:
    return sum(max(0.0, min(a.fin, fin) - max(a.debut, debut)) for a in tl if a.type == CONDUITE)


def _conduite_par_semaine(tl: list[Activite]) -> dict[int, float]:
    semaines: dict[int, float] = {}
    for a in tl:
        if a.type != CONDUITE:
            continue
        t = a.debut
        while t < a.fin - 1e-9:
            w = int(t // c.SEMAINE)
            fin_s = min(a.fin, (w + 1) * c.SEMAINE)
            semaines[w] = semaines.get(w, 0.0) + (fin_s - t)
            t = fin_s
    return semaines


def analyser(activites: list[Activite]) -> Analyse:
    tl = normaliser(activites)
    res = Analyse()
    if not tl:
        return res
    for a in tl:
        res.chrono.appliquer(a)
    res.infractions.extend(res.chrono.infractions)

    debut_jour = tl[0].debut
    fin_hist = tl[-1].fin
    fraction = False  # première partie (>= 3 h) d'un repos journalier fractionné vue dans la journée en cours
    reduits = 0
    dernier_hebdo_fin: float | None = None
    extensions: dict[int, int] = {}

    for debut_r, fin_r in _fusionner_repos(tl):
        longueur = fin_r - debut_r
        if debut_r < debut_jour:  # repos antérieur au début de journée courant (début d'historique)
            continue
        if longueur < c.REPOS_JOUR_REDUIT:
            if longueur >= c.REPOS_JOUR_FRACTIONNE_PARTIE_1:
                fraction = True
            continue
        if longueur >= c.REPOS_HEBDO_REDUIT:
            type_repos = "hebdomadaire"
        elif longueur >= c.REPOS_JOUR:
            type_repos = "normal"
        elif fraction:
            type_repos = "fractionne"
        else:
            type_repos = "reduit"
        conduite = _conduite_entre(tl, debut_jour, debut_r)
        res.jours.append(Jour(debut_jour, debut_r, conduite, longueur, type_repos))

        semaine = int(debut_jour // c.SEMAINE)
        if conduite > c.CONDUITE_JOUR_ETENDUE + 1e-9:
            res.infractions.append(Infraction("CONDUITE_JOURNALIERE", "Plus de 10 h de conduite dans la journée", debut_jour, debut_r))
        elif conduite > c.CONDUITE_JOUR + 1e-9:
            extensions[semaine] = extensions.get(semaine, 0) + 1
            if extensions[semaine] > c.EXTENSIONS_PAR_SEMAINE:
                res.infractions.append(Infraction("EXTENSION_10H_EXCEDEE", "Plus de deux journées de conduite supérieures à 9 h dans la semaine", debut_jour, debut_r))
        if (debut_r - debut_jour) > c.FENETRE_REPOS_JOUR - min(longueur, c.REPOS_JOUR) + 1e-9:
            res.infractions.append(Infraction("REPOS_JOURNALIER_TARDIF", "Repos journalier pris plus de 24 h après le précédent repos", debut_jour, fin_r))
        if type_repos == "hebdomadaire":
            if dernier_hebdo_fin is not None and debut_r - dernier_hebdo_fin > c.PERIODES_MAX_ENTRE_REPOS_HEBDO + 1e-9:
                res.infractions.append(Infraction("REPOS_HEBDO_TARDIF", "Repos hebdomadaire pris plus de six périodes de 24 h après le précédent", dernier_hebdo_fin, debut_r))
            if longueur < c.REPOS_HEBDO:
                res.notes.append("Repos hebdomadaire réduit (moins de 45 h) : à compenser avant la fin de la troisième semaine suivante")
            dernier_hebdo_fin, reduits = fin_r, 0
        elif type_repos == "reduit":
            reduits += 1
            if reduits > c.REPOS_REDUITS_MAX:
                res.infractions.append(Infraction("REPOS_REDUIT_EXCEDE", "Plus de trois repos journaliers réduits entre deux repos hebdomadaires", debut_r, fin_r))
        debut_jour, fraction = fin_r, False

    # Journée en cours (aucun repos valable ne la clôt dans l'historique)
    if fin_hist > debut_jour:
        res.jours.append(Jour(debut_jour, fin_hist, _conduite_entre(tl, debut_jour, fin_hist), None, None))
        if fin_hist - debut_jour > c.FENETRE_REPOS_JOUR + 1e-9:
            res.infractions.append(Infraction("REPOS_JOURNALIER_MANQUANT", "Aucun repos journalier valable pris dans les 24 h", debut_jour, fin_hist))
        ouverte = res.jours[-1].conduite
        semaine = int(debut_jour // c.SEMAINE)
        if ouverte > c.CONDUITE_JOUR_ETENDUE + 1e-9:
            res.infractions.append(Infraction("CONDUITE_JOURNALIERE", "Plus de 10 h de conduite dans la journée", debut_jour, fin_hist))
        elif ouverte > c.CONDUITE_JOUR + 1e-9 and extensions.get(semaine, 0) + 1 > c.EXTENSIONS_PAR_SEMAINE:
            res.infractions.append(Infraction("EXTENSION_10H_EXCEDEE", "Plus de deux journées de conduite supérieures à 9 h dans la semaine", debut_jour, fin_hist))
    ref = dernier_hebdo_fin if dernier_hebdo_fin is not None else tl[0].debut
    if dernier_hebdo_fin is not None and fin_hist - ref > c.PERIODES_MAX_ENTRE_REPOS_HEBDO + 1e-9:
        res.infractions.append(Infraction("REPOS_HEBDO_MANQUANT", "Aucun repos hebdomadaire pris après six périodes de 24 h", ref, fin_hist))

    res.conduite_par_semaine = _conduite_par_semaine(tl)
    for w, total in sorted(res.conduite_par_semaine.items()):
        if total > c.CONDUITE_SEMAINE + 1e-9:
            res.infractions.append(Infraction("CONDUITE_HEBDOMADAIRE", "Plus de 56 h de conduite dans la semaine", w * c.SEMAINE, (w + 1) * c.SEMAINE))
        precedent = res.conduite_par_semaine.get(w - 1)
        if precedent is not None and total + precedent > c.CONDUITE_BIHEBDOMADAIRE + 1e-9:
            res.infractions.append(Infraction("CONDUITE_BIHEBDOMADAIRE", "Plus de 90 h de conduite sur deux semaines consécutives", (w - 1) * c.SEMAINE, (w + 1) * c.SEMAINE))
    res.infractions.sort(key=lambda i: (i.debut, i.code))
    return res


@dataclass
class Restant:
    """Ce qu'un conducteur peut encore faire s'il reprend la conduite à `maintenant`."""
    conduite_continue: float  # avant la prochaine pause obligatoire
    pause_necessaire: float  # durée de cette pause (45 min, ou 30 si la première partie est faite)
    conduite_jour: float  # reste de la journée, en tenant compte d'une éventuelle extension à 10 h
    conduite_jour_normale: float  # reste jusqu'à 9 h
    extensions_restantes: int
    conduite_semaine: float  # reste de la semaine et du plafond sur deux semaines
    debut_journee: float
    repos_avant: float  # dernier moment pour commencer un repos journalier de 11 h
    debut_possible: float  # plus tôt pour reprendre si le repos en cours est incomplet (repos de 11 h)
    debut_possible_reduit: float  # idem avec un repos réduit de 9 h (s'il en reste)


def restant(activites: list[Activite], maintenant: float) -> Restant:
    """Compteurs d'un conducteur à l'instant `maintenant`. Les activités postérieures sont ignorées."""
    passees = [Activite(a.type, a.debut, min(a.fin, maintenant)) for a in activites if a.debut < maintenant]
    tl = normaliser(passees)
    if tl and tl[-1].fin < maintenant:
        tl.append(Activite(REPOS, tl[-1].fin, maintenant))  # temps écoulé depuis la dernière activité = repos
    if not tl:
        tl = [Activite(REPOS, maintenant - 1, maintenant)]
    an = analyser(tl)
    # Journée en cours : la dernière si aucun repos valable ne la clôt ; sinon une nouvelle journée commence maintenant.
    ouverte = an.jours[-1] if an.jours and an.jours[-1].repos_apres is None else None
    debut_jour = ouverte.debut if ouverte else maintenant
    conduite_jour = ouverte.conduite if ouverte else 0.0
    semaine_jour = int(debut_jour // c.SEMAINE)
    closes_etendues = sum(1 for j in an.jours if j.repos_apres is not None and j.conduite > c.CONDUITE_JOUR + 1e-9
                          and int(j.debut // c.SEMAINE) == semaine_jour)
    extensions_restantes = max(0, c.EXTENSIONS_PAR_SEMAINE - closes_etendues - (1 if conduite_jour > c.CONDUITE_JOUR + 1e-9 else 0))
    plafond_jour = c.CONDUITE_JOUR_ETENDUE if closes_etendues < c.EXTENSIONS_PAR_SEMAINE else c.CONDUITE_JOUR
    semaine = int(maintenant // c.SEMAINE)
    cw = an.conduite_par_semaine.get(semaine, 0.0)
    pw = an.conduite_par_semaine.get(semaine - 1, 0.0)
    ch = an.chrono
    fin_derniere_activite = max((a.fin for a in tl if a.type != REPOS), default=None)
    dernier_repos_debut = fin_derniere_activite if fin_derniere_activite is not None else maintenant
    deja_repos = maintenant - dernier_repos_debut
    return Restant(
        conduite_continue=max(0.0, c.CONDUITE_CONTINUE_MAX - ch.conduite), pause_necessaire=ch.pause_necessaire(),
        conduite_jour=max(0.0, plafond_jour - conduite_jour), conduite_jour_normale=max(0.0, c.CONDUITE_JOUR - conduite_jour),
        extensions_restantes=extensions_restantes,
        conduite_semaine=max(0.0, min(c.CONDUITE_SEMAINE - cw, c.CONDUITE_BIHEBDOMADAIRE - (pw + cw))),
        debut_journee=debut_jour, repos_avant=debut_jour + c.FENETRE_REPOS_JOUR - c.REPOS_JOUR,
        debut_possible=maintenant if deja_repos >= c.REPOS_JOUR or fin_derniere_activite is None else dernier_repos_debut + c.REPOS_JOUR,
        debut_possible_reduit=maintenant if deja_repos >= c.REPOS_JOUR_REDUIT or fin_derniere_activite is None else dernier_repos_debut + c.REPOS_JOUR_REDUIT,
    )
