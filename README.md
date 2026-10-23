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
