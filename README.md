# Transport SaaS

Squelette du module « contrôle avant départ ». Contexte et étapes : `claude.md`.

- API : `cd api && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pytest`
- Front : `cd web && npm install && npm run build`
- Tout : `docker compose up -d --build` puis http://localhost:3000/c/demo

## Base de données et comptes

- Migrations : `cd api && alembic upgrade head` (variable `DATABASE_URL`, SQLite par défaut). Nouvelle migration : `alembic revision --autogenerate -m "message"`.
- Premier compte d'une société (pas d'inscription publique) : `cd api && python create_user.py email@exemple.fr "Nom société" admin` (mot de passe demandé, ou variable `PASSWORD`, 10 caractères minimum).
- Docker : `docker compose exec api python create_user.py ...` après le premier démarrage.
- Sessions : cookie httpOnly, 7 jours, stockées hachées en base ; `COOKIE_SECURE=1` derrière HTTPS.
- Limitation de connexion : 5 échecs / 15 min par email, en mémoire (un seul worker).

## Données personnelles et conservation (RGPD)

- Un contrôle contient le nom du conducteur, sa signature, des photos et, si le téléphone l'autorise, sa position GPS au moment du contrôle. Ces données sont minimales : pas de suivi continu.
- Durée de conservation par société : 3 ans par défaut (`retention_jours`, modifiable de 30 à 3650 jours dans Paramètres). Passé ce délai, `python purge.py` supprime les contrôles, les photos (fichiers compris) et les positions. À lancer chaque jour ; la planification automatique (Celery) arrive à l'étape 3B. Le journal des déblocages (qui, quand, pourquoi) n'est pas purgé.
- Photos : stockées sur disque (`UPLOAD_DIR`, volume Docker `uploads`), JPEG ou PNG vérifiés sur le contenu, 5 Mo et 5 photos maximum par contrôle, ajout possible dans l'heure qui suit le contrôle.
- Rappel : heure configurable par société (Paramètres), liste des camions sans contrôle affichée sur le tableau de bord.

## Alertes, rappels et PDF

- Services : `redis` et `worker` (Celery avec planificateur intégré) en plus de `api`, `web` et `db`.
- Brevo (email) : variables `BREVO_API_KEY` et `BREVO_SENDER` (expéditeur validé chez Brevo), `APP_URL` pour le lien dans l'email. Sans clé, l'alerte est enregistrée avec le statut `non_configure` et rien n'est envoyé.
- Défaut critique : le contrôle est enregistré et le camion bloqué immédiatement ; l'email part en tâche de fond, réessayé après 1, 5, 15 puis 60 minutes (statuts de la table `alerts` : `en_attente`, `envoye`, `echec`, `non_configure`, `sans_destinataire`). Si Redis est indisponible, le chauffeur n'est pas impacté et le worker relance les alertes jamais tentées toutes les 5 minutes.
- Destinataires : Paramètres, un email par ligne (10 maximum par société). Pas de SMS pour l'instant.
- Rappel : un email par jour et par société, dès l'heure choisie, avec les camions sans contrôle. La purge RGPD tourne chaque nuit à 3 h (heure de Paris).
- PDF d'un contrôle : bouton sur la page de détail. Logo de la société : Paramètres (JPEG ou PNG, 1 Mo maximum).

## Flotte, conducteurs, QR codes (étape 4)

- Véhicules : gabarit (hauteur, largeur, longueur, PTAC, essieux), capacité (palettes, kg, m³), ADR, frigo, statut actif. Un véhicule avec historique se désactive, il ne se supprime pas.
- Import CSV ou Excel (`.xlsx`) : aperçu ligne par ligne avant import (`/api/admin/vehicules/import/apercu`), puis import des lignes valides. Séparateur `;` ou `,`, virgule décimale, encodage UTF-8 ou Windows. Colonnes reconnues : plaque, type, hauteur, largeur, longueur, PTAC, charge utile, essieux, palettes, kg, m3, ADR, frigo, actif.
- Planches de QR codes : `GET /api/admin/vehicules/qr.pdf` (6 par page, avec la plaque). L'adresse encodée vient de `APP_URL`.
- Conducteurs : code PIN à 4 chiffres, unique par société, montré une seule fois (en base : HMAC avec `PIN_SECRET`, à définir en production). Le chauffeur saisit son code sur la page du camion et reçoit un badge signé valable 12 h ; 5 essais ratés par camion et par 15 minutes bloquent la saisie. Sans réseau ou sans code, il peut saisir son nom.
- Mode hors ligne : un service worker garde la page et la checklist d'un camion déjà ouvert ; un contrôle fait sans réseau est mis en file sur le téléphone (IndexedDB, photos comprises) et envoyé au retour du réseau. Chaque envoi porte un identifiant (`client_id`) : le rejouer ne crée jamais de doublon. L'heure réelle du contrôle (`fait_le`) est conservée si elle est plausible (moins de 7 jours, pas dans le futur).
- Limite connue : le mode hors ligne suppose que le chauffeur a ouvert la page du camion au moins une fois avec du réseau.

