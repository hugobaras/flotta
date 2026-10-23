"""Matrices de durées et de distances entre le dépôt et les commandes, par profil de véhicule (via Valhalla)."""
import logging

import httpx

from .routage import RouteurIndisponible, valhalla_url

log = logging.getLogger(__name__)
BLOC = 40  # Valhalla limite le nombre de paires par requête : on découpe en blocs de BLOC x BLOC
INJOIGNABLE_S = 3 * 86400


def _bloc(sources, cibles, options):
    corps = {"sources": [{"lat": a, "lon": b} for a, b in sources], "targets": [{"lat": a, "lon": b} for a, b in cibles],
             "costing": "truck", "costing_options": {"truck": options}}
    try:
        r = httpx.post(f"{valhalla_url()}/sources_to_targets", json=corps, timeout=60)
    except httpx.HTTPError as e:
        raise RouteurIndisponible(str(e)) from e
    if r.status_code >= 400:
        raise RouteurIndisponible(f"Valhalla a répondu {r.status_code}")
    try:
        return r.json()["sources_to_targets"]
    except (KeyError, ValueError, TypeError) as e:
        raise RouteurIndisponible("Réponse inattendue de Valhalla") from e


def valhalla(locations: list[tuple[float, float]], profils: dict[str, dict]) -> dict[str, dict]:
    """locations = [(lat, lng)] (dépôt en premier). Renvoie {profil: {"durations": [[s]], "distances": [[km]]}}."""
    n = len(locations)
    sortie = {}
    for cle, options in profils.items():
        durees = [[0] * n for _ in range(n)]
        distances = [[0.0] * n for _ in range(n)]
        for i0 in range(0, n, BLOC):
            for j0 in range(0, n, BLOC):
                src, cib = locations[i0:i0 + BLOC], locations[j0:j0 + BLOC]
                for ligne in _bloc(src, cib, options):
                    for cell in ligne:
                        i, j = i0 + cell["from_index"], j0 + cell["to_index"]
                        if i == j:
                            continue
                        # Trajet sans chemin : durée très grande, pour que le solveur l'évite.
                        durees[i][j] = int(cell["time"]) if cell.get("time") is not None else INJOIGNABLE_S
                        distances[i][j] = float(cell["distance"]) if cell.get("distance") is not None else 0.0
        sortie[cle] = {"durations": durees, "distances": distances}
    return sortie


# Remplaçable dans les tests : fournisseur(locations, profils) -> {profil: {"durations", "distances"}}
fournisseur = valhalla
