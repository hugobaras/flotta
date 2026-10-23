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
