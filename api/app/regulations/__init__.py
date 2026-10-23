"""Règles de temps de conduite et de repos (règlement CE 561/2006) : module isolé, sans dépendance au reste de l'application.

Les instants sont des minutes depuis un lundi 00:00 de référence. Tout est pur : aucune lecture de base ni d'horloge.
"""
from . import constantes
from .activites import CONDUITE, DISPONIBILITE, REPOS, TRAVAIL, Activite, Infraction, normaliser
from .analyse import Analyse, Jour, Restant, analyser, restant
from .chrono import Chrono, Parcours, attendre, conduire, demarrer, travailler

__all__ = ["constantes", "CONDUITE", "DISPONIBILITE", "REPOS", "TRAVAIL", "Activite", "Infraction", "normaliser", "Analyse", "Jour", "Restant",
           "analyser", "restant", "Chrono", "Parcours", "attendre", "conduire", "demarrer", "travailler"]
