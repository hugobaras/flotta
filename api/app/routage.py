"""Itinéraire poids lourd via Valhalla (profil « truck »). Jamais d'itinéraire inventé : si Valhalla ne répond pas, on le dit."""
import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)


class RouteurIndisponible(Exception):
    """Valhalla ne répond pas (arrêté, tuiles en construction, réseau)."""


class ItineraireImpossible(Exception):
    """Valhalla répond mais ne trouve aucun chemin compatible avec le gabarit."""


def valhalla_url() -> str:
    return os.getenv("VALHALLA_URL", "http://valhalla:8002").rstrip("/")


GABARIT_REQUIS = [("hauteur_m", "hauteur"), ("largeur_m", "largeur"), ("longueur_m", "longueur"), ("ptac_kg", "PTAC")]


def gabarit_manquant(v) -> list[str]:
    return [libelle for champ, libelle in GABARIT_REQUIS if getattr(v, champ) is None]


def options_camion(v) -> dict:
    """Options du profil « truck » depuis la fiche véhicule (mètres, tonnes)."""
    o = {"height": v.hauteur_m, "width": v.largeur_m, "length": v.longueur_m, "weight": round(v.ptac_kg / 1000, 2),
         "hazmat": bool(v.adr)}
    if v.essieux:
        o["axle_count"] = v.essieux
        o["axle_load"] = round(v.ptac_kg / 1000 / v.essieux, 2)  # répartition uniforme : approximation
    return o


def decoder_polyline6(texte: str) -> list[list[float]]:
    """Décode la géométrie Valhalla (polyline à 6 décimales) en [[lng, lat], ...] (ordre GeoJSON)."""
    coords, i, lat, lng = [], 0, 0, 0
    while i < len(texte):
        for axe in (0, 1):
            decalage = resultat = 0
            while True:
                b = ord(texte[i]) - 63
                i += 1
                resultat |= (b & 0x1F) << decalage
                decalage += 5
                if b < 0x20:
                    break
            delta = ~(resultat >> 1) if resultat & 1 else resultat >> 1
            if axe == 0:
                lat += delta
            else:
                lng += delta
        coords.append([lng / 1e6, lat / 1e6])
    return coords


@dataclass
class Itineraire:
    duree_s: float
    distance_km: float
    geometrie: dict  # GeoJSON LineString
    peage: bool
    avertissements: list[str]


def _avertissements(reponse: dict) -> list[str]:
    bruts = list(reponse.get("warnings") or []) + list((reponse.get("trip") or {}).get("warnings") or [])
    return [w.get("text", str(w)) if isinstance(w, dict) else str(w) for w in bruts]


def calculer(points: list[tuple[float, float]], v) -> Itineraire:
    """points = [(lat, lng), ...] dans l'ordre de passage (2 minimum)."""
    corps = {
        "locations": [{"lat": lat, "lon": lng, "type": "break"} for lat, lng in points],
        "costing": "truck",
        "costing_options": {"truck": options_camion(v)},
        "directions_options": {"units": "kilometers", "language": "fr-FR"},
    }
    try:
        r = httpx.post(f"{valhalla_url()}/route", json=corps, timeout=30)
    except httpx.HTTPError as e:
        log.warning("Valhalla injoignable : %s", e)
        raise RouteurIndisponible(str(e)) from e
    if r.status_code >= 500:
        raise RouteurIndisponible(f"Valhalla a répondu {r.status_code}")
    if r.status_code >= 400:
        try:
            detail = r.json()
        except ValueError:
            detail = {}
        raise ItineraireImpossible(detail.get("error") or f"Valhalla a refusé la requête ({r.status_code})")
    try:
        trip = r.json()["trip"]
        coords: list[list[float]] = []
        for jambe in trip["legs"]:
            pts = decoder_polyline6(jambe["shape"])
            coords.extend(pts[1:] if coords else pts)  # le dernier point d'une jambe est le premier de la suivante
        resume = trip["summary"]
    except (KeyError, ValueError, TypeError, IndexError) as e:
        raise RouteurIndisponible("Réponse inattendue de Valhalla") from e
    return Itineraire(duree_s=float(resume["time"]), distance_km=float(resume["length"]),
                      geometrie={"type": "LineString", "coordinates": coords}, peage=bool(resume.get("has_toll")),
                      avertissements=_avertissements(r.json()))


def disponible() -> bool:
    try:
        return httpx.get(f"{valhalla_url()}/status", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


def estimer(distance_km: float, peage: bool, company) -> dict:
    """Estimation indicative des coûts : carburant, péage, coût kilométrique. Les hypothèses sont renvoyées avec le résultat."""
    carburant = distance_km * company.conso_l_100km / 100 * company.prix_carburant_eur_l
    peage_eur = distance_km * company.peage_eur_km if peage else 0.0
    autre = distance_km * company.cout_km_eur
    return {"carburant_eur": round(carburant, 2), "peage_eur": round(peage_eur, 2), "cout_km_eur": round(autre, 2),
            "total_eur": round(carburant + peage_eur + autre, 2), "estimation": True,
            "hypotheses": {"conso_l_100km": company.conso_l_100km, "prix_carburant_eur_l": company.prix_carburant_eur_l,
                           "peage_eur_km": company.peage_eur_km, "cout_km_eur": company.cout_km_eur,
                           "peage_emprunte": peage}}
