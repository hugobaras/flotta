import time
from datetime import date

import pytest
from sqlalchemy import select, text

from app import matrices, plans, plans_api
from app.models import Order, Plan, Route, RouteStop
from app.routage import RouteurIndisponible
from test_optimisation import matrice_haversine
from helpers import make_admin

JOUR = "2026-11-02"


@pytest.fixture
def calcul(monkeypatch):
    """File de tâches simulée (les ids restent en attente) et matrices calculées sans Valhalla."""
    class Faux:
        file, panne_routage, panne_file = [], False, False

    f = Faux()
    f.file = []

    def enqueue(plan_id):
        if f.panne_file:
            raise ConnectionError("redis")
        f.file.append(plan_id)

    def fournisseur(locations, profils):
        if f.panne_routage:
            raise RouteurIndisponible("coupé")
        durees = matrice_haversine(locations)
        dist = [[round(d / 3600 * 60, 2) for d in row] for row in durees]  # km à 60 km/h
        return {cle: {"durations": durees, "distances": dist} for cle in profils}

    monkeypatch.setattr(plans_api, "enqueue_plan", enqueue)
    monkeypatch.setattr(matrices, "fournisseur", fournisseur)
    return f


def executer(client, plan_id):
    with client.Session() as db:
        return plans.executer(db, plan_id)


def camion(c, plaque, **extra):
    corps = {"plaque": plaque, "hauteur_m": 3.9, "largeur_m": 2.55, "longueur_m": 16.5, "ptac_kg": 40000, "essieux": 5,
             "capacite_kg": 12000, "palettes": 33, "capacite_m3": 80, **extra}
    r = c.post("/api/admin/vehicules", json=corps)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def depot(c, lat=47.2184, lng=-1.5536):
    return c.post("/api/admin/depots", json={"nom": "Dépôt", "adresse": "1 quai de la Fosse Nantes", "lat": lat, "lng": lng}).json()["id"]


def ajouter_commandes(client, company_id, n, localisees=True, jour=date(2026, 11, 2), **extra):
    with client.Session() as db:
        for i in range(n):
            db.add(Order(company_id=company_id, reference=f"C{company_id}-{i}", adresse=f"{i} rue Test", lat=47.2 + i * 0.01 if localisees else None,
                         lng=-1.55 + i * 0.01 if localisees else None, geo_statut="ok" if localisees else "introuvable", poids_kg=200,
                         palettes=1, volume_m3=2, date_livraison=jour, **extra))
        db.commit()


def lancer(c, **extra):
    r = c.post("/api/admin/plans", json={"jour": JOUR, "temps_max_s": 2, **extra})
    assert r.status_code == 202, r.text
    return r.json()["id"]


