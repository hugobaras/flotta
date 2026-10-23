import logging
import os
from datetime import datetime, timedelta, timezone

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from . import notifications
from .db import SessionLocal
from .exploitation import sans_controle, today_paris
from .models import Alert, Company
from .notifications import process_alert
from .retention import purge

log = logging.getLogger(__name__)

celery = Celery("transport", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
celery.conf.update(
    timezone="Europe/Paris",
    broker_connection_timeout=2,  # Redis absent : l'API ne doit pas rester bloquée
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "purge-nocturne": {"task": "app.worker.daily_purge", "schedule": crontab(hour=3, minute=0)},
        "rappels": {"task": "app.worker.send_reminders_task", "schedule": 300.0},
        "alertes-oubliees": {"task": "app.worker.requeue_unsent_alerts_task", "schedule": 300.0},
    },
)

RETRY_DELAYS = [60, 300, 900, 3600]  # réessais espacés : 1, 5, 15, 60 min


@celery.task(bind=True, max_retries=len(RETRY_DELAYS))
def send_critical_alert(self, alert_id: int):
    with SessionLocal() as db:
        last = self.request.retries >= len(RETRY_DELAYS)
        if not process_alert(db, alert_id, last):
            raise self.retry(countdown=RETRY_DELAYS[self.request.retries])


def send_reminders(db, now: datetime | None = None) -> int:
    """Email « camions sans contrôle », une fois par jour et par société, après l'heure de rappel."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    for company in db.scalars(select(Company)):
        today = today_paris(now)
        if company.rappel_envoye_le == today or not company.alert_emails or not notifications.brevo_configured():
            continue
        vehicles = sans_controle(db, company, now)
        if not vehicles:
            continue
        try:
            notifications.send_email(
                company.alert_emails, f"{len(vehicles)} camion(s) sans contrôle avant départ",
                "<p>Camions sans contrôle à ce jour :</p><ul>"
                + "".join(f"<li>{notifications.escape(v.plaque)}</li>" for v in vehicles) + "</ul>")
        except Exception:
            log.exception("Rappel société %s : échec, nouvel essai au prochain passage", company.id)
            continue
        company.rappel_envoye_le = today  # marqué seulement après un envoi réussi
        db.commit()
        sent += 1
    return sent


def requeue_unsent_alerts(db, now: datetime | None = None) -> int:
    """Relance les alertes jamais tentées (Redis était indisponible à l'envoi du contrôle)."""
    now = now or datetime.now(timezone.utc)
    ids = list(db.scalars(select(Alert.id).where(
        Alert.statut == "en_attente", Alert.tentatives == 0, Alert.created_at < now - timedelta(minutes=5))))
    for alert_id in ids:
        send_critical_alert.apply_async(args=[alert_id], retry=False)
    return len(ids)


@celery.task
def requeue_unsent_alerts_task():
    with SessionLocal() as db:
        return requeue_unsent_alerts(db)


@celery.task
def send_reminders_task():
    with SessionLocal() as db:
        return send_reminders(db)


@celery.task
def calculer_plan(plan_id: int):
    """Optimisation d'un plan de tournées en tâche de fond (jamais dans la requête web)."""
    from . import plans
    with SessionLocal() as db:
        plans.executer(db, plan_id)


@celery.task
def daily_purge():
    with SessionLocal() as db:
        return purge(db)
