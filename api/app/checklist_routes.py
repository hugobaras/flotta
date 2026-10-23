from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import ChecklistItem, ChecklistTemplate, User

router = APIRouter(prefix="/api/admin/checklists")


def _item_out(i: ChecklistItem):
    return {"id": i.id, "libelle": i.libelle, "critique": i.critique, "ordre": i.ordre, "actif": i.actif}


def _own_item(db: Session, user: User, item_id: int) -> ChecklistItem:
    item = db.scalar(select(ChecklistItem).where(
        ChecklistItem.id == item_id, ChecklistItem.company_id == user.company_id))
    if not item:
        raise HTTPException(404, "Point inconnu")
    return item


@router.get("")
def list_templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    templates = db.scalars(select(ChecklistTemplate).where(ChecklistTemplate.company_id == user.company_id))
    out = []
    for t in templates:
        items = db.scalars(select(ChecklistItem).where(ChecklistItem.template_id == t.id)
                           .order_by(ChecklistItem.ordre, ChecklistItem.id))
        out.append({"id": t.id, "nom": t.nom, "vehicle_type": t.vehicle_type,
                    "items": [_item_out(i) for i in items]})
    return out


class ItemIn(BaseModel):
    libelle: str = Field(min_length=1, max_length=200)
    critique: bool = False


@router.post("/{template_id}/items", status_code=201)
def add_item(template_id: int, body: ItemIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    t = db.scalar(select(ChecklistTemplate).where(
        ChecklistTemplate.id == template_id, ChecklistTemplate.company_id == user.company_id))
    if not t:
        raise HTTPException(404, "Modèle inconnu")
    last = db.scalar(select(ChecklistItem.ordre).where(ChecklistItem.template_id == t.id)
                     .order_by(ChecklistItem.ordre.desc()).limit(1))
    item = ChecklistItem(company_id=user.company_id, template_id=t.id, libelle=body.libelle.strip(),
                         critique=body.critique, ordre=(last + 1) if last is not None else 0)
    db.add(item)
    db.commit()
    return _item_out(item)


class ItemPatch(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=200)
    critique: bool | None = None
    actif: bool | None = None


@router.patch("/items/{item_id}")
def patch_item(item_id: int, body: ItemPatch, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    item = _own_item(db, user, item_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value.strip() if field == "libelle" else value)
    db.commit()
    return _item_out(item)


class Move(BaseModel):
    sens: Literal["haut", "bas"]


@router.post("/items/{item_id}/deplacer")
def move_item(item_id: int, body: Move, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    item = _own_item(db, user, item_id)
    items = list(db.scalars(select(ChecklistItem).where(ChecklistItem.template_id == item.template_id)
                            .order_by(ChecklistItem.ordre, ChecklistItem.id)))
    pos = items.index(item)
    other = pos - 1 if body.sens == "haut" else pos + 1
    if 0 <= other < len(items):
        items[pos], items[other] = items[other], items[pos]
    for n, i in enumerate(items):  # renumérote : pas de doublons d'ordre
        i.ordre = n
    db.commit()
    return [_item_out(i) for i in items]