## Commandes, géocodage, dépôts (étape 5)

- Une commande : référence, client, adresse, position, poids, volume, palettes, fenêtre de livraison, durée de service, contraintes (frigo, ADR, hayon), jour de livraison. La référence est unique par société et par jour.
- Import CSV ou Excel en trois temps : choix du fichier, association des colonnes (proposée automatiquement, **mémorisée par société**), aperçu ligne par ligne, import. Une ligne en erreur est ignorée et listée ; une commande déjà présente (même référence, même jour) est mise à jour.
- Géocodage par l'API Adresse (api-adresse.data.gouv.fr, service public gratuit) : un seul appel groupé par import, uniquement pour les adresses absentes du cache en base (`geocode_cache`). Score ≥ 0,75 : localisée ; entre 0,5 et 0,75 : à vérifier ; en dessous ou sans résultat : introuvable. Si le service est indisponible, l'import réussit et les commandes restent « en attente » (bouton « Géocoder les … en attente »). Variable `GEOCODER_URL` pour changer de serveur.
- Correction à la main : sélectionner la commande puis cliquer sur la carte.
- Dépôts : un par société au minimum (le dernier ne peut pas être supprimé), un seul dépôt par défaut, horaires d'ouverture.
- Hors périmètre de cette étape : la création d'une commande unique n'a pas d'écran (API `POST /api/admin/commandes` disponible).

## Optimisation de tournées (étape 7)

- `POST /api/admin/plans` crée un plan et le met en file (Celery) ; l'écran Planning interroge `GET /api/admin/plans/{id}` toutes les secondes (en attente, en cours avec pourcentage, terminé, échec).
- Données : commandes localisées du jour, camions actifs non bloqués avec gabarit complet (les autres sont listés comme exclus), dépôt par défaut. La matrice des temps vient de Valhalla, **une par profil de gabarit** (flotte mixte). Si Valhalla ne répond pas, le plan échoue avec un message clair : aucun temps de trajet n'est inventé.
- Contraintes : capacité en poids, volume et palettes, fenêtres horaires, durée de service, compatibilité frigo / ADR, horaires d'ouverture du dépôt (départ et retour), durée maximale de tournée (10 h par défaut).
- Commandes non affectées : listées avec la raison la plus probable (capacité, fenêtre horaire inaccessible, aucun véhicule compatible, adresse inaccessible, retour après la fermeture, durée maximale).
- Temps de calcul maximal : paramètre `temps_max_s` (10 s par défaut, 120 s au plus). Les petits problèmes s'arrêtent plus tôt.
- Mesure : 100 commandes et 8 camions (distances simulées) : plan complet en une dizaine de secondes.
- Limite connue : la contrainte « hayon » d'une commande n'est pas prise en compte (les véhicules n'ont pas encore de champ hayon).

## Interface de planification (étape 8)

- Écran Planning : indicateurs (distance, durée, remplissage, alertes, non affectées) **comparés au plan initial**, alertes détaillées, une section par camion avec frise horaire et liste d'arrêts, carte (ordre de passage à vol d'oiseau, pas l'itinéraire routier).
- Modification à la main : glisser-déposer d'un arrêt vers un autre camion, une autre position ou la zone « Non affectées » (ou menu « Déplacer… » au clavier). L'API recalcule les heures d'arrivée et les alertes avec les matrices conservées dans le plan, sans relancer l'optimisation ni rappeler Valhalla (quelques dizaines de millisecondes).
- Alertes recalculées : retard sur une fenêtre horaire, surcharge (poids, palettes, volume), durée maximale de tournée, retour après la fermeture du dépôt, incompatibilité frigo ou ADR. Elles n'empêchent pas la modification : c'est à l'exploitant d'arbitrer.
- Verrouillage d'un arrêt ou d'une tournée : un élément verrouillé ne se déplace plus et n'est pas touché par « Réoptimiser (hors verrouillés) ». Un arrêt verrouillé reste sur son camion mais peut changer de place dans la tournée.
- Annuler / rétablir : historique de toutes les modifications d'un plan. « Enregistrer une version » copie le plan courant sous un nom ; les versions du jour sont dans le sélecteur.
- Les routes des plans sont identifiées par véhicule et par commande (pas par identifiant de ligne) : les identifiants de lignes changent à chaque recalcul.

## Temps de conduite (étape 9)

Module isolé `api/app/regulations/` (règlement CE 561/2006), intégré à l'optimisation et au planning : pauses de 45 min insérées dans les tournées, plafonds de conduite et heure de départ par conducteur, historiques déclarés par conducteur, alertes d'infraction après une modification manuelle, temps de conduite restants par conducteur. Détail des règles, des choix et **des points à vérifier avec le texte officiel** : [docs/temps-de-conduite.md](docs/temps-de-conduite.md).

## Plan du chauffeur sur téléphone (étape 10)

- Publication : bouton « Publier aux chauffeurs » dans le planning. Chaque camion qui a des arrêts reçoit un **lien personnel** (`/t/<jeton>`), sans compte ; les liens sont copiables, envoyés par email aux conducteurs qui ont une adresse (si Brevo est configuré), et accessibles depuis le QR code du camion. Republier ne change pas les liens ; publier un autre plan le même jour rend les anciens liens caducs (message explicite). Pas d'envoi par SMS.
- **Le contrôle avant départ d'abord** : tant que le contrôle du jour n'est pas fait, ou si le camion est bloqué, la tournée est verrouillée côté serveur (aucun arrêt n'est communiqué, aucun statut n'est accepté) et la page renvoie vers le contrôle.
- Tournée : arrêts dans l'ordre avec heure prévue, client, adresse, contact (téléphone cliquable), consignes, bouton « Naviguer » (lien Google Maps vers l'adresse). Contact et consignes viennent de l'import ou de la fiche commande.
- Statuts par arrêt : arrivé, livré (nom du destinataire, signature, photo facultatifs) ou impossible (motif obligatoire, photo facultative), avec heure et position. Un arrêt clôturé ne change plus ; l'arrivée et le rejeu d'un envoi sont idempotents (`client_id`).
- **Hors ligne** : mêmes mécanismes que le contrôle (service worker, file IndexedDB avec photos, envoi au retour du réseau, heure réelle conservée). Les statuts saisis hors ligne s'affichent tout de suite sur le téléphone.
- Suivi : le planning affiche, par arrêt, le statut en direct, la signature et les photos, un retard (heure prévue dépassée de plus de 15 minutes et arrêt pas atteint) et un résumé (livrées, sur place, impossibles, en retard) ; il se rafraîchit toutes les 30 secondes.
- Les statuts sont dans un journal séparé du plan : modifier le plan après publication ne les efface pas, et une commande livrée ne redevient jamais « planifiée ».
- Limites : la position n'est enregistrée qu'à chaque changement de statut (pas de suivi GPS continu) ; le « retard » est celui par rapport à l'heure prévue, sans recalcul d'arrivée en fonction de la position (étape 11).

