from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ChecklistItem, ChecklistTemplate

# Modèle par défaut, copié dans chaque nouvelle société.
DEFAULT_ITEMS = [
    ("Pneus : état et pression", True),
    ("Freins : pédale ferme, pas de bruit anormal", True),
    ("Feux et signalisation", True),
    ("Niveaux (huile, liquide de refroidissement)", False),
    ("Rétroviseurs et pare-brise", False),
    ("Documents de bord présents", False),
]


def create_default_template(db: Session, company_id: int, vehicle_type: str = "poids_lourd"):
    t = ChecklistTemplate(company_id=company_id, vehicle_type=vehicle_type, nom="Contrôle avant départ")
    db.add(t)
    db.flush()
    for ordre, (libelle, critique) in enumerate(DEFAULT_ITEMS):
        db.add(ChecklistItem(company_id=company_id, template_id=t.id, libelle=libelle,
                             critique=critique, ordre=ordre))
    return t


def active_items(db: Session, company_id: int, vehicle_type: str) -> list[ChecklistItem]:
    return list(db.scalars(
        select(ChecklistItem)
        .join(ChecklistTemplate, ChecklistItem.template_id == ChecklistTemplate.id)
        .where(ChecklistTemplate.company_id == company_id,
               ChecklistTemplate.vehicle_type == vehicle_type,
               ChecklistItem.actif.is_(True))
        .order_by(ChecklistItem.ordre, ChecklistItem.id)
    ))
