from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import routage
from .auth import current_user
from .db import get_db
from .models import Company, User, Vehicle

router = APIRouter(prefix="/api/admin/itineraires")


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ItineraireIn(BaseModel):
    vehicle_id: int
    points: list[Point] = Field(min_length=2, max_length=25)


@router.get("/etat")
def etat(user: User = Depends(current_user)):
    return {"disponible": routage.disponible()}


@router.post("")
def calculer(body: ItineraireIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = db.scalar(select(Vehicle).where(Vehicle.id == body.vehicle_id, Vehicle.company_id == user.company_id))
    if not v:
        raise HTTPException(404, "Véhicule inconnu")
    manque = routage.gabarit_manquant(v)
    if manque:
        raise HTTPException(422, f"Renseignez le gabarit du véhicule {v.plaque} avant de calculer un itinéraire : {', '.join(manque)}")
    try:
        it = routage.calculer([(p.lat, p.lng) for p in body.points], v)
    except routage.RouteurIndisponible:
        raise HTTPException(503, "Le service de calcul d'itinéraire poids lourd est indisponible. Aucun itinéraire n'est affiché : réessayez plus tard.")
    except routage.ItineraireImpossible as e:
        raise HTTPException(422, f"Aucun itinéraire poids lourd possible avec ce gabarit entre ces points ({e}).")
    avertissements = list(it.avertissements)
    if not v.essieux:
        avertissements.append("Nombre d'essieux non renseigné : valeur par défaut du service de routage.")
    company = db.get(Company, user.company_id)
    return {"duree_s": it.duree_s, "distance_km": it.distance_km, "geometrie": it.geometrie, "peage": it.peage,
            "avertissements": avertissements, "estimation": routage.estimer(it.distance_km, it.peage, company),
            "gabarit": routage.options_camion(v), "vehicule": v.plaque}
