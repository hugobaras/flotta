"""Test d'intégration sur un cas réel (pont bas) : ignoré tant que le cas et un Valhalla chargé ne sont pas fournis."""
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import routage

CAS = Path(__file__).parent / "data" / "pont_bas.json"

pytestmark = pytest.mark.skipif(
    not (CAS.exists() and os.getenv("VALHALLA_URL")),
    reason="Fournir tests/data/pont_bas.json (voir README) et VALHALLA_URL pour valider le routage sur un cas réel",
)


def camion(hauteur):
    return SimpleNamespace(hauteur_m=hauteur, largeur_m=2.55, longueur_m=16.5, ptac_kg=40000, essieux=5, adr=False)


def passe_a_proximite(geometrie, pont, rayon_m=60):
    for lng, lat in geometrie["coordinates"]:
        dx = (lng - pont["lng"]) * 111_320 * math.cos(math.radians(lat))
        dy = (lat - pont["lat"]) * 110_540
        if math.hypot(dx, dy) < rayon_m:
            return True
    return False


def test_camion_trop_haut_evite_le_pont_bas():
    cas = json.loads(CAS.read_text())
    points = [(cas["depart"]["lat"], cas["depart"]["lng"]), (cas["arrivee"]["lat"], cas["arrivee"]["lng"])]
    try:
        trop_haut = routage.calculer(points, camion(cas["hauteur_trop_haute_m"]))
        assert not passe_a_proximite(trop_haut.geometrie, cas["pont"])
    except routage.ItineraireImpossible:
        pass  # aucun chemin : acceptable, ce qui compte est de ne jamais passer sous le pont
    compatible = routage.calculer(points, camion(cas["hauteur_compatible_m"]))
    assert compatible.distance_km > 0
