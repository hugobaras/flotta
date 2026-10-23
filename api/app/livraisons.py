"""Suivi des livraisons : aides partagées entre l'API des chauffeurs et l'affichage du planning."""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .exploitation import PARIS, day_bounds
from .models import Check, LivraisonEvenement, LivraisonPhoto, Vehicle

RETARD_TOLERE_MIN = 15
MOTIFS = {"absent": "Destinataire absent", "ferme": "Site fermé", "refus": "Livraison refusée", "adresse": "Adresse introuvable",
          "marchandise": "Marchandise endommagée", "autre": "Autre motif"}
FINAUX = ("livre", "impossible")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)  # isolé pour figer l'horloge dans les tests


def aujourdhui() -> date:
    return maintenant().astimezone(PARIS).date()


def controle_du_jour(db: Session, vehicle: Vehicle, jour: date) -> tuple[bool, str | None]:
    """La tournée n'est accessible que si le camion n'est pas bloqué et que son contrôle avant départ du jour est fait."""
    if vehicle.bloque:
        return False, "Ce camion est bloqué : ne prenez pas la route et contactez votre exploitant."
    debut, fin = day_bounds(jour)
    fait = db.scalar(select(Check.id).where(Check.vehicle_id == vehicle.id, Check.created_at >= debut, Check.created_at <= fin).limit(1))
    if fait is None:
        return False, "Le contrôle avant départ du jour n'est pas fait : faites-le pour débloquer votre tournée."
    return True, None


def derniers_evenements(db: Session, plan_id: int) -> dict[int, dict]:
    """Par commande : statut courant, heures d'arrivée et de clôture, motif, photos."""
    evs = list(db.scalars(select(LivraisonEvenement).where(LivraisonEvenement.plan_id == plan_id)
                          .order_by(LivraisonEvenement.fait_le, LivraisonEvenement.id)))
    photos: dict[int, list[int]] = {}
    if evs:
        for p in db.scalars(select(LivraisonPhoto).where(LivraisonPhoto.evenement_id.in_([e.id for e in evs]))):
            photos.setdefault(p.evenement_id, []).append(p.id)
    sortie: dict[int, dict] = {}
    for e in evs:
        s = sortie.setdefault(e.order_id, {"statut": None, "arrive_le": None, "termine_le": None, "motif": None, "commentaire": None,
                                           "nom_destinataire": None, "a_signature": False, "photos": [], "lat": None, "lng": None})
        if e.statut == "arrive" and s["arrive_le"] is None:
            s["arrive_le"] = e.fait_le
        if e.statut in FINAUX or s["statut"] is None or s["statut"] == "arrive":
            s["statut"] = e.statut
        if e.statut in FINAUX:
            s.update(termine_le=e.fait_le, motif=e.motif, commentaire=e.commentaire, nom_destinataire=e.nom_destinataire,
                     a_signature=bool(e.signature), lat=e.lat, lng=e.lng)
        s["photos"] += photos.get(e.id, [])
    return sortie


def retard_min(arrivee_prevue_min: float, statut: str | None, jour: date) -> int | None:
    """Retard d'un arrêt pas encore atteint : minutes écoulées depuis l'heure prévue (au-delà de la tolérance), le jour même seulement."""
    if statut is not None or jour != aujourdhui():
        return None
    local = maintenant().astimezone(PARIS)
    ecart = local.hour * 60 + local.minute - arrivee_prevue_min
    return int(ecart) if ecart > RETARD_TOLERE_MIN else None