## Temps réel et replanification (étape 11)

- **Retards** : `GET /api/admin/plans/{id}/suivi` recalcule les heures d'arrivée des arrêts restants à partir de la dernière position connue et du statut des arrêts ; une fenêtre horaire manquée est signalée dans le planning.
- **Propositions** (`POST /plans/{id}/propositions`, types `retard`, `urgence`, `panne`) : 2 ou 3 solutions chiffrées (retards, retour au plus tard, kilomètres). Cet appel ne modifie rien ; seul `POST /plans/{id}/propositions/appliquer`, déclenché par un clic sur « Appliquer », change le plan, en une seule version annulable.
- **Trafic** : abstraction `app/trafic.py` (HERE, TomTom), **désactivée par défaut**. Elle ne s'active qu'avec `TRAFIC_ACTIF=true` et une clé fournisseur ; sans cela, les durées du plan sont utilisées. Les appels HERE/TomTom sont testés avec des réponses simulées et n'ont jamais été exécutés contre le vrai service : à vérifier avant activation.

## Offres et facturation (étape 12)

| | Essentiel | Pro |
|---|---|---|
| Prix par camion et par mois (HT) | 45 € | 75 € |
| Minimum mensuel (HT) | 500 € | 900 € |
| Utilisateurs exploitants | 2 | illimités |
| Temps de conduite (déclarations, compteurs), temps réel et replanification | non | oui |

