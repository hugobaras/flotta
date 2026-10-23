from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, false, true
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
    # Hypothèses d'estimation des coûts d'un itinéraire (sans API payante), réglables par société.
    cout_km_eur: Mapped[float] = mapped_column(Float, default=0, server_default="0")  # coût d'exploitation hors carburant et péages
    conso_l_100km: Mapped[float] = mapped_column(Float, default=32, server_default="32")
    prix_carburant_eur_l: Mapped[float] = mapped_column(Float, default=1.7, server_default="1.7")
    peage_eur_km: Mapped[float] = mapped_column(Float, default=0, server_default="0")  # appliqué si l'itinéraire emprunte un péage


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True)
    offre: Mapped[str] = mapped_column(String(20), default="essentiel")  # essentiel | pro
    camions_factures: Mapped[int] = mapped_column(default=1)
    statut: Mapped[str] = mapped_column(String(20), default="actif")  # essai | actif | suspendu
    debut: Mapped[date] = mapped_column(Date, default=date.today)


class Facture(Base):
    """Devis ou facture émis par la plateforme pour une société cliente (montants en centimes)."""
    __tablename__ = "factures"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True)  # FA-2026-0001 / DE-2026-0001
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    type: Mapped[str] = mapped_column(String(10))  # devis | facture
    emise_le: Mapped[date] = mapped_column(Date)
    detail: Mapped[dict] = mapped_column(JSON)  # offre, camions, période, remise, TVA et montants figés à l'émission


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    nom: Mapped[str] = mapped_column(String(100))
    apercu: Mapped[str] = mapped_column(String(16))  # début de la clé, pour la reconnaître sans la révéler
    hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 : la clé elle-même n'est jamais stockée
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    derniere_utilisation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoquee_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Webhook(Base):
    __tablename__ = "webhooks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(64))  # nécessaire pour signer : stocké en clair, montré une seule fois
    evenements: Mapped[list] = mapped_column(JSON)
    actif: Mapped[bool] = mapped_column(default=True, server_default=true())


class WebhookLivraison(Base):
    __tablename__ = "webhook_livraisons"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id"), index=True)
    evenement: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    statut: Mapped[str] = mapped_column(String(10), default="en_attente")  # en_attente | ok | echec
    tentatives: Mapped[int] = mapped_column(default=0)
    prochaine_tentative: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    derniere_erreur: Mapped[str | None] = mapped_column(String(300))
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Journal d'audit des actions sensibles (déblocage, suppression, changement d'offre, clés…). Jamais modifié ni purgé avec les contrôles."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    user_email: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(60))
    cible: Mapped[str] = mapped_column(String(200), default="")
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Signalement(Base):
    """« Signaler un problème » : message de l'utilisateur et contexte capturé automatiquement."""
    __tablename__ = "signalements"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    user_email: Mapped[str] = mapped_column(String(254))
    message: Mapped[str] = mapped_column(Text)
    contexte: Mapped[dict] = mapped_column(JSON)  # page, société, version, navigateur
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


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
    __table_args__ = (UniqueConstraint("company_id", "plaque", name="uq_vehicle_plaque"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    plaque: Mapped[str] = mapped_column(String(20))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(30), default="poids_lourd", server_default="poids_lourd")
    bloque: Mapped[bool] = mapped_column(default=False)
    actif: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Gabarit (mètres, kilogrammes), utilisé par le routage poids lourd.
    hauteur_m: Mapped[float | None] = mapped_column(Float)
    largeur_m: Mapped[float | None] = mapped_column(Float)
    longueur_m: Mapped[float | None] = mapped_column(Float)
    ptac_kg: Mapped[int | None]
    charge_utile_kg: Mapped[int | None]
    essieux: Mapped[int | None]
    # Capacité de chargement.
    palettes: Mapped[int | None]
    capacite_kg: Mapped[int | None]
    capacite_m3: Mapped[float | None] = mapped_column(Float)
    adr: Mapped[bool] = mapped_column(default=False, server_default=false())
    frigo: Mapped[bool] = mapped_column(default=False, server_default=false())


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    nom: Mapped[str] = mapped_column(String(100))
    # HMAC du code PIN (jamais le PIN en clair) : permet de retrouver le conducteur sans parcourir des hachages lents.
    pin_hash: Mapped[str] = mapped_column(String(64))
    vehicule_habituel_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    actif: Mapped[bool] = mapped_column(default=True, server_default=true())
    email: Mapped[str | None] = mapped_column(String(254))  # pour lui envoyer le lien de sa tournée
    __table_args__ = (UniqueConstraint("company_id", "pin_hash", name="uq_driver_pin"),)


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
    conducteur_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    # Identifiant généré par le téléphone : rejouer un envoi (réseau coupé) ne crée jamais de doublon.
    client_id: Mapped[str | None] = mapped_column(String(64))
    recu_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)  # arrivée sur le serveur
    # Copie figée des points au moment du contrôle : [{id, libelle, critique, ok, commentaire}]
    reponses: Mapped[list] = mapped_column(JSON)
    defaut_critique: Mapped[bool] = mapped_column(default=False)
    has_defaut: Mapped[bool] = mapped_column(default=False, server_default=false())  # au moins un point KO
    signature: Mapped[str | None] = mapped_column(Text)  # data URL PNG
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)  # moment réel du contrôle
    __table_args__ = (UniqueConstraint("company_id", "client_id", name="uq_check_client"),)


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


