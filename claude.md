# Prompts incrémentaux pour construire le produit dans Claude Code

## Mode d'emploi

1. Décompresse `transport-saas.zip`, ouvre le dossier dans Claude Code, `git init` puis un premier commit.
2. Copie le bloc **CLAUDE.md** ci-dessous à la racine du projet (fichier `CLAUDE.md`). Claude Code le relit à chaque session.
3. Envoie les prompts **un par un, dans l'ordre**. Une étape = une session (`/clear` entre deux) = un commit.
4. Pour chaque étape : commence en **mode plan** (Shift+Tab), relis le plan, puis laisse faire. Ne passe pas à l'étape suivante tant que les tests ne passent pas et que tu n'as pas testé à la main.
5. Après chaque étape, lance le **prompt de revue** (en bas) dans une nouvelle session.
6. Les étapes 1 à 5 suffisent pour proposer un pilote du contrôle départ. Les étapes 6 à 12 construisent le routage. Ne code pas la suite avant d'avoir des retours de tes contacts.

---

## CLAUDE.md (à copier à la racine du projet)

```markdown
# Transport SaaS : contexte projet

SaaS B2B pour entreprises de transport routier de marchandises (poids lourds, PME de 10 à 50 camions, France).
Deux modules : (1) contrôle avant départ sur téléphone (QR code, sans app), (2) routage poids lourd et
optimisation de tournées avec respect des temps de conduite légaux (règlement CE 561/2006).
Développeur unique : privilégier la simplicité, un monolithe modulaire, pas de microservices.

## Stack
- API : Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL + PostGIS, Redis + Celery (jobs), OR-Tools, Valhalla (routage camion)
- Front : Next.js (app router) + TypeScript, site web mobile (pas d'app native), MapLibre pour les cartes
- Déploiement : Docker Compose sur un serveur Scaleway/OVH, HTTPS via Caddy
- Tout l'UI en français

## Règles
- Multi-tenant : chaque table métier porte `company_id`, chaque requête est filtrée par la société de l'utilisateur. Test d'isolation obligatoire pour toute nouvelle route.
- Les pages chauffeur n'ont pas de mot de passe : jeton du QR code / lien personnel, et fonctionnent hors ligne.
- Pas de dépendance payante ni de service tiers sans me le demander. Pas de secrets dans le code (variables d'environnement).
- Chaque fonctionnalité vient avec ses tests (pytest côté API). `pytest` et `npm run build` doivent passer avant de dire « terminé ».
- Migrations Alembic pour tout changement de schéma, jamais de modification manuelle de la base.
- Pas de sur-ingénierie : si une demande est ambiguë, pose la question avant de coder.
- Les règles réglementaires (temps de conduite, etc.) sont codées dans un module isolé et testées sur des cas chiffrés. Indique toujours ce qui reste à vérifier avec le texte officiel.
- Les données personnelles (noms de chauffeurs, positions GPS) relèvent du RGPD : minimiser, documenter la durée de conservation.

## Commandes
- API : `cd api && pytest`
- Front : `cd web && npm run build`
- Tout : `docker compose up -d --build`

## Parcours
Les étapes de construction sont dans PROMPTS.md. Travaille uniquement sur l'étape demandée.
```

---

## Prompt de démarrage d'une session

```
Lis CLAUDE.md et le README. Résume en 5 lignes l'état actuel du projet (ce qui fonctionne, ce qui manque), puis attends mes instructions.
```

---

## Étape 0 : prendre en main le squelette

```
Lance les tests de l'API et le build du front, puis docker compose up. Corrige tout ce qui ne marche pas.
Ajoute un workflow GitHub Actions (.github/workflows/ci.yml) qui lance pytest et npm run build à chaque push.
Ne change aucune fonctionnalité.

Critères d'acceptation :
- pytest : tous les tests passent
- npm run build : OK
- http://localhost:3000/c/demo affiche la checklist du camion de démonstration
- la CI est verte
```

## Étape 1 : base de données propre et comptes (multi-tenant)

