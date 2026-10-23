from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now():
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="exploitant")  # admin | exploitant


class Session(Base):
    __tablename__ = "sessions"
    # sha256 du jeton du cookie : une fuite de la base ne donne pas de session valide.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    plaque: Mapped[str] = mapped_column(String(20))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(30), default="poids_lourd", server_default="poids_lourd")
    bloque: Mapped[bool] = mapped_column(default=False)


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(30))
    nom: Mapped[str] = mapped_column(String(200))


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id"), index=True)
    libelle: Mapped[str] = mapped_column(String(200))
    critique: Mapped[bool] = mapped_column(default=False)
    ordre: Mapped[int]
    actif: Mapped[bool] = mapped_column(default=True)


class Check(Base):
    __tablename__ = "checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    conducteur: Mapped[str] = mapped_column(String(100))
    # Copie figée des points au moment du contrôle : [{id, libelle, critique, ok, commentaire}]
    reponses: Mapped[list] = mapped_column(JSON)
    defaut_critique: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
