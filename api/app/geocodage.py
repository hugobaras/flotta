"""Géocodage via l'API Adresse (api-adresse.data.gouv.fr), en lot, avec cache en base."""
import csv
import io
import logging
import os
import unicodedata
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GeocodeCache

log = logging.getLogger(__name__)
SEUIL_OK = 0.75       # au-dessus : adresse fiable
SEUIL_DOUTEUX = 0.5   # entre les deux : à vérifier, en dessous : introuvable


class GeocodageIndisponible(Exception):
    pass


@dataclass
class Resultat:
    lat: float | None
    lng: float | None
    score: float | None
    libelle: str | None

    @property
    def statut(self) -> str:
        if self.lat is None or self.lng is None or self.score is None or self.score < SEUIL_DOUTEUX:
            return "introuvable"
        return "ok" if self.score >= SEUIL_OK else "douteux"


def base_url() -> str:
    return os.getenv("GEOCODER_URL", "https://api-adresse.data.gouv.fr").rstrip("/")


def normaliser(adresse: str) -> str:
    texte = unicodedata.normalize("NFKD", adresse).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in texte).split())[:300]


def _depuis_cache(c: GeocodeCache) -> Resultat:
    return Resultat(c.lat, c.lng, c.score, c.libelle)


def geocoder_lot(db: Session, adresses: list[str]) -> dict[str, Resultat]:
    """Renvoie {adresse_normalisée: Resultat}. Seules les adresses absentes du cache partent vers l'API."""
    normales = {a: normaliser(a) for a in adresses if a and a.strip()}
    cles = set(normales.values())
    cache = {c.adresse_norm: c for c in db.scalars(select(GeocodeCache).where(GeocodeCache.adresse_norm.in_(cles)))} if cles else {}
    manquantes = {}
    for brute, norm in normales.items():
        if norm and norm not in cache and norm not in manquantes:
            manquantes[norm] = brute
    if manquantes:
        try:
            nouveaux = _interroger(list(manquantes.items()))
        except (httpx.HTTPError, ValueError) as e:
            log.warning("Géocodage indisponible : %s", e)
            raise GeocodageIndisponible(str(e)) from e
        for norm, res in nouveaux.items():
            ligne = GeocodeCache(adresse_norm=norm, lat=res.lat, lng=res.lng, score=res.score, libelle=res.libelle)
            db.add(ligne)
            cache[norm] = ligne
        db.flush()
    return {norm: _depuis_cache(cache[norm]) for norm in cles if norm in cache}


def _interroger(paires: list[tuple[str, str]]) -> dict[str, Resultat]:
    """Un seul appel au service de géocodage CSV pour toutes les adresses manquantes."""
    entree = io.StringIO()
    ecrivain = csv.writer(entree)
    ecrivain.writerow(["cle", "adresse"])
    for norm, brute in paires:
        ecrivain.writerow([norm, brute])
    reponse = httpx.post(f"{base_url()}/search/csv/", files={"data": ("adresses.csv", entree.getvalue().encode(), "text/csv")},
                         data={"columns": "adresse", "limit": "1"}, timeout=60)
    reponse.raise_for_status()
    sortie: dict[str, Resultat] = {}
    for ligne in csv.DictReader(io.StringIO(reponse.text)):
        try:
            lat, lng, score = float(ligne["latitude"]), float(ligne["longitude"]), float(ligne["result_score"])
            res = Resultat(lat, lng, score, ligne.get("result_label") or None)
        except (KeyError, ValueError, TypeError):
            res = Resultat(None, None, None, None)  # adresse sans résultat
        sortie[ligne.get("cle", "")] = res
    for norm, _ in paires:
        sortie.setdefault(norm, Resultat(None, None, None, None))
    return sortie


def geocoder_une(db: Session, adresse: str) -> Resultat:
    return geocoder_lot(db, [adresse])[normaliser(adresse)]
