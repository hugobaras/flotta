"""Purge RGPD : python purge.py (à lancer chaque jour ; sera planifié par Celery à l'étape 3B)."""
from app.db import SessionLocal
from app.retention import purge

with SessionLocal() as db:
    print(f"{purge(db)} contrôle(s) supprimé(s)")
