from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import photos
from .models import Check, CheckPhoto, Company


def purge(db: Session, now: datetime | None = None) -> int:
    """Supprime contrôles, photos et positions plus vieux que la durée de conservation de chaque société."""
    now = now or datetime.now(timezone.utc)
    total = 0
    for company in db.scalars(select(Company)):
        limit = now - timedelta(days=company.retention_jours)
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