class Depot(Base):
    __tablename__ = "depots"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    nom: Mapped[str] = mapped_column(String(100))
    adresse: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    ouverture: Mapped[str] = mapped_column(String(5), default="06:00", server_default="06:00")  # HH:MM
    fermeture: Mapped[str] = mapped_column(String(5), default="19:00", server_default="19:00")
    par_defaut: Mapped[bool] = mapped_column(default=False, server_default=false())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    reference: Mapped[str] = mapped_column(String(60))
    client: Mapped[str] = mapped_column(String(150), default="", server_default="")
    adresse: Mapped[str] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    geo_score: Mapped[float | None] = mapped_column(Float)
    # a_geocoder | ok | douteux | introuvable | manuel
    geo_statut: Mapped[str] = mapped_column(String(20), default="a_geocoder", server_default="a_geocoder")
    poids_kg: Mapped[int] = mapped_column(default=0, server_default="0")
    volume_m3: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    palettes: Mapped[int] = mapped_column(default=0, server_default="0")
    fenetre_debut: Mapped[str | None] = mapped_column(String(5))  # HH:MM
    fenetre_fin: Mapped[str | None] = mapped_column(String(5))
    duree_service_min: Mapped[int] = mapped_column(default=15, server_default="15")
    frigo: Mapped[bool] = mapped_column(default=False, server_default=false())
    adr: Mapped[bool] = mapped_column(default=False, server_default=false())
    hayon: Mapped[bool] = mapped_column(default=False, server_default=false())
    contact_nom: Mapped[str] = mapped_column(String(100), default="", server_default="")
    contact_telephone: Mapped[str] = mapped_column(String(30), default="", server_default="")
    consignes: Mapped[str] = mapped_column(String(500), default="", server_default="")  # accès, code porte, quai...
    date_livraison: Mapped[date] = mapped_column(Date, index=True)
    statut: Mapped[str] = mapped_column(String(20), default="a_planifier", server_default="a_planifier")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (UniqueConstraint("company_id", "reference", "date_livraison", name="uq_order_ref_day"),)


class GeocodeCache(Base):
    """Résultats de géocodage déjà obtenus : une adresse n'est interrogée qu'une fois."""
    __tablename__ = "geocode_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    adresse_norm: Mapped[str] = mapped_column(String(300), unique=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    libelle: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ColumnMapping(Base):
    """Association colonnes du fichier -> champs d'une commande, mémorisée par société."""
    __tablename__ = "column_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True)
    mapping: Mapped[dict] = mapped_column(JSON)