```
Objectif : remplacer create_all par Alembic, et remplacer la clé API unique par de vrais comptes exploitants rattachés à une société.

À faire :
1. Alembic : migration initiale correspondant aux modèles actuels, commande documentée dans le README.
2. Tables users (email, mot de passe haché avec argon2 ou bcrypt, rôle admin/exploitant, company_id) et sessions ou JWT court + refresh. Choisis le plus simple et justifie en deux lignes.
3. Écrans web : connexion, déconnexion, création du premier compte d'une société par un script (pas d'inscription publique pour l'instant).
4. Toutes les routes du back-office utilisent l'utilisateur courant pour déterminer company_id (supprime require_admin et current_company actuels).
5. Limitation des tentatives de connexion, mots de passe jamais journalisés.

Tests obligatoires :
- un utilisateur de la société A ne peut lire, modifier ni débloquer aucun véhicule ni contrôle de la société B (tester chaque route)
- les routes chauffeur /api/controle/{token} continuent de fonctionner sans compte

Critères d'acceptation : pytest vert, connexion fonctionnelle dans le navigateur, plus aucune référence à ADMIN_API_KEY.
```

## Étape 2 : checklists configurables (tes feuilles papier)

```
Objectif : l'exploitant crée et modifie ses propres checklists, au lieu de celles codées en dur dans checklists.py.

Contexte : voici le contenu de la feuille papier d'un client réel : [COLLE ICI LE TEXTE OU DÉCRIS LA FEUILLE].

À faire :
1. Tables checklist_templates (par société et par type de véhicule) et checklist_items (libellé, critique oui/non, ordre, actif).
2. Migration : les checklists actuelles deviennent le modèle par défaut copié à la création d'une société.
3. Écran exploitant : liste des modèles, ajouter/modifier/réordonner/désactiver des points, marquer critique.
4. Un contrôle enregistre une copie figée des points au moment du contrôle (modifier la checklist ne change pas l'historique).
5. L'endpoint chauffeur sert la checklist du modèle du véhicule.

Critères d'acceptation : je peux recréer la feuille papier du client dans l'écran, le chauffeur la voit sur /c/{token}, l'historique ancien reste lisible. Tests isolation multi-tenant inclus.
```

## Étape 3 : contrôle départ complet (alertes, tableau de bord, PDF)

```
Objectif : rendre le module de contrôle départ vendable.

À faire :
1. Alertes : sur défaut critique, envoi d'un email (et SMS en option) via Brevo. Clé API en variable d'environnement, destinataires configurables par société. Si l'envoi échoue, réessayer en tâche de fond (Celery) sans bloquer le chauffeur.
2. Tableau de bord exploitant : état du jour par camion (contrôlé / non contrôlé / défaut / bloqué), contrôles récents, filtres par date, véhicule, conducteur, défaut seulement.
3. Détail d'un contrôle : points, commentaires, photos (affichées), signature, position sur une mini-carte, bouton PDF.
4. PDF amélioré : logo et nom de la société, mise en page propre, photos des défauts incluses, signature.
5. Déblocage d'un véhicule avec commentaire obligatoire (qui, quand, pourquoi), tracé dans l'historique.
6. Rappel : liste des camions sans contrôle à une heure donnée (configurable).
7. Conservation : purge des photos et contrôles après une durée configurable (défaut 3 ans), documentée.

Critères d'acceptation : je scanne le QR, signale un défaut critique, je reçois l'email, le camion apparaît bloqué, je le débloque avec commentaire. Tests pour chaque règle métier.
```

## Étape 4 : flotte et chauffeurs

```
Objectif : gérer proprement les véhicules et les conducteurs, base du routage.

À faire :
1. Véhicules : CRUD complet avec gabarit (hauteur, largeur, longueur, PTAC, charge utile, nombre d'essieux), type, capacité (palettes, kg, m³), ADR oui/non, frigo oui/non, statut actif.
2. Import CSV de la flotte avec aperçu et rapport d'erreurs ligne par ligne.
3. Conducteurs : CRUD, code PIN court pour la saisie sur téléphone, véhicule habituel. Le nom saisi dans le contrôle départ est remplacé par une sélection du conducteur (en gardant un mode hors ligne).
4. Impression de planches de QR codes (PDF, 6 par page, avec la plaque) pour coller dans les cabines.

Critères d'acceptation : import d'un CSV de 30 camions, impression des QR, contrôle départ avec sélection du conducteur par PIN. Tests d'import avec fichiers valides et invalides.
```

> **Point d'arrêt** : tu as maintenant un produit « contrôle départ » complet. Fais-le tester à 2 ou 3 contacts avant de continuer.

## Étape 5 : commandes (arrêts à livrer) et géocodage

