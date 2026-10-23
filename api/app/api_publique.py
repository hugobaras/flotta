"""API publique (clé API, offre Pro) et gestion des clés et webhooks par les administrateurs."""
import hashlib
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import commandes, offres, plans_api, webhooks
from .auth import current_user
from .db import get_db
from .models import ApiKey, Check, Order, Subscription, User, Vehicle, Webhook, WebhookLivraison
import os

LIMITE_PAR_MINUTE = int(os.getenv("API_LIMITE_PAR_MINUTE", "120"))
# shortcut: fenêtre glissante en mémoire, valable pour un seul worker ; passer sur Redis avec plusieurs workers.
_appels: dict[int, list[float]] = {}

bearer = HTTPBearer(auto_error=False, description="Clé API créée dans l'espace exploitant (flt_…)")
public = APIRouter(prefix="/api/v1", tags=["API publique"])
admin = APIRouter(prefix="/api/admin/integrations")


def digest(cle: str) -> str:
    return hashlib.sha256(cle.encode()).hexdigest()


def cle_api(auth: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not auth:
        raise HTTPException(401, "Clé API manquante", headers={"WWW-Authenticate": "Bearer"})
    k = db.scalar(select(ApiKey).where(ApiKey.hash == digest(auth.credentials), ApiKey.revoquee_le.is_(None)))
    if not k:
        raise HTTPException(401, "Clé API invalide ou révoquée", headers={"WWW-Authenticate": "Bearer"})
    if "api" not in offres.fonctions(db, k.company_id):
        raise HTTPException(403, "L'API est incluse dans l'offre Pro.")
    sub = offres.abonnement(db, k.company_id)
    if sub and sub.statut == "suspendu":
        raise HTTPException(403, "Compte suspendu")
    now = time.monotonic()
    recents = [t for t in _appels.get(k.id, []) if now - t < 60]
    if len(recents) >= LIMITE_PAR_MINUTE:
        _appels[k.id] = recents
        raise HTTPException(429, "Trop de requêtes", headers={"Retry-After": str(int(60 - (now - recents[0])) + 1)})
    recents.append(now)
    _appels[k.id] = recents
    maintenant = datetime.now(timezone.utc)
    if k.derniere_utilisation is None or maintenant - k.derniere_utilisation.replace(tzinfo=timezone.utc) > timedelta(minutes=1):
        k.derniere_utilisation = maintenant
        db.commit()
    return SimpleNamespace(company_id=k.company_id)  # même forme que l'utilisateur attendu par les fonctions réutilisées


# --- Ressources publiques (les fonctions métier sont celles de l'espace exploitant) ---

@public.get("/commandes", summary="Lister les commandes")
def lister_commandes(date_: date | None = Query(default=None, alias="date"), q: str | None = None,
                     ctx=Depends(cle_api), db: Session = Depends(get_db)):
    return commandes.lister(date_, None, q, ctx, db)


@public.post("/commandes", status_code=201, summary="Créer une commande (géocodée automatiquement)")
def creer_commande(body: commandes.CommandeIn, ctx=Depends(cle_api), db: Session = Depends(get_db)):
    return commandes.creer(body, ctx, db)


@public.get("/commandes/{order_id}", summary="Lire une commande")
def lire_commande(order_id: int, ctx=Depends(cle_api), db: Session = Depends(get_db)):
    return commandes.sortie(commandes._commande(db, ctx, order_id))


@public.patch("/commandes/{order_id}", summary="Modifier une commande")
def modifier_commande(order_id: int, body: commandes.CommandePatch, ctx=Depends(cle_api), db: Session = Depends(get_db)):
    return commandes.modifier(order_id, body, ctx, db)


@public.get("/plans", summary="Lister les plans de tournées")
def lister_plans(ctx=Depends(cle_api), db: Session = Depends(get_db)):
    return plans_api.lister(ctx, db)


@public.get("/plans/{plan_id}", summary="Lire un plan : tournées, arrêts, heures prévues, avancement")
def lire_plan(plan_id: int, ctx=Depends(cle_api), db: Session = Depends(get_db)):
    return plans_api.lire(plan_id, ctx, db)


@public.get("/controles", summary="Lister les contrôles avant départ d'un jour")
def lister_controles(date_: date = Query(alias="date"), ctx=Depends(cle_api), db: Session = Depends(get_db)):
    debut = datetime.combine(date_, datetime.min.time(), tzinfo=timezone.utc) - timedelta(hours=2)
    rows = db.execute(select(Check, Vehicle.plaque).join(Vehicle, Vehicle.id == Check.vehicle_id).where(
        Check.company_id == ctx.company_id, Check.created_at >= debut, Check.created_at < debut + timedelta(hours=28)
    ).order_by(Check.created_at))
    return [{"id": c.id, "plaque": plaque, "conducteur": c.conducteur, "date": c.created_at, "defaut": c.has_defaut,
             "defaut_critique": c.defaut_critique} for c, plaque in rows]


def schema_public(app):
    """OpenAPI limité à l'API publique (l'API interne de l'interface n'est pas un contrat)."""
    return get_openapi(title="Flotta : API publique", version="1.0", routes=public.routes,
                       description="Authentification : en-tête `Authorization: Bearer flt_…`. Offre Pro. Limite : 120 requêtes par minute et par clé.")


def installer_docs(app):
    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def openapi_public():
        return schema_public(app)

    @app.get("/api/v1/docs", include_in_schema=False)
    def docs_public():
        return get_swagger_ui_html(openapi_url="/api/v1/openapi.json", title="Flotta : API publique")


# --- Clés et webhooks (administrateurs, offre Pro) ---

def admin_api(user: User = Depends(offres.exige("api"))) -> User:
    if user.role not in ("admin", "plateforme"):
        raise HTTPException(403, "Réservé aux administrateurs")
    return user


class CleIn(BaseModel):
    nom: str = Field(min_length=1, max_length=100)


@admin.get("/cles")
def lister_cles(user: User = Depends(admin_api), db: Session = Depends(get_db)):
    return [{"id": k.id, "nom": k.nom, "apercu": k.apercu, "cree_le": k.cree_le, "derniere_utilisation": k.derniere_utilisation,
             "revoquee": k.revoquee_le is not None} for k in db.scalars(select(ApiKey).where(ApiKey.company_id == user.company_id).order_by(ApiKey.id))]


@admin.post("/cles", status_code=201)
def creer_cle(body: CleIn, user: User = Depends(admin_api), db: Session = Depends(get_db)):
    cle = "flt_" + secrets.token_urlsafe(32)
    k = ApiKey(company_id=user.company_id, nom=body.nom, apercu=cle[:10], hash=digest(cle))
    db.add(k)
    db.commit()
    return {"id": k.id, "nom": k.nom, "apercu": k.apercu, "cle": cle, "avertissement": "Copiez cette clé maintenant : elle ne sera plus affichée."}


@admin.delete("/cles/{cle_id}", status_code=204)
def revoquer_cle(cle_id: int, user: User = Depends(admin_api), db: Session = Depends(get_db)):
    k = db.scalar(select(ApiKey).where(ApiKey.id == cle_id, ApiKey.company_id == user.company_id))
    if not k:
        raise HTTPException(404, "Clé inconnue")
    k.revoquee_le = k.revoquee_le or datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


class WebhookIn(BaseModel):
    url: str = Field(max_length=500)
    evenements: list[str] = Field(min_length=1)


def _sortie_webhook(w: Webhook) -> dict:
    return {"id": w.id, "url": w.url, "evenements": w.evenements, "actif": w.actif}


@admin.get("/webhooks")
def lister_webhooks(user: User = Depends(admin_api), db: Session = Depends(get_db)):
    return {"evenements_disponibles": sorted(webhooks.EVENEMENTS),
            "webhooks": [_sortie_webhook(w) for w in db.scalars(select(Webhook).where(Webhook.company_id == user.company_id).order_by(Webhook.id))]}


@admin.post("/webhooks", status_code=201)
def creer_webhook(body: WebhookIn, user: User = Depends(admin_api), db: Session = Depends(get_db)):
    inconnus = set(body.evenements) - webhooks.EVENEMENTS
    if inconnus:
        raise HTTPException(422, f"Événement inconnu : {', '.join(sorted(inconnus))}")
    refus = webhooks.url_sure(body.url)
    if refus:
        raise HTTPException(422, refus)
    w = Webhook(company_id=user.company_id, url=body.url, secret="whsec_" + secrets.token_urlsafe(24), evenements=sorted(set(body.evenements)))
    db.add(w)
    db.commit()
    return {**_sortie_webhook(w), "secret": w.secret, "avertissement": "Copiez ce secret maintenant : il ne sera plus affiché."}


@admin.delete("/webhooks/{webhook_id}", status_code=204)
def supprimer_webhook(webhook_id: int, user: User = Depends(admin_api), db: Session = Depends(get_db)):
    w = db.scalar(select(Webhook).where(Webhook.id == webhook_id, Webhook.company_id == user.company_id))
    if not w:
        raise HTTPException(404, "Webhook inconnu")
    w.actif = False  # les livraisons passées restent consultables
    db.commit()
    return Response(status_code=204)


@admin.get("/webhooks/{webhook_id}/livraisons")
def livraisons_webhook(webhook_id: int, user: User = Depends(admin_api), db: Session = Depends(get_db)):
    rows = db.scalars(select(WebhookLivraison).where(WebhookLivraison.webhook_id == webhook_id, WebhookLivraison.company_id == user.company_id)
                      .order_by(WebhookLivraison.id.desc()).limit(50))
    return [{"id": l.id, "evenement": l.evenement, "statut": l.statut, "tentatives": l.tentatives, "derniere_erreur": l.derniere_erreur,
             "prochaine_tentative": l.prochaine_tentative, "cree_le": l.cree_le} for l in rows]
