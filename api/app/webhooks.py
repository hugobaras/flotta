"""Webhooks sortants signés (HMAC-SHA256) avec réessais à délai croissant.

Un événement crée une ligne `WebhookLivraison` en base (jamais perdue), puis une première tentative part en tâche de fond ;
la tâche périodique `relancer_dus` reprend ce qui est dû (Redis indisponible, échec précédent). Le corps est signé avec
`t.corps` : le receveur vérifie la signature et la fraîcheur de `t` pour rejeter un rejeu."""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import offres
from .models import Webhook, WebhookLivraison

log = logging.getLogger(__name__)

EVENEMENTS = {"plan.publie", "arret.livre", "controle.defaut_critique"}
DELAIS = [60, 300, 1800, 7200, 43200]  # après l'échec n° k, prochain essai dans DELAIS[k-1] ; au-delà : abandon (6 essais)
RESERVATION = timedelta(minutes=5)
TOLERANCE_S = 300


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def url_sure(url: str) -> str | None:
    """None si l'adresse est acceptable, sinon la raison du refus (HTTPS public uniquement, contre le SSRF)."""
    p = urlparse(url)
    local = os.getenv("WEBHOOKS_AUTORISER_LOCAL") == "1"  # développement uniquement
    if p.scheme != "https" and not (local and p.scheme == "http"):
        return "L'adresse doit commencer par https://"
    if not p.hostname or p.username or p.password:
        return "Adresse invalide"
    try:
        adresses = {a[4][0] for a in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except OSError:
        return "Adresse introuvable"
    if not local and not all(ipaddress.ip_address(a).is_global for a in adresses):
        return "Adresse non publique refusée"
    return None


def signer(secret: str, corps: bytes, t: int) -> str:
    return f"t={t},v1=" + hmac.new(secret.encode(), f"{t}.".encode() + corps, hashlib.sha256).hexdigest()


def verifier(secret: str, entete: str, corps: bytes, maintenant_s: float | None = None) -> bool:
    """Côté receveur : signature valide et horodatage récent (5 min)."""
    try:
        parts = dict(x.split("=", 1) for x in entete.split(","))
        t = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((maintenant_s if maintenant_s is not None else time.time()) - t) > TOLERANCE_S:
        return False
    return hmac.compare_digest(signer(secret, corps, t), entete)


def declencher(db: Session, company_id: int, evenement: str, data: dict) -> None:
    """Met l'événement en file pour chaque webhook abonné. Ne lève jamais : un webhook ne doit pas casser l'action métier."""
    try:
        if "api" not in offres.fonctions(db, company_id):
            return
        ids = []
        for w in db.scalars(select(Webhook).where(Webhook.company_id == company_id, Webhook.actif.is_(True))):
            if evenement in w.evenements:
                l = WebhookLivraison(company_id=company_id, webhook_id=w.id, evenement=evenement, prochaine_tentative=maintenant(),
                                     payload={"id": str(uuid.uuid4()), "evenement": evenement, "cree_le": maintenant().isoformat(), "data": data})
                db.add(l)
                db.flush()
                ids.append(l.id)
        db.commit()
        from .worker import envoyer_webhook_task
        for i in ids:
            try:
                envoyer_webhook_task.apply_async(args=[i], retry=False)
            except Exception:  # Redis indisponible : la tâche périodique reprendra
                log.warning("Webhook %s non mis en file", i)
    except Exception:
        db.rollback()
        log.exception("Webhook %s non déclenché", evenement)


def envoyer(db: Session, livraison_id: int, now: datetime | None = None) -> str:
    """Une tentative d'envoi. Retourne le statut final de la ligne (ok / en_attente / echec / ignore)."""
    now = now or maintenant()
    # Réservation atomique : deux workers (ou la tâche immédiate et la tâche périodique) n'envoient pas deux fois.
    pris = db.execute(update(WebhookLivraison).where(
        WebhookLivraison.id == livraison_id, WebhookLivraison.statut == "en_attente", WebhookLivraison.prochaine_tentative <= now
    ).values(prochaine_tentative=now + RESERVATION), execution_options={"synchronize_session": False}).rowcount
    db.commit()
    if not pris:
        return "ignore"
    l = db.get(WebhookLivraison, livraison_id)
    w = db.get(Webhook, l.webhook_id)
    erreur = None
    if not w.actif:
        l.statut = "echec"
        erreur = "Webhook désactivé"
    else:
        refus = url_sure(w.url)
        corps = json.dumps(l.payload, separators=(",", ":"), sort_keys=True).encode()
        if refus:
            erreur = refus
        else:
            try:
                r = httpx.post(w.url, content=corps, timeout=10, follow_redirects=False, headers={
                    "Content-Type": "application/json", "X-Flotta-Evenement": l.evenement, "X-Flotta-Livraison": str(l.id),
                    "X-Flotta-Signature": signer(w.secret, corps, int(now.timestamp()))})
                if not 200 <= r.status_code < 300:
                    erreur = f"Réponse HTTP {r.status_code}"
            except httpx.HTTPError as e:
                erreur = f"{type(e).__name__}"[:300]
    l.tentatives += 1
    l.derniere_erreur = erreur
    if erreur is None:
        l.statut = "ok"
    elif l.statut != "echec":
        if l.tentatives > len(DELAIS):
            l.statut = "echec"
        else:
            l.prochaine_tentative = now + timedelta(seconds=DELAIS[l.tentatives - 1])
    db.commit()
    return l.statut


def relancer_dus(db: Session, now: datetime | None = None) -> int:
    now = now or maintenant()
    ids = list(db.scalars(select(WebhookLivraison.id).where(WebhookLivraison.statut == "en_attente", WebhookLivraison.prochaine_tentative <= now)
                          .order_by(WebhookLivraison.id).limit(100)))
    for i in ids:
        envoyer(db, i, now)
    return len(ids)