def test_plan_is_created_pending_and_queued_then_computed(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    ajouter_commandes(client, 1, 6)
    pid = lancer(a)
    assert calcul.file == [pid]
    attente = a.get(f"/api/admin/plans/{pid}").json()
    assert attente["statut"] == "en_attente" and attente["routes"] == []
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert d["statut"] == "termine" and d["progression"] == 100 and d["non_affectees"] == []
    assert sum(len(r["arrets"]) for r in d["routes"]) == 6
    r = d["routes"][0]
    assert r["plaque"] == "AA-100-AA" and r["distance_km"] > 0 and r["charge_kg"] == 1200 and r["retour_min"] > r["depart_min"]
    assert [x["ordre"] for x in r["arrets"]] == list(range(1, len(r["arrets"]) + 1))
    assert d["resume"]["km"] > 0 and d["resume"]["nb_tournees"] == 1 and d["resume"]["remplissage_pct"] == 10
    with client.Session() as db:
        assert {o.statut for o in db.scalars(select(Order))} == {"planifie"}


def test_plan_stores_matrices_for_later_recalculation(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    ajouter_commandes(client, 1, 3)
    pid = lancer(a)
    executer(client, pid)
    with client.Session() as db:
        m = db.get(Plan, pid).matrices
    prof = next(iter(m["profils"].values()))
    assert len(m["commandes"]) == 4 and len(prof["durations"]) == 4 and prof["vehicle_ids"]


def test_orders_without_position_are_listed_with_a_reason(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    ajouter_commandes(client, 1, 3)
    with client.Session() as db:
        db.add(Order(company_id=1, reference="SANS-GPS", adresse="rue inconnue", date_livraison=date(2026, 11, 2), geo_statut="introuvable"))
        db.commit()
    pid = lancer(a)
    executer(client, pid)
    non = a.get(f"/api/admin/plans/{pid}").json()["non_affectees"]
    assert [n["reference"] for n in non] == ["SANS-GPS"] and "non localisée" in non[0]["raison"]


def test_blocked_and_incomplete_vehicles_are_excluded_and_reported(a, client, calcul):
    camion(a, "OK-100-OK")
    camion(a, "BL-100-BL")
    a.post("/api/admin/vehicules", json={"plaque": "NG-100-NG"})  # sans gabarit
    with client.Session() as db:
        from app.models import Vehicle
        db.scalar(select(Vehicle).where(Vehicle.plaque == "BL-100-BL")).bloque = True
        db.commit()
    depot(a)
    ajouter_commandes(client, 1, 2)
    pid = lancer(a)
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    exclus = {e["plaque"]: e["raison"] for e in d["resume"]["vehicules_exclus"]}
    assert "bloqué" in exclus["BL-100-BL"] and "Gabarit incomplet" in exclus["NG-100-NG"]
    # les camions de test de la fixture (AA-111-AA, ZZ-999-ZZ) n'ont pas de gabarit non plus
    assert {r["plaque"] for r in d["routes"]} == {"OK-100-OK"}


def test_capacity_forces_several_trucks_and_leftovers_are_explained(a, client, calcul):
    camion(a, "AA-100-AA", capacite_kg=500)
    camion(a, "BB-100-BB", capacite_kg=500)
    depot(a)
    ajouter_commandes(client, 1, 7)  # 7 x 200 kg = 1400 kg pour 1000 kg de capacité
    pid = lancer(a, rotations_max=1)  # une seule sortie par camion : c'est la capacité d'une tournée qui est testée ici
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert len(d["routes"]) == 2 and all(r["charge_kg"] <= 500 for r in d["routes"])
    assert len(d["non_affectees"]) == 3 and all("Capacité" in n["raison"] for n in d["non_affectees"])


def test_plan_without_depot_fails_with_a_clear_message(a, client, calcul):
    camion(a, "AA-100-AA")
    ajouter_commandes(client, 1, 2)
    pid = lancer(a)
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert d["statut"] == "echec" and "dépôt" in d["message"]


def test_plan_without_orders_or_vehicles_fails_clearly(a, client, calcul):
    depot(a)
    pid = lancer(a)
    executer(client, pid)
    assert "Aucune commande" in a.get(f"/api/admin/plans/{pid}").json()["message"]
    ajouter_commandes(client, 1, 2)
    pid2 = lancer(a)
    executer(client, pid2)
    assert "Aucun véhicule" in a.get(f"/api/admin/plans/{pid2}").json()["message"]


def test_routing_service_down_marks_plan_failed_without_inventing_times(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    ajouter_commandes(client, 1, 3)
    calcul.panne_routage = True
    pid = lancer(a)
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert d["statut"] == "echec" and "indisponible" in d["message"] and d["routes"] == []
    with client.Session() as db:
        assert {o.statut for o in db.scalars(select(Order))} == {"a_planifier"}  # rien n'est marqué planifié


def test_task_queue_down_returns_503_and_leaves_no_ghost_plan(a, client, calcul):
    calcul.panne_file = True
    r = a.post("/api/admin/plans", json={"jour": JOUR})
    assert r.status_code == 503
    assert a.get("/api/admin/plans").json() == []


@pytest.mark.parametrize("extra", [{"temps_max_s": 0}, {"temps_max_s": 500}, {"duree_max_min": 10}, {"duree_max_min": 2000}, {"jour": "pas une date"}])
def test_plan_parameters_validated(a, calcul, extra):
    assert a.post("/api/admin/plans", json={"jour": JOUR, **extra}).status_code == 422


def test_100_orders_8_trucks_under_60_seconds_with_leftovers_explained(a, client, calcul):
    for i in range(8):
        camion(a, f"CT-{100 + i}-AA")
    depot(a)
    ajouter_commandes(client, 1, 100)
    pid = lancer(a, temps_max_s=10)
    debut = time.time()
    executer(client, pid)
    assert time.time() - debut < 60
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert d["statut"] == "termine"
    assert sum(len(r["arrets"]) for r in d["routes"]) + len(d["non_affectees"]) == 100
    assert all(n["raison"] for n in d["non_affectees"])


def test_plans_are_isolated_between_companies(a, b, client, calcul):
    camion(a, "AA-100-AA")
    camion(b, "BB-100-BB")
    depot(a)
    depot(b)
    ajouter_commandes(client, 1, 3)
    ajouter_commandes(client, 2, 3)
    pid = lancer(a)
    executer(client, pid)
    assert b.get("/api/admin/plans").json() == []
    assert b.get(f"/api/admin/plans/{pid}").status_code == 404
    assert b.delete(f"/api/admin/plans/{pid}").status_code == 404
    refs = {s["reference"] for r in a.get(f"/api/admin/plans/{pid}").json()["routes"] for s in r["arrets"]}
    assert refs and all(x.startswith("C1-") for x in refs)  # jamais de commande de la société B
    vid_b = b.get("/api/admin/vehicules").json()[0]["id"]
    assert a.post("/api/admin/plans", json={"jour": JOUR, "vehicle_ids": [vid_b]}).status_code == 404
    depot_b = b.get("/api/admin/depots").json()[0]["id"]
    assert a.post("/api/admin/plans", json={"jour": JOUR, "depot_id": depot_b}).status_code == 404


def test_delete_plan_removes_its_routes_and_stops(a, client, calcul):
    with client.Session() as db:  # SQLite n'applique pas les clés étrangères par défaut, Postgres oui : on reproduit Postgres
        db.execute(text("PRAGMA foreign_keys=ON"))
    camion(a, "AA-100-AA")
    depot(a)
    ajouter_commandes(client, 1, 3)
    pid = lancer(a)
    executer(client, pid)
    assert a.delete(f"/api/admin/plans/{pid}").status_code == 204
    with client.Session() as db:
        assert db.scalars(select(Route)).all() == [] and db.scalars(select(RouteStop)).all() == []


def test_plan_routes_require_login(client):
    for method, url in [("get", "/api/admin/plans"), ("post", "/api/admin/plans"), ("get", "/api/admin/plans/1"), ("delete", "/api/admin/plans/1")]:
        assert getattr(client, method)(url).status_code == 401


# ---------------------------------------------------------------- Rotations


def commandes_de_8_palettes(client, n=3):
    with client.Session() as db:
        for i in range(n):
            db.add(Order(company_id=1, reference=f"R{i}", adresse=f"{i} rue Test", lat=47.22 + i * 0.01, lng=-1.55, geo_statut="ok", poids_kg=800,
                         palettes=8, volume_m3=10, date_livraison=date(2026, 11, 2)))
        db.commit()


def test_plan_uses_rotations_when_one_trip_cannot_carry_everything(a, client, calcul):
    camion(a, "AA-100-AA", palettes=10)
    depot(a)
    commandes_de_8_palettes(client)
    seul = lancer(a, rotations_max=1)
    executer(client, seul)
    assert len(a.get(f"/api/admin/plans/{seul}").json()["non_affectees"]) == 2
    pid = lancer(a)  # 3 rotations par défaut
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert d["non_affectees"] == [] and d["alertes"] == []
    (r,) = d["routes"]
    assert [x["rotation"] for x in r["arrets"]] == [1, 2, 3]
    assert [(x["numero"], x["charge_palettes"]) for x in r["rotations"]] == [(1, 8), (2, 8), (3, 8)]
    sorties = [x["depart_min"] for x in r["rotations"]]
    retours = [x["retour_min"] for x in r["rotations"]]
    assert all(sorties[i + 1] >= retours[i] + 45 - 1e-6 for i in range(2))  # rechargement de 45 min respecté dans le plan enregistré
    assert d["resume"]["nb_rotations"] == 3 and d["resume"]["nb_tournees"] == 1


def test_loading_time_and_rotation_count_are_validated(a):
    assert a.post("/api/admin/plans", json={"jour": JOUR, "rotations_max": 4}).status_code == 422
    assert a.post("/api/admin/plans", json={"jour": JOUR, "rechargement_min": 5}).status_code == 422


def test_rotations_survive_undo_redo_and_old_snapshots_default_to_one_rotation(a, client, calcul):
    camion(a, "AA-100-AA", palettes=10)
    depot(a)
    commandes_de_8_palettes(client)
    pid = lancer(a)
    executer(client, pid)
    avant = a.get(f"/api/admin/plans/{pid}").json()["routes"][0]["arrets"]
    with client.Session() as db:
        plan = db.get(Plan, pid)
        etat = plans.charger_etat(db, plan)
        for r in etat["routes"]:
            for ar in r["arrets"]:
                ar.pop("rotation")  # un instantané antérieur aux rotations
        plans.ecrire_etat(db, plan, etat)
        db.commit()
    apres = a.get(f"/api/admin/plans/{pid}").json()
    assert {x["rotation"] for x in apres["routes"][0]["arrets"]} == {1} and len(avant) == len(apres["routes"][0]["arrets"]) == 3
    assert [x["type"] for x in apres["alertes"]] == ["surcharge"]  # 24 palettes dans un camion de 10 : la surcharge est signalée
