import json
from types import SimpleNamespace

import httpx
import pytest

from app import routage
from helpers import make_admin


def encoder_polyline6(coords):
    """Encodeur de test (algorithme de polyline à 6 décimales), pour vérifier le décodeur sans dépendre d'une valeur copiée."""
    sortie, prec_lat, prec_lng = [], 0, 0
    for lng, lat in coords:
        for valeur, prec in ((round(lat * 1e6), prec_lat), (round(lng * 1e6), prec_lng)):
            delta = valeur - prec
            delta = ~(delta << 1) if delta < 0 else delta << 1
            while delta >= 0x20:
                sortie.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            sortie.append(chr(delta + 63))
        prec_lat, prec_lng = round(lat * 1e6), round(lng * 1e6)
    return "".join(sortie)


NANTES, RENNES, ANGERS = (47.2184, -1.5536), (48.1173, -1.6778), (47.4784, -0.5632)


class FauxValhalla:
    def __init__(self, monkeypatch):
        self.requetes, self.mode = [], "ok"
        monkeypatch.setattr(routage.httpx, "post", self._post)
        monkeypatch.setattr(routage.httpx, "get", self._get)

    def _post(self, url, json, timeout):
        self.requetes.append((url, json))
        if self.mode == "panne":
            raise httpx.ConnectError("refusé")
        if self.mode == "erreur_serveur":
            return httpx.Response(503, request=httpx.Request("POST", url))
        if self.mode == "impossible":
            return httpx.Response(400, json={"error_code": 442, "error": "No path could be found for input"}, request=httpx.Request("POST", url))
        if self.mode == "charabia":
            return httpx.Response(200, json={"pas": "un trip"}, request=httpx.Request("POST", url))
        pts = [(l["lat"], l["lon"]) for l in json["locations"]]
        legs = []
        for (a, b) in zip(pts, pts[1:]):
            legs.append({"shape": encoder_polyline6([(a[1], a[0]), ((a[1] + b[1]) / 2, (a[0] + b[0]) / 2), (b[1], b[0])]),
                         "summary": {"time": 1800, "length": 50.0}})
        trip = {"legs": legs, "summary": {"time": 1800 * len(legs), "length": 50.0 * len(legs), "has_toll": self.mode == "peage"}}
        return httpx.Response(200, json={"trip": trip, "warnings": ["Restriction de hauteur sur le trajet"] if self.mode == "avertissement" else []},
                              request=httpx.Request("POST", url))

    def _get(self, url, timeout):
        if self.mode == "panne":
            raise httpx.ConnectError("refusé")
        return httpx.Response(200, request=httpx.Request("GET", url))


@pytest.fixture
def valhalla(monkeypatch):
    return FauxValhalla(monkeypatch)


def vehicule_complet(a, **extra):
    corps = {"plaque": "RT-100-RT", "hauteur_m": 3.9, "largeur_m": 2.55, "longueur_m": 16.5, "ptac_kg": 40000, "essieux": 5, "adr": True, **extra}
    return a.post("/api/admin/vehicules", json=corps).json()["id"]


def itineraire(c, vid, points=(NANTES, RENNES)):
    return c.post("/api/admin/itineraires", json={"vehicle_id": vid, "points": [{"lat": la, "lng": ln} for la, ln in points]})


# --- Fonctions pures ---


def test_polyline_roundtrip_with_negative_and_large_coordinates():
    coords = [[-1.5536, 47.2184], [-1.55361, 47.21842], [2.3522, 48.8566], [-179.99, -85.0], [0.0, 0.0]]
    decode = routage.decoder_polyline6(encoder_polyline6(coords))
    assert len(decode) == len(coords)
    for (lng, lat), (lng2, lat2) in zip(coords, decode):
        assert abs(lng - lng2) < 1e-6 and abs(lat - lat2) < 1e-6


def test_truck_options_from_vehicle_sheet():
    v = SimpleNamespace(hauteur_m=3.9, largeur_m=2.55, longueur_m=16.5, ptac_kg=40000, essieux=5, adr=True)
    assert routage.options_camion(v) == {"height": 3.9, "width": 2.55, "length": 16.5, "weight": 40.0, "hazmat": True,
                                         "axle_count": 5, "axle_load": 8.0}
    v.essieux, v.adr = None, False
    assert "axle_load" not in routage.options_camion(v) and routage.options_camion(v)["hazmat"] is False


def test_cost_estimation_uses_company_assumptions():
    c = SimpleNamespace(conso_l_100km=30, prix_carburant_eur_l=1.5, peage_eur_km=0.2, cout_km_eur=0.5)
    e = routage.estimer(200, True, c)
    assert (e["carburant_eur"], e["peage_eur"], e["cout_km_eur"], e["total_eur"]) == (90.0, 40.0, 100.0, 230.0)
    assert e["estimation"] is True and e["hypotheses"]["peage_emprunte"] is True
    assert routage.estimer(200, False, c)["peage_eur"] == 0


# --- Route d'itinéraire ---


