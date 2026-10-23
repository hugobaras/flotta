"""Pont entre la base de données et le module `regulations` (qui reste pur et ignore dates et base)."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import regulations as reg
from .models import ActiviteConducteur

PARIS = ZoneInfo("Europe/Paris")
LUNDI_REFERENCE = date(2001, 1, 1)  # un lundi : les minutes de `regulations` partent de son minuit
FENETRE_HISTORIQUE = timedelta(days=15)  # assez pour la semaine précédente et celle en cours


def minutes(dt: datetime) -> float:
    """Instant -> minutes depuis le lundi de référence, à l'heure de Paris (semaine civile locale)."""
    local = (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone(PARIS).replace(tzinfo=None)
    return (local - datetime.combine(LUNDI_REFERENCE, datetime.min.time())).total_seconds() / 60


def minuit(jour: date) -> float:
    """Minutes (échelle de `regulations`) du début de `jour`."""
    return (jour - LUNDI_REFERENCE).days * 1440.0


def instant(m: float) -> datetime:
    local = datetime.combine(LUNDI_REFERENCE, datetime.min.time()) + timedelta(minutes=m)
    return local.replace(tzinfo=PARIS).astimezone(timezone.utc)


def historique(db: Session, conducteur_id: int, jusqu_a: float) -> list[reg.Activite]:
    """Activités déclarées d'un conducteur dans les 15 jours qui précèdent `jusqu_a` (minutes)."""
    fin = instant(jusqu_a)
    rows = db.scalars(select(ActiviteConducteur).where(
        ActiviteConducteur.conducteur_id == conducteur_id, ActiviteConducteur.debut < fin,
        ActiviteConducteur.fin > fin - FENETRE_HISTORIQUE).order_by(ActiviteConducteur.debut))
    return [reg.Activite(a.type, minutes(a.debut), minutes(a.fin)) for a in rows]


def compteurs(db: Session, conducteur_id: int, jour: date, ouverture_min: int) -> reg.Restant:
    """Ce que le conducteur peut encore faire quand il prend son service à l'ouverture du dépôt le `jour` donné."""
    t = minuit(jour) + ouverture_min
    return reg.restant(historique(db, conducteur_id, t), t)
