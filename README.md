# Transport SaaS

Squelette du module « contrôle avant départ ». Contexte et étapes : `claude.md`.

- API : `cd api && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pytest`
- Front : `cd web && npm install && npm run build`
- Tout : `docker compose up -d --build` puis http://localhost:3000/c/demo

Base : tables créées au démarrage (`create_all`), remplacé par Alembic à l'étape 1.
Routes exploitant : en-tête `X-API-Key` (clé de démo `DEMO_API_KEY`, défaut `dev-demo-key`), provisoire jusqu'à l'étape 1.