```
Objectif : importer les commandes de la journée et les placer sur une carte.

À faire :
1. Modèle Order : référence, client, adresse, lat/lng, poids, volume, palettes, fenêtre de livraison (début/fin), durée de service, contraintes (frigo, ADR, hayon), date de livraison, statut.
2. Import CSV / Excel avec mappage des colonnes choisi par l'utilisateur (mémorisé par société), aperçu, rapport d'erreurs.
3. Géocodage via l'API Adresse (api-adresse.data.gouv.fr) en lot, avec cache en base ; les adresses non trouvées ou douteuses (score bas) sont signalées et corrigeables à la main (clic sur la carte).
4. Carte MapLibre avec les commandes du jour, filtre par date.
5. Dépôts : modèle Depot (adresse, horaires), un par société au minimum.

Critères d'acceptation : import d'un fichier de 100 commandes, 95 % géocodées automatiquement, les autres corrigeables. Tests sur le parseur CSV et le cache de géocodage (service externe mocké).
```

## Étape 6 : routage poids lourd en production

```
Objectif : un itinéraire camion fiable, affiché sur la carte.

À faire :
1. Valhalla : vérifier le profil truck (hauteur, largeur, longueur, poids, essieux, hazmat), documenter la construction des tuiles France et la mise à jour mensuelle.
2. Endpoint d'itinéraire entre deux points ou plus pour un véhicule donné (gabarit pris dans la fiche véhicule). Renvoie durée, distance, géométrie décodée en GeoJSON, et les avertissements de restriction si Valhalla les fournit.
3. Estimation des péages et du carburant : champs prévus, avec des valeurs paramétrables par société (coût au km, consommation), sans API payante pour l'instant.
4. Affichage de l'itinéraire sur la carte MapLibre.
5. Si Valhalla est injoignable : message clair à l'utilisateur, jamais d'itinéraire inventé sans l'indiquer.

Critères d'acceptation : un 4 m de haut ne passe pas sous un pont à 3,5 m connu (test avec un cas réel de ma région, que je fournirai). Tests avec Valhalla mocké.
```

## Étape 7 : optimisation de tournées asynchrone

```
Objectif : lancer l'optimisation en tâche de fond et conserver les plans.

À faire :
1. Celery + Redis : l'endpoint /api/optimize devient POST /api/plans qui crée un job et renvoie un identifiant ; le front interroge l'état (en attente, en cours, terminé, échec) avec une barre de progression simple.
2. Modèles Plan, Route (un par véhicule), RouteStop (ordre, heure d'arrivée prévue, commande) persistés en base.
3. La matrice de temps vient de Valhalla ; une matrice par profil de véhicule si la flotte est mixte (gabarits différents).
4. Contraintes prises en charge : capacités (poids, volume, palettes), fenêtres horaires, durée de service, compatibilité véhicule/commande (frigo, ADR), dépôt de départ et de retour, durée maximale de tournée.
5. Les commandes non affectées sont listées avec la raison probable (capacité, fenêtre horaire, aucun véhicule compatible).
6. Paramètre « temps de calcul maximal » (10 s par défaut).

Critères d'acceptation : 100 commandes et 8 camions donnent un plan en moins de 60 s, avec les non affectées expliquées. Tests unitaires de optimize.py étendus aux nouvelles contraintes.
```

## Étape 8 : interface de planification (le cœur pour l'exploitant)

```
Objectif : un exploitant planifie sa journée plus vite qu'avec son Excel.

À faire :
1. Écran planning : à gauche la liste des camions avec leur tournée (frise horaire des arrêts), à droite la carte avec les itinéraires colorés par camion.
2. Boutons : « Optimiser », « Réoptimiser sans toucher aux tournées verrouillées ».
3. Modification à la main : glisser-déposer d'un arrêt vers un autre camion ou une autre position, recalcul immédiat des heures d'arrivée et des alertes (retard sur fenêtre, surcharge, durée dépassée), sans relancer toute l'optimisation.
4. Verrouiller un arrêt ou une tournée (l'optimiseur n'y touche plus).
5. Indicateurs : kilomètres, durée, taux de remplissage, nombre d'alertes, comparaison avec le plan avant modification.
6. Annuler / rétablir, enregistrer plusieurs versions d'un plan.

Critères d'acceptation : je modifie un plan à la main et vois l'effet en moins d'une seconde. L'interface reste utilisable sur tablette. Tests côté API pour le recalcul des heures d'arrivée.
```

## Étape 9 : temps de conduite légal (CE 561/2006)

