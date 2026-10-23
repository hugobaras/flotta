from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import photos
from .models import ActiviteConducteur, Check, CheckPhoto, Company, LivraisonEvenement, LivraisonPhoto, WebhookLivraison


def _purger_livraisons(db: Session, company_id: int, limit: datetime) -> int:
    """Événements de livraison (positions, signatures, noms de destinataires) et leurs photos."""
    ids = list(db.scalars(select(LivraisonEvenement.id).where(LivraisonEvenement.company_id == company_id, LivraisonEvenement.fait_le < limit)))
    if not ids:
        return 0
    for p in db.scalars(select(LivraisonPhoto).where(LivraisonPhoto.evenement_id.in_(ids))):
        photos.path(company_id, p.fichier).unlink(missing_ok=True)
    db.execute(delete(LivraisonPhoto).where(LivraisonPhoto.evenement_id.in_(ids)))
    db.execute(delete(LivraisonEvenement).where(LivraisonEvenement.id.in_(ids)))
    return len(ids)


def purge(db: Session, now: datetime | None = None) -> int:
    """Supprime contrôles, photos et positions plus vieux que la durée de conservation de chaque société."""
    now = now or datetime.now(timezone.utc)
    total = 0
    for company in db.scalars(select(Company)):
        limit = now - timedelta(days=company.retention_jours)
        total += _purger_livraisons(db, company.id, limit)
        db.execute(delete(ActiviteConducteur).where(ActiviteConducteur.company_id == company.id, ActiviteConducteur.fin < limit))
        db.execute(delete(WebhookLivraison).where(WebhookLivraison.company_id == company.id, WebhookLivraison.cree_le < now - timedelta(days=90)))
        old = list(db.scalars(select(Check.id).where(Check.company_id == company.id, Check.created_at < limit)))
        if not old:
            continue
        for p in db.scalars(select(CheckPhoto).where(CheckPhoto.check_id.in_(old))):
            photos.path(company.id, p.fichier).unlink(missing_ok=True)
        db.execute(delete(CheckPhoto).where(CheckPhoto.check_id.in_(old)))
        db.execute(delete(Check).where(Check.id.in_(old)))
        total += len(old)
    db.commit()
    return total