- **Grille réglable sans code** : variable `OFFRES_JSON` (par exemple `{"pro": {"prix_eur": 80}}`), `REMISE_ANNUELLE_PCT` (10 par défaut, **valeur d'hypothèse à confirmer**) et `TVA_PCT` (20).
- **Verrouillage** : `app/offres.py` (`exige("temps_reel")`, `exige("conduite")`) refuse en 403 côté API ; l'interface masque les boutons et affiche un message Pro. Une société sans abonnement enregistré garde toutes les fonctions (sociétés antérieures à l'étape 12). Une société suspendue est bloquée côté exploitant ; les chauffeurs gardent leurs pages.
- **Back-office** : rôle `plateforme` (`PASSWORD=… python create_user.py EMAIL "Nom société" plateforme`), page `/admin/plateforme` : création de société, offre, camions facturés, statut (essai / actif / suspendu), MRR (abonnements actifs seulement), devis et factures PDF numérotés `DE-AAAA-NNNN` / `FA-AAAA-NNNN`. Le paiement se fait par virement.
- **Mentions légales** : l'identité du vendeur vient de `VENDEUR_NOM`, `VENDEUR_ADRESSE`, `VENDEUR_SIREN`, `VENDEUR_TVA`, `VENDEUR_IBAN` (des marqueurs « à renseigner » s'impriment sinon). Le texte des pénalités de retard et de l'indemnité de 40 € est à faire relire par un comptable avant la première facture réelle.
- Les fonctions `api` et `stats` de l'offre Pro n'ont pas encore de route à verrouiller (API publique : étape 13).

## API publique et webhooks (étape 13)

Offre Pro. Clés API et webhooks se gèrent dans **Réglages → Intégrations** (administrateurs). Documentation interactive : `/api/v1/docs` ; guide avec exemples curl et Python, vérification de signature : [docs/api-publique.md](docs/api-publique.md) ; script complet : `exemples/api_et_webhook.py`.

- Clés `flt_…` : affichées une fois, stockées hachées (sha256), révocables, dernière utilisation suivie ; 120 requêtes par minute et par clé (`API_LIMITE_PAR_MINUTE`).
- Webhooks `plan.publie`, `arret.livre`, `controle.defaut_critique`, signés `HMAC-SHA256(secret, "<t>." + corps)`, réessais à 1 min, 5 min, 30 min, 2 h, 12 h puis abandon. Adresses HTTPS publiques uniquement (contrôle à l'enregistrement et à l'envoi). Livraisons conservées en base ; la tâche Celery `relancer_webhooks_task` (toutes les minutes) reprend les envois dus.
- Limites connues : le compteur de débit est en mémoire (un seul worker API) ; la vérification d'adresse à l'envoi ne protège pas contre un DNS qui change entre la vérification et la connexion ; le secret du webhook est stocké en clair (nécessaire pour signer).

## Page d'accueil et « Mon offre »

`/` est la page d'accueil publique (contrôle départ, tournées, tarifs) ; les tarifs viennent de `GET /api/offres`, donc de la grille configurée, jamais recopiés en dur. Réglages → Mon offre montre l'offre de la société. Aucune référence client ni chiffre d'impact n'est affiché : il n'y en a pas encore.

## Production, sécurité et RGPD (étape 14)

Déploiement (Caddy en HTTPS, sauvegardes S3, restauration), supervision (`/api/health`, Sentry, UptimeRobot), procédure d'incident : [docs/exploitation.md](docs/exploitation.md). RGPD : [registre des traitements](docs/rgpd/registre-traitements.md) et [modèle de contrat de sous-traitance](docs/rgpd/contrat-sous-traitance.md), à faire relire par un juriste. Journal d'audit des actions sensibles (déblocage, suppressions, clés API, changement d'offre) ; export et effacement par conducteur ; la purge automatique couvre aussi les événements de livraison, les activités de conduite et l'historique des webhooks (90 jours). En-têtes de sécurité (API et front), limite de débit par adresse (600 requêtes par minute, pages chauffeur exemptées), page d'état publique `/statut`, audit des dépendances dans la CI (`pip-audit`, `npm audit`).

## Prise en main pour les pilotes (étape 15)

- **Démarrer** (`/admin/demarrer`) : six étapes (flotte, conducteurs, checklists, QR codes, commandes d'essai, premier contrôle) avec ce qui est déjà fait, lu en base (`GET /api/admin/demarrage`).
- **Données de démonstration** en un clic (administrateur) : 15 camions `DM-…`, 15 conducteurs « Démo n », un dépôt et 80 commandes `DEMO-…` du jour, déjà localisées autour de Nantes (aucun appel externe). `DELETE /api/admin/demo` retire uniquement ces données et ce qui s'y rattache.
- **Aide** : infobulles `?` sur le planning, les conducteurs et les commandes ; guides d'une page par module en PDF (`/aide/*.pdf`), générés depuis `docs/client/*.md` par `scripts/guides_pdf.py`.
- **Signaler un problème** (pied de page de l'espace exploitant) : message enregistré avec la page, la société, la version (`APP_VERSION`) et le navigateur ; lisible par la plateforme (`GET /api/plateforme/signalements`) ; envoyé par email à `SUPPORT_EMAIL` si Brevo est configuré.
- Non mesuré : le critère « opérationnel en moins de 30 minutes » demande un essai avec une vraie société vierge.
