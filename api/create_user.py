"""Crée une société (si besoin) et un compte : python create_user.py EMAIL "Nom société" [admin|exploitant]
Le mot de passe est lu sur l'entrée (variable PASSWORD ou invite), jamais en argument."""
import getpass
import os
import sys

from sqlalchemy import select

from app.auth import hasher
from app.db import SessionLocal
from app.models import Company, User

email, nom = sys.argv[1].strip().lower(), sys.argv[2]
role = sys.argv[3] if len(sys.argv) > 3 else "exploitant"
password = os.getenv("PASSWORD") or getpass.getpass("Mot de passe : ")
if len(password) < 10:
    sys.exit("Mot de passe trop court (10 caractères minimum)")

with SessionLocal() as db:
    company = db.scalar(select(Company).where(Company.nom == nom)) or Company(nom=nom)
    db.add(company)
    db.flush()
    db.add(User(company_id=company.id, email=email, password_hash=hasher.hash(password), role=role))
    db.commit()
print(f"Compte {email} créé pour {nom}")
