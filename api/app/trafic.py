"""Trafic en direct : interface et implémentations HERE / TomTom, **désactivées par défaut**.

Rien n'est appelé tant que `TRAFIC_ACTIF=1` n'est pas défini avec une clé (`HERE_API_KEY` ou `TOMTOM_API_KEY`). Ces fournisseurs sont des
services tiers à tarification propre : leur activation est une décision de l'exploitant. Les implémentations ci-dessous suivent la documentation
publique des deux services mais n'ont pas été éprouvées contre les vrais services (aucune clé disponible au développement).
"""
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

log = logging.getLogger(__name__)


class TraficIndisponible(Exception):
    pass


class FournisseurTrafic(ABC):
    nom: str

    @abstractmethod
    def durees(self, origines: list[tuple[float, float]], destinations: list[tuple[float, float]], depart: datetime) -> list[list[float | None]]:
        """Matrice des durées de trajet en secondes (trafic en direct à `depart`) ; None si aucun chemin."""


class HereTrafic(FournisseurTrafic):
    nom = "here"

    def __init__(self, cle: str):
        self.cle = cle

    def durees(self, origines, destinations, depart):
        corps = {"origins": [{"lat": a, "lng": b} for a, b in origines], "destinations": [{"lat": a, "lng": b} for a, b in destinations],
                 "regionDefinition": {"type": "world"}, "transportMode": "truck", "departureTime": depart.isoformat(),
                 "matrixAttributes": ["travelTimes"]}
        try:
            r = httpx.post("https://matrix.router.hereapi.com/v8/matrix", params={"apiKey": self.cle, "async": "false"}, json=corps, timeout=20)
            r.raise_for_status()
            m = r.json()["matrix"]
            n, p, t = m["numOrigins"], m["numDestinations"], m["travelTimes"]
            erreurs = set(m.get("errorCodes") or [])
            return [[None if (m.get("errorCodes") and m["errorCodes"][i * p + j] in erreurs - {0}) else float(t[i * p + j]) for j in range(p)] for i in range(n)]
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError) as e:
            raise TraficIndisponible(str(e)) from e


class TomTomTrafic(FournisseurTrafic):
    nom = "tomtom"

    def __init__(self, cle: str):
        self.cle = cle

    def durees(self, origines, destinations, depart):
        corps = {"origins": [{"point": {"latitude": a, "longitude": b}} for a, b in origines],
                 "destinations": [{"point": {"latitude": a, "longitude": b}} for a, b in destinations],
                 "options": {"departAt": depart.isoformat(), "routeType": "fastest", "traffic": "live", "travelMode": "truck"}}
        try:
            r = httpx.post("https://api.tomtom.com/routing/matrix/2", params={"key": self.cle}, json=corps, timeout=20)
            r.raise_for_status()
            sortie: list[list[float | None]] = [[None] * len(destinations) for _ in origines]
            for cell in r.json()["data"]:
                if "routeSummary" in cell:
                    sortie[cell["originIndex"]][cell["destinationIndex"]] = float(cell["routeSummary"]["travelTimeInSeconds"])
            return sortie
        except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError) as e:
            raise TraficIndisponible(str(e)) from e


def actif() -> bool:
    return os.getenv("TRAFIC_ACTIF", "").strip().lower() in ("1", "true", "oui")


def fournisseur() -> FournisseurTrafic | None:
    """Le fournisseur configuré, ou None : désactivé par défaut, ou clé absente."""
    if not actif():
        return None
    nom = os.getenv("TRAFIC_FOURNISSEUR", "here").strip().lower()
    cle = os.getenv("HERE_API_KEY" if nom == "here" else "TOMTOM_API_KEY", "")
    if not cle or nom not in ("here", "tomtom"):
        log.warning("Trafic activé mais fournisseur ou clé invalide (%s)", nom)
        return None
    return HereTrafic(cle) if nom == "here" else TomTomTrafic(cle)
