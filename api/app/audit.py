"""Journal d'audit : `journaliser` ajoute la ligne dans la transaction de l'action (validée avec elle)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import AuditLog, User

router = APIRouter(prefix="/api/admin")


def journaliser(db: Session, user: User, action: str, cible: str = "", company_id: int | None = None) -> None:
    db.add(AuditLog(company_id=company_id if company_id is not None else user.company_id, user_email=user.email, action=action, cible=cible[:200]))


@router.get("/audit")
def lire(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("admin", "plateforme"):
        raise HTTPException(403, "Réservé aux administrateurs")
    rows = db.scalars(select(AuditLog).where(AuditLog.company_id == user.company_id).order_by(AuditLog.id.desc()).limit(200))
    return [{"id": a.id, "par": a.user_email, "action": a.action, "cible": a.cible, "date": a.cree_le} for a in rows]
