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
