"""Suivi pas à pas de la conduite et des pauses (art. 7) : sert à l'analyse d'un historique et à la planification d'une tournée."""
from dataclasses import dataclass, field

from . import constantes as c
from .activites import CONDUITE, DISPONIBILITE, REPOS, TRAVAIL, Activite, Infraction


@dataclass
class Chrono:
    """État du compteur de conduite continue. `conduite` = conduite cumulée depuis la dernière pause valable."""
    conduite: float = 0.0
    partie1: bool = False  # première partie (>= 15 min) d'une pause fractionnée déjà prise
    infractions: list[Infraction] = field(default_factory=list)
    _depasse: bool = False

    def pause_necessaire(self) -> float:
        """Durée de la prochaine pause : 45 min, ou 30 min si la première partie (15 min) est déjà prise."""
        return c.PAUSE_PARTIE_2 if self.partie1 else c.PAUSE

    def reposer(self, debut: float, duree: float):
        """Applique un temps de repos (pause, trou, repos) au compteur."""
        if duree >= c.PAUSE or (self.partie1 and duree >= c.PAUSE_PARTIE_2):
            self.conduite, self.partie1, self._depasse = 0.0, False, False
        elif duree >= c.PAUSE_PARTIE_1:
            self.partie1 = True

    def conduire(self, debut: float, duree: float):
        """Ajoute de la conduite ; consigne une infraction au moment où les 4 h 30 sont dépassées."""
        if self.conduite + duree > c.CONDUITE_CONTINUE_MAX + 1e-9 and not self._depasse:
            moment = debut + (c.CONDUITE_CONTINUE_MAX - self.conduite)
            self.infractions.append(Infraction("PAUSE_MANQUANTE", "Plus de 4 h 30 de conduite sans pause suffisante", moment, debut + duree))
            self._depasse = True
        self.conduite += duree

    def appliquer(self, a: Activite):
        if a.type == CONDUITE:
            self.conduire(a.debut, a.duree)
        elif a.type == REPOS:
            self.reposer(a.debut, a.duree)
        # travail et disponibilité : ni conduite, ni pause (l'attente n'est jamais comptée comme pause)


@dataclass
class Parcours:
    """Résultat de la simulation d'une tournée : activités datées (pauses insérées comprises)."""
    activites: list[Activite] = field(default_factory=list)
    pauses: list[tuple[float, float]] = field(default_factory=list)
    conduite_totale: float = 0.0
    chrono: Chrono = field(default_factory=Chrono)
    t: float = 0.0


def demarrer(t: float, chrono: Chrono | None = None) -> Parcours:
    return Parcours(t=t, chrono=chrono or Chrono())


def conduire(p: Parcours, duree: float) -> Parcours:
    """Conduit `duree` minutes en insérant les pauses obligatoires, au dernier moment permis."""
    reste = duree
    while reste > 1e-9:
        libre = c.CONDUITE_CONTINUE_MAX - p.chrono.conduite
        if libre <= 1e-9:  # limite atteinte : pause obligatoire
            pause = p.chrono.pause_necessaire()
            p.activites.append(Activite(REPOS, p.t, p.t + pause))
            p.pauses.append((p.t, p.t + pause))
            p.chrono.reposer(p.t, pause)
            p.t += pause
            continue
        tranche = min(reste, libre)
        p.activites.append(Activite(CONDUITE, p.t, p.t + tranche))
        p.chrono.conduire(p.t, tranche)
        p.conduite_totale += tranche
        p.t += tranche
        reste -= tranche
    return p


def travailler(p: Parcours, duree: float) -> Parcours:
    if duree > 0:
        p.activites.append(Activite(TRAVAIL, p.t, p.t + duree))
        p.t += duree
    return p


def attendre(p: Parcours, duree: float) -> Parcours:
    if duree > 0:
        p.activites.append(Activite(DISPONIBILITE, p.t, p.t + duree))
        p.t += duree
    return p
