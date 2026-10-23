"""Codes PIN des conducteurs et badge signé remis après identification (jamais de PIN en clair en base)."""
import hashlib
import hmac
import os
import secrets
import time

BADGE_DUREE = 12 * 3600  # un badge vaut une journée de travail


def _secret() -> bytes:
    # Variable d'environnement en production ; la valeur par défaut ne sert qu'au développement.
    return os.getenv("PIN_SECRET", "dev-pin-secret-a-changer").encode()


def hash_pin(company_id: int, pin: str) -> str:
    return hmac.new(_secret(), f"{company_id}:{pin}".encode(), hashlib.sha256).hexdigest()


def nouveau_pin() -> str:
    return f"{secrets.randbelow(9000) + 1000}"


def signer_badge(driver_id: int, company_id: int, maintenant: float | None = None) -> tuple[str, int]:
    expire = int((maintenant or time.time()) + BADGE_DUREE)
    msg = f"{driver_id}.{company_id}.{expire}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{msg}.{sig}", expire


def lire_badge(badge: str, company_id: int, maintenant: float | None = None) -> int | None:
    """Renvoie l'identifiant du conducteur si le badge est authentique, de cette société et non expiré."""
    try:
        driver_id, comp, expire, sig = badge.split(".")
        attendu = hmac.new(_secret(), f"{driver_id}.{comp}.{expire}".encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, attendu) or int(comp) != company_id or int(expire) < (maintenant or time.time()):
            return None
        return int(driver_id)
    except (ValueError, AttributeError):
        return None