def test_route_sends_truck_costing_with_the_vehicle_gauge(a, valhalla):
    vid = vehicule_complet(a)
    r = itineraire(a, vid)
    assert r.status_code == 200, r.text
    url, corps = valhalla.requetes[0]
    assert url.endswith("/route") and corps["costing"] == "truck"
    assert corps["costing_options"]["truck"]["height"] == 3.9 and corps["costing_options"]["truck"]["hazmat"] is True
    assert [(l["lat"], l["lon"]) for l in corps["locations"]] == [NANTES, RENNES]


def test_route_returns_duration_distance_geojson_and_estimate(a, valhalla):
    d = itineraire(a, vehicule_complet(a)).json()
    assert d["duree_s"] == 1800 and d["distance_km"] == 50.0 and d["vehicule"] == "RT-100-RT"
    assert d["geometrie"]["type"] == "LineString" and len(d["geometrie"]["coordinates"]) == 3
    lng, lat = d["geometrie"]["coordinates"][0]
    assert abs(lat - NANTES[0]) < 1e-5 and abs(lng - NANTES[1]) < 1e-5
    assert d["estimation"]["estimation"] is True and d["estimation"]["carburant_eur"] == round(50 * 32 / 100 * 1.7, 2)
    assert d["gabarit"]["height"] == 3.9


def test_multi_stop_route_joins_legs_without_duplicate_points(a, valhalla):
    d = itineraire(a, vehicule_complet(a), (NANTES, RENNES, ANGERS)).json()
    assert d["distance_km"] == 100.0 and len(d["geometrie"]["coordinates"]) == 5  # 3 + 3 - 1 point commun


def test_toll_flag_and_company_cost_settings(a, client, valhalla):
    make_admin(client, "a@a.fr")
    a.patch("/api/admin/parametres", json={"peage_eur_km": 0.1, "cout_km_eur": 0.3, "conso_l_100km": 25, "prix_carburant_eur_l": 2})
    valhalla.mode = "peage"
    e = itineraire(a, vehicule_complet(a)).json()["estimation"]
    assert e["peage_eur"] == 5.0 and e["cout_km_eur"] == 15.0 and e["carburant_eur"] == 25.0 and e["total_eur"] == 45.0


def test_warnings_from_service_are_passed_on(a, valhalla):
    valhalla.mode = "avertissement"
    assert "Restriction de hauteur sur le trajet" in itineraire(a, vehicule_complet(a)).json()["avertissements"]


def test_missing_axle_count_is_flagged(a, valhalla):
    vid = vehicule_complet(a, essieux="")
    assert any("essieux" in w for w in itineraire(a, vid).json()["avertissements"])


def test_service_down_is_reported_and_no_route_is_invented(a, valhalla):
    vid = vehicule_complet(a)
    valhalla.mode = "panne"
    r = itineraire(a, vid)
    assert r.status_code == 503 and "indisponible" in r.json()["detail"] and "geometrie" not in r.json()
    valhalla.mode = "erreur_serveur"
    assert itineraire(a, vid).status_code == 503
    valhalla.mode = "charabia"
    assert itineraire(a, vid).status_code == 503


def test_no_possible_route_for_gauge_is_a_clear_422(a, valhalla):
    valhalla.mode = "impossible"
    r = itineraire(a, vehicule_complet(a, hauteur_m=4.8))
    assert r.status_code == 422 and "gabarit" in r.json()["detail"]


def test_vehicle_without_gauge_cannot_route(a, valhalla):
    vid = a.post("/api/admin/vehicules", json={"plaque": "SA-111-SA"}).json()["id"]
    r = itineraire(a, vid)
    assert r.status_code == 422 and "hauteur" in r.json()["detail"] and valhalla.requetes == []


@pytest.mark.parametrize("points", [[(47.0, -1.0)], [(47.0, -1.0)] * 26, [(95.0, 0.0), (47.0, -1.0)]])
def test_points_validated(a, valhalla, points):
    assert itineraire(a, vehicule_complet(a), points).status_code == 422


def test_status_endpoint(a, valhalla):
    assert a.get("/api/admin/itineraires/etat").json() == {"disponible": True}
    valhalla.mode = "panne"
    assert a.get("/api/admin/itineraires/etat").json() == {"disponible": False}


def test_routing_requires_login_and_is_isolated(client, a, b, valhalla):
    vid = vehicule_complet(a)
    assert client.__class__(client.app).post("/api/admin/itineraires", json={}).status_code == 401
    assert itineraire(b, vid).status_code == 404  # le véhicule d'une autre société n'existe pas pour B
    assert valhalla.requetes == []


@pytest.mark.parametrize("champ,valeur", [("conso_l_100km", 2), ("conso_l_100km", 200), ("prix_carburant_eur_l", -1), ("peage_eur_km", 9), ("cout_km_eur", -0.1)])
def test_cost_settings_validated_and_admin_only(a, client, champ, valeur):
    assert a.patch("/api/admin/parametres", json={"peage_eur_km": 0.1}).status_code == 403
    make_admin(client, "a@a.fr")
    assert a.patch("/api/admin/parametres", json={champ: valeur}).status_code == 422
