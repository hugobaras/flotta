"""Seuils du règlement (CE) n° 561/2006, en minutes. Chaque valeur renvoie à l'article indiqué.

À VÉRIFIER avec le texte officiel et un exploitant (voir README « Temps de conduite ») : les seuils ci-dessous sont ceux
du règlement tel que compris par l'auteur ; ce module n'a pas de valeur juridique.
"""
SEMAINE = 7 * 24 * 60  # semaine civile : du lundi 00:00 au dimanche 24:00 (art. 4, i)

# Art. 7 : pause après 4 h 30 de conduite
CONDUITE_CONTINUE_MAX = 4 * 60 + 30
PAUSE = 45
PAUSE_PARTIE_1 = 15  # la pause peut être fractionnée : 15 min puis 30 min, dans cet ordre
PAUSE_PARTIE_2 = 30

# Art. 6 : durées de conduite
CONDUITE_JOUR = 9 * 60
CONDUITE_JOUR_ETENDUE = 10 * 60  # au plus deux fois par semaine
EXTENSIONS_PAR_SEMAINE = 2
CONDUITE_SEMAINE = 56 * 60
CONDUITE_BIHEBDOMADAIRE = 90 * 60  # deux semaines consécutives

# Art. 8 : repos
REPOS_JOUR = 11 * 60
REPOS_JOUR_REDUIT = 9 * 60  # au plus trois fois entre deux repos hebdomadaires
REPOS_REDUITS_MAX = 3
REPOS_JOUR_FRACTIONNE_PARTIE_1 = 3 * 60  # 3 h puis 9 h = 12 h au total
FENETRE_REPOS_JOUR = 24 * 60  # un nouveau repos journalier doit être pris dans les 24 h qui suivent le précédent repos
REPOS_HEBDO = 45 * 60
REPOS_HEBDO_REDUIT = 24 * 60  # à compenser avant la fin de la troisième semaine suivante
PERIODES_MAX_ENTRE_REPOS_HEBDO = 6 * 24 * 60  # un repos hebdomadaire commence au plus tard à la fin de six périodes de 24 h
