import logging
import os
from datetime import timezone
from html import escape
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from .models import Alert, Check, Company, Vehicle

log = logging.getLogger(__name__)
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
PARIS = ZoneInfo("Europe/Paris")


def brevo_configured() -> bool:
    return bool(os.getenv("BREVO_API_KEY") and os.getenv("BREVO_SENDER"))


def send_email(to: list[str], subject: str, html: str) -> None:
    """Envoie un email par l'API Brevo ; lève une exception si l'envoi échoue."""
    r = httpx.post(
        BREVO_URL,
        headers={"api-key": os.environ["BREVO_API_KEY"], "accept": "application/json"},
        json={"sender": {"email": os.environ["BREVO_SENDER"]}, "to": [{"email": e} for e in to],
              "subject": subject, "htmlContent": html},
        timeout=10,
    )
    r.raise_for_status()


def _alert_html(company: Company, check: Check, vehicle: Vehicle) -> str:
    when = check.created_at
    when = (when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when).astimezone(PARIS)
    ko = "".join(f"<li>{escape(r['libelle'])}{' : ' + escape(r['commentaire']) if r['commentaire'] else ''}</li>"
                 for r in check.reponses if not r["ok"] and r["critique"])
    link = os.getenv("APP_URL", "").rstrip("/")
    detail = f'<p><a href="{escape(link)}/admin/controles/{check.id}">Voir le contrôle</a></p>' if link else ""
    return (f"<p>Défaut critique sur <b>{escape(vehicle.plaque)}</b> ({escape(company.nom)}), contrôle de "
            f"{escape(check.conducteur)} le {when:%d/%m/%Y à %H:%M}. Le véhicule est bloqué.</p><ul>{ko}</ul>{detail}")


def process_alert(db: Session, alert_id: int, last_attempt: bool) -> bool:
    """Envoie l'alerte. Renvoie True si le traitement est terminé, False s'il faut réessayer."""
    alert = db.get(Alert, alert_id)
    if not alert or alert.statut in ("envoye", "echec", "non_configure", "sans_destinataire"):
        return True  # déjà traitée : une tâche rejouée n'envoie pas deux emails
    company = db.get(Company, alert.company_id)
    check = db.get(Check, alert.check_id)
    vehicle = db.get(Vehicle, check.vehicle_id)
    if not company.alert_emails:
        alert.statut = "sans_destinataire"
    elif not brevo_configured():
        log.warning("Brevo non configuré : alerte %s non envoyée", alert.id)
        alert.statut = "non_configure"
    else:
        try:
            send_email(company.alert_emails, f"Défaut critique : {vehicle.plaque}", _alert_html(company, check, vehicle))
            alert.statut = "envoye"
        except Exception as e:  # réseau, 4xx/5xx Brevo : on réessaie, puis on abandonne
            alert.tentatives += 1
            alert.erreur = f"{type(e).__name__}: {e}"[:500]
            alert.statut = "echec" if last_attempt else "en_attente"
            log.warning("Alerte %s : échec d'envoi (tentative %s)", alert.id, alert.tentatives)
            db.commit()
            return last_attempt
    db.commit()
    return True
