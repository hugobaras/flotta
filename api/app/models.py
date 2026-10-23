from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now():
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200))
    heure_rappel: Mapped[str] = mapped_column(String(5), default="08:00", server_default="08:00")  # HH:MM, heure de Paris
    # RGPD : durée de conservation des contrôles, photos et positions (3 ans par défaut).
    retention_jours: Mapped[int] = mapped_column(default=1095, server_default="1095")
    alert_emails: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # destinataires des alertes
    logo_fichier: Mapped[str | None] = mapped_column(String(100))
    rappel_envoye_le: Mapped[date | None] = mapped_column(Date)  # un seul rappel par jour et par société


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
    has_defaut: Mapped[bool] = mapped_column(default=False, server_default=false())  # au moins un point KO
    signature: Mapped[str | None] = mapped_column(Text)  # data URL PNG
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CheckPhoto(Base):
    __tablename__ = "check_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    fichier: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Unblock(Base):
    __tablename__ = "unblocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    commentaire: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Alert(Base):
    """Suivi de l'envoi d'un email d'alerte (défaut critique)."""
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    check_id: Mapped[int] = mapped_column(ForeignKey("checks.id"), index=True)
    # en_attente | envoye | echec | non_configure | sans_destinataire
    statut: Mapped[str] = mapped_column(String(20), default="en_attente")
    tentatives: Mapped[int] = mapped_column(default=0)
    erreur: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