> C'est ta vraie différenciation : fais cette étape avec soin et fais relire les règles par un exploitant.

```
Objectif : un plan ne doit jamais violer les règles de temps de conduite et de repos.

Règles à modéliser (à vérifier avec le texte officiel du règlement CE 561/2006 et me dire ce qui reste incertain) :
- conduite continue max 4 h 30, puis pause de 45 min (ou 15 min puis 30 min)
- conduite journalière max 9 h, portée à 10 h au plus deux fois par semaine
- conduite hebdomadaire max 56 h, et 90 h sur deux semaines consécutives
- repos journalier 11 h (réduit à 9 h au plus trois fois entre deux repos hebdomadaires)
- repos hebdomadaire 45 h (réduit possible avec compensation)

À faire :
1. Module isolé api/app/regulations/ (sans dépendance au reste) : fonctions pures qui, à partir d'un historique d'activité d'un conducteur et d'une séquence prévue, calculent les temps restants et les infractions.
2. Jeux de tests chiffrés nombreux (journée de 8 h, journée à 10 h, deux 10 h dans la semaine, pause fractionnée, etc.).
3. Intégration à l'optimisation : dimensions OR-Tools pour la conduite continue et la durée journalière, insertion automatique des pauses dans les tournées, et prise en compte des temps déjà consommés par chaque conducteur.
4. Affichage dans le planning : pauses visibles sur la frise, alerte rouge si une modification manuelle crée une infraction, temps de conduite restant par conducteur.
5. Mode « sans conducteur affecté » : les règles s'appliquent par tournée.

Critères d'acceptation : aucun plan généré ne dépasse 4 h 30 sans pause ni 10 h par jour ; une modification manuelle fautive est signalée. Couverture de tests élevée sur le module regulations.
```

## Étape 10 : plan du chauffeur sur téléphone

```
Objectif : le chauffeur reçoit sa tournée sur son téléphone et la suit.

À faire :
1. Lien personnel de la tournée du jour (envoyé par SMS ou email, ou lisible via le QR du camion) : liste ordonnée des arrêts avec adresse, heure prévue, contact, consignes.
2. Bouton « Naviguer » qui ouvre l'application de navigation du téléphone vers l'arrêt (lien géo universel).
3. Statut par arrêt : arrivé, livré, impossible (motif), avec heure et position ; photo de preuve et signature du destinataire en option.
4. Fonctionne hors ligne comme le contrôle départ (file d'attente et synchronisation).
5. L'exploitant voit l'avancement en temps réel sur le planning (arrêts livrés, retards).
6. Le contrôle départ du jour apparaît en premier : tournée verrouillée tant que le contrôle n'est pas fait ou si le camion est bloqué.

Critères d'acceptation : je simule une journée complète sur téléphone, y compris une coupure réseau en milieu de tournée. Tests API sur les changements de statut et l'idempotence.
```

## Étape 11 : temps réel et replanification

```
Objectif : réagir quand la journée déraille.

À faire :
1. Détection de retard : à partir de la position et du statut des arrêts, recalculer les heures d'arrivée prévues ; alerte si une fenêtre horaire va être manquée.
2. Réoptimisation partielle : proposer à l'exploitant 2 ou 3 solutions (réaffecter l'arrêt X à un autre camion, décaler, ajouter une pause) avec l'impact chiffré. L'exploitant valide, jamais de changement automatique.
3. Commande urgente : insertion d'une commande dans les tournées en cours au meilleur endroit.
4. Panne : retirer un camion, redistribuer ses arrêts restants.
5. Abstraction du fournisseur de trafic (interface), implémentation avec HERE ou TomTom derrière un indicateur de fonctionnalité, désactivée par défaut. Ne l'active pas sans me demander.

Critères d'acceptation : scénarios de test automatisés (retard, panne, urgence) avec résultats attendus. Aucune modification de plan sans validation explicite.
```

## Étape 12 : offres, facturation et limites