class Plan(Base):
    """Plan de tournées d'une journée, calculé en tâche de fond."""
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    jour: Mapped[date] = mapped_column(Date, index=True)
    # en_attente | en_cours | termine | echec
    statut: Mapped[str] = mapped_column(String(20), default="en_attente", server_default="en_attente")
    progression: Mapped[int] = mapped_column(default=0, server_default="0")
    message: Mapped[str | None] = mapped_column(Text)
    parametres: Mapped[dict] = mapped_column(JSON, default=dict)
    resume: Mapped[dict | None] = mapped_column(JSON)  # kilomètres, durée, taux de remplissage, véhicules exclus...
    non_affectees: Mapped[list] = mapped_column(JSON, default=list)  # [{order_id, raison}]
    matrices: Mapped[dict | None] = mapped_column(JSON)  # conservées pour recalculer sans rappeler le routage
    nom: Mapped[str | None] = mapped_column(String(100))  # nom de la version enregistrée
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))  # plan dont cette version est copiée
    curseur: Mapped[int] = mapped_column(default=0, server_default="0")  # position dans l'historique des modifications
    publie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # tournées visibles par les chauffeurs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    depart_min: Mapped[float] = mapped_column(Float)
    retour_min: Mapped[float] = mapped_column(Float)
    trajet_s: Mapped[int]
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    charge_kg: Mapped[int] = mapped_column(default=0)
    charge_palettes: Mapped[int] = mapped_column(default=0)
    charge_m3: Mapped[float] = mapped_column(Float, default=0)
    verrouille: Mapped[bool] = mapped_column(default=False, server_default=false())
    conducteur_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    conduite_min: Mapped[float] = mapped_column(Float, default=0, server_default="0")  # conduite effective, hors pauses
    pauses: Mapped[list] = mapped_column(JSON, default=list)  # pauses réglementaires insérées : [[début, fin], ...] en minutes


class RouteStop(Base):
    __tablename__ = "route_stops"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    ordre: Mapped[int]
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    arrivee_min: Mapped[float] = mapped_column(Float)
    depart_min: Mapped[float] = mapped_column(Float)
    attente_min: Mapped[float] = mapped_column(Float, default=0)
    verrouille: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Rotation du camion (1, 2, 3) : entre deux rotations il revient au dépôt et recharge.
    rotation: Mapped[int] = mapped_column(default=1, server_default="1")


class PlanSnapshot(Base):
    """État du plan après chaque modification : annuler / rétablir. Le snapshot 0 est le plan optimisé d'origine."""
    __tablename__ = "plan_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    seq: Mapped[int]
    libelle: Mapped[str] = mapped_column(String(200))
    etat: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    __table_args__ = (UniqueConstraint("plan_id", "seq", name="uq_snapshot_seq"),)


class ActiviteConducteur(Base):
    """Activité déclarée d'un conducteur (conduite, autre tâche, disponibilité, repos) : base du calcul des temps restants."""
    __tablename__ = "driver_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    conducteur_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # conduite | travail | disponibilite | repos
    debut: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanLien(Base):
    """Lien personnel d'une tournée : le jeton donne accès à la tournée d'un véhicule dans un plan, sans compte."""
    __tablename__ = "plan_links"
    token: Mapped[str] = mapped_column(String(40), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    __table_args__ = (UniqueConstraint("plan_id", "vehicle_id", name="uq_link_plan_vehicle"),)


class LivraisonEvenement(Base):
    """Changement de statut d'un arrêt (arrivé, livré, impossible), envoyé par le téléphone du chauffeur. Journal sans modification."""
    __tablename__ = "delivery_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    statut: Mapped[str] = mapped_column(String(20))  # arrive | livre | impossible
    client_id: Mapped[str | None] = mapped_column(String(64))
    fait_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # heure réelle (téléphone si plausible)
    recu_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    motif: Mapped[str | None] = mapped_column(String(40))
    commentaire: Mapped[str | None] = mapped_column(String(300))
    nom_destinataire: Mapped[str | None] = mapped_column(String(100))
    signature: Mapped[str | None] = mapped_column(Text)  # data URL PNG
    __table_args__ = (UniqueConstraint("company_id", "client_id", name="uq_delivery_client"),)


class LivraisonPhoto(Base):
    __tablename__ = "delivery_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    evenement_id: Mapped[int] = mapped_column(ForeignKey("delivery_events.id"), index=True)
    fichier: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
