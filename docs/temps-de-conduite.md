# Temps de conduite et de repos (règlement CE 561/2006)

Le module `api/app/regulations/` est **isolé** (aucune dépendance au reste de l'application, aucune lecture de base ni d'horloge) : des fonctions pures sur des activités datées en minutes. Il est testé par 43 cas chiffrés (`api/tests/test_regulations.py`).

> **Ce module n'a pas de valeur juridique.** Les seuils ci-dessous sont ceux du règlement tels qu'ils ont été compris lors du développement. **Ils doivent être relus avec le texte officiel et par un exploitant avant tout usage en conditions réelles** (voir la liste des points à vérifier plus bas).

## Règles modélisées

| Règle | Seuil | Où dans le code |
|---|---|---|
| Pause après conduite continue (art. 7) | 45 min après 4 h 30, ou 15 min puis 30 min dans cet ordre | `chrono.py` (`Chrono`) |
| Conduite journalière (art. 6) | 9 h, 10 h au plus deux fois par semaine civile | `analyse.py` |
| Conduite hebdomadaire | 56 h par semaine, 90 h sur deux semaines consécutives | `analyse.py` |
| Repos journalier (art. 8) | 11 h, réduit à 9 h trois fois au plus entre deux repos hebdomadaires, ou fractionné 3 h + 9 h | `analyse.py` |
| Fenêtre de 24 h | un repos journalier valable doit être complété dans les 24 h qui suivent le repos précédent | `analyse.py` |
| Repos hebdomadaire | 45 h, réduit à 24 h (à compenser), au plus tard après six périodes de 24 h | `analyse.py` |

## Ce que l'application en fait

1. **Pauses insérées** : chaque tournée est recalculée avec les pauses obligatoires (`regulations.conduire`), placées au dernier moment permis. Le service chez un client et l'attente d'une fenêtre horaire ne comptent jamais comme une pause.
2. **Optimisation** : plafond de conduite par véhicule (9 h, ou ce qui reste au conducteur affecté) et heure de départ au plus tôt (repos journalier du conducteur). Les pauses sont modélisées par un surcoût de 45 min par 4 h 30 de trajet : toujours supérieur au nombre réel de pauses, donc un plan réalisable pour l'optimiseur l'est aussi une fois les pauses placées exactement (propriété testée).
3. **Conducteurs** : activités déclarées à la main (page Flotta, onglet Conducteurs, « Temps de conduite »). Le conducteur habituel d'un véhicule lui est affecté automatiquement ; l'affectation se change dans le planning.
4. **Sans conducteur affecté** : les règles s'appliquent à la tournée seule (9 h de conduite à l'optimisation).
5. **Alertes** : une modification manuelle qui dépasse la limite journalière ou hebdomadaire produit une alerte **Infraction** (rouge). Entre 9 h et 10 h sans conducteur connu, ou avec une extension disponible, c'est un avertissement « extension à 10 h ».

## À vérifier avec le texte officiel et un exploitant

- **Attente et pause** : une attente d'ouverture de créneau n'est pas comptée comme pause (choix prudent) ; certains exploitants l'utilisent comme pause si le conducteur en connaît la durée à l'avance.
- **Fenêtre de 24 h** : le repos doit être *complété* dans les 24 h (lecture retenue). Une lecture « commencé dans les 24 h » est moins stricte.
- **Pause fractionnée** : la première partie (15 min) ne remet pas le compteur à zéro ; la seconde (30 min) doit suivre dans la même période de 4 h 30. Une pause de 30 min suivie de 15 min est refusée.
- **Repos hebdomadaire réduit** : signalé comme « à compenser », mais la compensation (avant la fin de la troisième semaine suivante) n'est pas suivie.
- **Semaines** : calendaires (lundi 00:00 au dimanche 24:00), à l'heure de Paris. Les nuits de changement d'heure ne sont pas corrigées (une durée peut être décalée d'une heure).
- **Repos réduit au départ** : l'heure de départ au plus tôt suppose un repos de 11 h (le repos réduit de 9 h n'est pas utilisé pour planifier).
- **Non modélisé** : conduite en équipage de deux conducteurs, transbordeurs et trains, dérogations nationales (rayon d'action, véhicules exemptés, transports de courte distance), conduite hors règlement (véhicules de moins de 3,5 t), temps passé hors du champ du règlement.
- **Extensions à 10 h** : comptées par semaine civile, à partir des journées complètes de l'historique déclaré.

## Intégration au tachygraphe

Les activités sont déclarées à la main : il n'y a pas de lecture de carte conducteur ni de fichier de tachygraphe. Sans historique, un conducteur est supposé reposé et sans temps consommé.