```
Objectif : vendre deux offres, Essentiel et Pro, par camion et par mois.

Grille actuelle (modifiable dans la configuration, jamais en dur) :
- Essentiel 45 €/camion/mois : contrôle départ, routage, optimisation, plan chauffeur ; 2 utilisateurs exploitants
- Pro 75 €/camion/mois : + temps de conduite légal, temps réel et replanification, API, statistiques complètes ; utilisateurs illimités
- Minimum de facturation : 500 €/mois (Essentiel), 900 €/mois (Pro)

À faire :
1. Modèle Subscription (offre, nombre de camions facturés, dates, statut) par société, et drapeaux de fonctionnalités dérivés de l'offre.
2. Les fonctions Pro sont verrouillées côté API ET côté interface en Essentiel, avec un message d'upsell clair.
3. Back-office interne (pour moi) : créer une société, choisir l'offre, fixer le nombre de camions, suspendre.
4. Génération de devis et de factures PDF (numérotation, mentions légales françaises, TVA paramétrable). Pas de paiement en ligne pour l'instant : virement.
5. Tableau de suivi pour moi : MRR, nombre de camions par client, clients en essai.

Critères d'acceptation : une société en Essentiel ne peut pas appeler les endpoints Pro (tests). Une facture PDF correcte pour 20 camions Pro avec remise de paiement annuel.
```

## Étape 13 : API publique et intégrations

```
Objectif : s'intégrer aux TMS/ERP des clients (offre Pro).

À faire :
1. Clés API par société (créer, révoquer, dernière utilisation), en-tête Authorization, limitation de débit.
2. API REST documentée (OpenAPI) : commandes (créer, lister, modifier), plans, statuts de livraison, contrôles départ.
3. Webhooks sortants signés (HMAC) : plan publié, arrêt livré, défaut critique ; réessais avec délai croissant.
4. Exemples de code dans la documentation (curl, Python).

Critères d'acceptation : un script d'exemple crée une commande par API et reçoit un webhook. Tests d'authentification, d'isolation et de signature des webhooks.
```

## Étape 14 : sécurité, RGPD, production

```
Objectif : être prêt à héberger de vrais clients.

À faire :
1. Déploiement : docker-compose de production avec Caddy (HTTPS automatique), variables d'environnement, volumes persistants, sauvegardes quotidiennes de la base et des photos vers un stockage S3 (restauration testée et documentée).
2. Sécurité : en-têtes HTTP, limitation de débit, validation stricte des fichiers envoyés, journal d'audit des actions sensibles (déblocage, changement d'offre, suppression), vérification des dépendances (pip-audit, npm audit) dans la CI.
3. RGPD : registre des traitements (modèle), politique de conservation appliquée automatiquement, export et suppression des données d'un conducteur sur demande, mentions et contrat de sous-traitance (modèles à faire relire par un juriste).
4. Observabilité : Sentry, journaux structurés, endpoint de santé, alerte si le site tombe (UptimeRobot).
5. Page d'état et procédure d'incident (document court).

Critères d'acceptation : restauration complète testée sur un serveur vierge, analyse de dépendances sans vulnérabilité critique, document RGPD généré.
```

## Étape 15 : prêt pour les pilotes

```
Objectif : un nouveau client est opérationnel en moins d'une demi-journée.

À faire :
1. Parcours d'accueil guidé : importer la flotte, importer les conducteurs, créer les checklists, imprimer les QR, importer des commandes d'essai.
2. Jeu de données de démonstration activable en un clic (société fictive, 15 camions, 80 commandes).
3. Aide intégrée courte (infobulles) et page « Démarrer » avec 5 étapes.
4. Recueil de retours : bouton « Signaler un problème » avec capture automatique du contexte (page, société, version).
5. Documentation client d'une page par module (PDF).

Critères d'acceptation : je déroule l'onboarding avec une société vierge en moins de 30 minutes en suivant uniquement l'interface.
```

---

## Prompt de revue (après chaque étape, dans une nouvelle session)

```
Relis les changements de la dernière étape (git diff depuis le commit précédent) comme un relecteur exigeant.
Vérifie en priorité :
1. isolation multi-tenant : y a-t-il une route ou une requête sans filtre company_id ?
2. sécurité : validation des entrées, fichiers envoyés, secrets, injections
3. cas limites : réseau coupé, doublons, données vides, très gros volumes
4. tests : les règles métier sont-elles réellement testées, pas seulement les cas heureux ?
5. dette : ce qui est resté en TODO et que je dois savoir

Liste les problèmes par gravité, corrige ceux qui sont critiques, et signale le reste sans le corriger.
```

## Prompt de dépannage

```
Voici l'erreur : [colle le message ou la trace]. Reproduis-la d'abord avec un test qui échoue, trouve la cause réelle (pas un contournement), corrige, puis vérifie que tous les tests passent.
```
