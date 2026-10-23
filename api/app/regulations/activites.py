from dataclasses import dataclass

CONDUITE = "conduite"
TRAVAIL = "travail"  # autre tâche : chargement, livraison, attente de déchargement...
DISPONIBILITE = "disponibilite"  # attente dont la durée n'est pas connue à l'avance : ne compte pas comme pause
REPOS = "repos"  # pause ou repos : ni conduite ni travail
TYPES = (CONDUITE, TRAVAIL, DISPONIBILITE, REPOS)


@dataclass(frozen=True)
class Activite:
    """Activité d'un conducteur. Les instants sont en minutes depuis un lundi 00:00 de référence."""
    type: str
    debut: float
    fin: float

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"Type d'activité inconnu : {self.type}")
        if self.fin < self.debut:
            raise ValueError("Une activité ne peut pas finir avant de commencer")

    @property
    def duree(self) -> float:
        return self.fin - self.debut


@dataclass(frozen=True)
class Infraction:
    code: str
    message: str
    debut: float
    fin: float


def normaliser(activites: list[Activite]) -> list[Activite]:
    """Trie les activités, refuse les chevauchements et comble les trous par du repos (un trou = le conducteur ne travaille pas)."""
    triees = sorted((a for a in activites if a.duree > 0), key=lambda a: (a.debut, a.fin))
    sortie: list[Activite] = []
    for a in triees:
        if sortie:
            prec = sortie[-1]
            if a.debut < prec.fin - 1e-9:
                raise ValueError(f"Activités qui se chevauchent à {a.debut}")
            if a.debut > prec.fin + 1e-9:
                sortie.append(Activite(REPOS, prec.fin, a.debut))
        sortie.append(a)
    return sortie
