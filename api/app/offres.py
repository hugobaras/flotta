"""Offres Essentiel / Pro : grille tarifaire, fonctions incluses et calcul des montants.

La grille se règle sans toucher au code : OFFRES_JSON (fusionné sur les valeurs par défaut),
REMISE_ANNUELLE_PCT et TVA_PCT. Les montants sont en centimes pour éviter les erreurs d'arrondi."""
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import Subscription, User

PRO = ["conduite", "temps_reel", "api", "stats"]
DEFAUT = {
    "essentiel": {"nom": "Essentiel", "prix_eur": 45, "minimum_eur": 500, "utilisateurs": 2, "fonctions": [],
                  "inclus": ["Contrôle avant départ sur téléphone (QR code, sans application)", "Alertes et blocage du camion sur défaut critique",
                             "Routage poids lourd et optimisation des tournées", "Plan du chauffeur sur téléphone, suivi en direct", "2 utilisateurs exploitants"]},
    "pro": {"nom": "Pro", "prix_eur": 75, "minimum_eur": 900, "utilisateurs": None, "fonctions": PRO,
            "inclus": ["Tout ce qui est dans l'offre Essentiel", "Temps de conduite légal (CE 561/2006) intégré aux tournées", "Temps réel : retards prévus et replanification validée par vous",
                       "API publique et webhooks signés", "Utilisateurs exploitants illimités"]},
}


def grille() -> dict:
    g = {k: dict(v) for k, v in DEFAUT.items()}
    for k, v in json.loads(os.getenv("OFFRES_JSON") or "{}").items():
        g.setdefault(k, {}).update(v)
    return g


def remise_annuelle_pct() -> float:
    return float(os.getenv("REMISE_ANNUELLE_PCT", "10"))


def tva_pct() -> float:
    return float(os.getenv("TVA_PCT", "20"))


def calculer(offre: str, camions: int, periode: str, remise_pct: float, tva: float) -> dict:
    """Montants d'une période : mensuel = 1 mois, annuel = 12 mois avec remise de paiement annuel."""
    o = grille()[offre]
    mensuel = max(camions * round(o["prix_eur"] * 100), round(o["minimum_eur"] * 100))
    mois = 12 if periode == "annuel" else 1
    brut = mensuel * mois
    remise = round(brut * remise_pct / 100) if periode == "annuel" else 0
    ht = brut - remise
    tva_c = round(ht * tva / 100)
    return {"mensuel_ht": mensuel, "mois": mois, "brut_ht": brut, "remise": remise, "ht": ht, "tva": tva_c, "ttc": ht + tva_c}


def abonnement(db: Session, company_id: int) -> Subscription | None:
    return db.scalar(select(Subscription).where(Subscription.company_id == company_id))


def fonctions(db: Session, company_id: int) -> list[str]:
    """Sans abonnement enregistré (société créée avant l'étape 12), toutes les fonctions restent disponibles."""
    s = abonnement(db, company_id)
    return PRO if s is None else grille()[s.offre]["fonctions"]


def exige(fonction: str):
    """Dépendance FastAPI : refuse (403) si l'offre de la société n'inclut pas la fonction."""
    def verifier(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if user.role != "plateforme" and fonction not in fonctions(db, user.company_id):
            raise HTTPException(403, "Cette fonction est incluse dans l'offre Pro.")
        return user
    return verifier


def place_utilisateur(db: Session, company_id: int) -> bool:
    """Vrai si la société peut encore avoir un exploitant de plus (2 en Essentiel, illimité en Pro)."""
    s = abonnement(db, company_id)
    limite = grille()[s.offre]["utilisateurs"] if s else None
    nb = db.scalar(select(func.count()).select_from(User).where(User.company_id == company_id, User.role != "plateforme"))
    return limite is None or nb < limite


router = APIRouter(prefix="/api")


@router.get("/offres")
def offres_publiques():
    """Grille tarifaire publique (page d'accueil, « Mon offre »). Prix HT, par camion et par mois."""
    return {"offres": [{"id": k, "nom": v["nom"], "prix_eur": v["prix_eur"], "minimum_eur": v["minimum_eur"], "inclus": v.get("inclus", [])}
                       for k, v in grille().items()],
            "remise_annuelle_pct": remise_annuelle_pct()}
