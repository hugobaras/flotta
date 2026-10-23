import time

import pytest
from sqlalchemy import select

from app import plans, plans_api
from app.models import Order, Plan, PlanSnapshot
from test_plans import JOUR, ajouter_commandes, calcul, camion, depot, executer, lancer  # noqa: F401


@pytest.fixture
def plan(a, client, calcul):  # noqa: F811
    """Plan calculé : 2 camions, 8 commandes réparties sur deux zones."""
    camion(a, "AA-100-AA", capacite_kg=1500)  # 8 x 300 kg = 2400 kg : deux camions sont nécessaires
    camion(a, "BB-100-BB", capacite_kg=1500)
    depot(a)
    with client.Session() as db:
        from app.models import Order as O
        from datetime import date
        for i in range(8):
            zone = 0 if i < 4 else 1
            db.add(O(company_id=1, reference=f"C{i}", adresse=f"{i} rue", lat=47.2 + zone * 0.5 + i * 0.005, lng=-1.55 + zone * 0.5, geo_statut="ok",
                     poids_kg=300, palettes=2, volume_m3=3, date_livraison=date(2026, 11, 2)))
        db.commit()
    pid = lancer(a, temps_max_s=3)
    executer(client, pid)
    d = a.get(f"/api/admin/plans/{pid}").json()
    assert d["statut"] == "termine"
    return pid


def get(c, pid):
    return c.get(f"/api/admin/plans/{pid}").json()


def route_de(d, plaque):
    return next(r for r in d["routes"] if r["plaque"] == plaque)


def refs(r):
    return [s["reference"] for s in r["arrets"]]


def deplacer(c, pid, order_id, vehicle_id, position=None):
    return c.post(f"/api/admin/plans/{pid}/deplacer", json={"order_id": order_id, "vehicle_id": vehicle_id, "position": position})


def une_commande(d, plaque):
    r = route_de(d, plaque)
    return r["arrets"][0]["order_id"], r["vehicle_id"]


def test_plan_detail_has_references_for_comparison_and_no_alerts(a, plan):
    d = get(a, plan)
    assert d["reference"]["km"] == d["resume"]["km"] and d["alertes"] == []
    assert d["peut_annuler"] is False and d["peut_retablir"] is False
    assert len(d["routes"]) == 2 and sum(len(r["arrets"]) for r in d["routes"]) == 8


def test_move_stop_to_other_truck_recalculates_times_and_indicators(a, plan):
    avant = get(a, plan)
    oid, _ = une_commande(avant, "AA-100-AA")
    cible = route_de(avant, "BB-100-BB")
    r = deplacer(a, plan, oid, cible["vehicle_id"], 0)
    assert r.status_code == 200, r.text
    d = r.json()
    assert oid in [s["order_id"] for s in route_de(d, "BB-100-BB")["arrets"]] and route_de(d, "BB-100-BB")["arrets"][0]["order_id"] == oid
    assert len(route_de(d, "BB-100-BB")["arrets"]) == len(cible["arrets"]) + 1
    assert route_de(d, "BB-100-BB")["charge_kg"] == cible["charge_kg"] + 300
    assert d["resume"]["km"] != avant["resume"]["km"] and d["reference"]["km"] == avant["resume"]["km"]  # la référence reste le plan d'origine
    assert d["peut_annuler"] is True
    arrivees = [s["arrivee_min"] for s in route_de(d, "BB-100-BB")["arrets"]]
    assert arrivees == sorted(arrivees)


def test_reorder_inside_the_same_truck(a, plan):
    avant = get(a, plan)
    r = route_de(avant, "AA-100-AA")
    dernier = r["arrets"][-1]["order_id"]
    d = deplacer(a, plan, dernier, r["vehicle_id"], 0).json()
    assert route_de(d, "AA-100-AA")["arrets"][0]["order_id"] == dernier and len(route_de(d, "AA-100-AA")["arrets"]) == len(r["arrets"])


def test_remove_from_plan_and_put_back(a, plan):
    avant = get(a, plan)
    oid, vid = une_commande(avant, "AA-100-AA")
    d = deplacer(a, plan, oid, None).json()
    assert [n["order_id"] for n in d["non_affectees"]] == [oid]
    assert d["resume"]["nb_non_affectees"] == 1 and oid not in [s["order_id"] for r in d["routes"] for s in r["arrets"]]
    d = deplacer(a, plan, oid, vid, None).json()
    assert d["non_affectees"] == [] and oid in [s["order_id"] for s in route_de(d, "AA-100-AA")["arrets"]]


def test_order_status_follows_the_plan(a, client, plan):
    oid, _ = une_commande(get(a, plan), "AA-100-AA")
    deplacer(a, plan, oid, None)
    with client.Session() as db:
        assert db.get(Order, oid).statut == "a_planifier"


def test_undo_redo_and_redo_branch_is_cleared(a, plan):
    d0 = get(a, plan)
    oid, _ = une_commande(d0, "AA-100-AA")
    vb = route_de(d0, "BB-100-BB")["vehicle_id"]
    deplacer(a, plan, oid, vb, 0)
    d_apres = get(a, plan)
    d_annule = a.post(f"/api/admin/plans/{plan}/annuler").json()
    assert refs(route_de(d_annule, "AA-100-AA")) == refs(route_de(d0, "AA-100-AA")) and d_annule["peut_retablir"] is True
    assert d_annule["resume"]["km"] == d0["resume"]["km"]
    d_retabli = a.post(f"/api/admin/plans/{plan}/retablir").json()
    assert refs(route_de(d_retabli, "BB-100-BB")) == refs(route_de(d_apres, "BB-100-BB"))
    a.post(f"/api/admin/plans/{plan}/annuler")
    deplacer(a, plan, oid, None)  # nouvelle modification : l'ancien « rétablir » disparaît
    assert get(a, plan)["peut_retablir"] is False
    assert a.post(f"/api/admin/plans/{plan}/retablir").status_code == 409


def test_cannot_undo_before_the_first_state(a, plan):
    assert a.post(f"/api/admin/plans/{plan}/annuler").status_code == 409


def test_locked_stop_and_locked_route_cannot_be_moved(a, plan):
    d = get(a, plan)
    oid, va = une_commande(d, "AA-100-AA")
    vb = route_de(d, "BB-100-BB")["vehicle_id"]
    assert a.post(f"/api/admin/plans/{plan}/verrouiller", json={"order_id": oid, "verrouille": True}).status_code == 200
    r = deplacer(a, plan, oid, vb, 0)
    assert r.status_code == 409 and "verrouillé" in r.json()["detail"]
    a.post(f"/api/admin/plans/{plan}/verrouiller", json={"order_id": oid, "verrouille": False})
    assert deplacer(a, plan, oid, vb, 0).status_code == 200
    a.post(f"/api/admin/plans/{plan}/verrouiller", json={"vehicle_id": vb, "verrouille": True})
    autre, _ = une_commande(get(a, plan), "AA-100-AA")
    assert deplacer(a, plan, autre, vb, 0).status_code == 409  # vers une tournée verrouillée
    sortant = route_de(get(a, plan), "BB-100-BB")["arrets"][0]["order_id"]
    assert deplacer(a, plan, sortant, va, 0).status_code == 409  # depuis une tournée verrouillée
    assert route_de(get(a, plan), "BB-100-BB")["verrouille"] is True


def test_alerts_overload_late_and_incompatibility(a, client, plan):
    d = get(a, plan)
    vb = route_de(d, "BB-100-BB")["vehicle_id"]
    with client.Session() as db:
        db.get(Order, une_commande(d, "AA-100-AA")[0]).fenetre_fin = "06:10"
        db.get(Order, une_commande(d, "AA-100-AA")[0]).frigo = True
        db.commit()
    oid, _ = une_commande(d, "AA-100-AA")
    out = deplacer(a, plan, oid, vb, 99).json()  # en dernier : forcément en retard, frigo sur camion sans frigo
    types = {x["type"] for x in out["alertes"]}
    assert {"retard", "incompatible"} <= types
    assert all(x["message"] for x in out["alertes"]) and out["resume"]["nb_alertes"] == len(out["alertes"])


def test_overload_alert_appears_when_a_truck_gets_too_full(a, client, plan):
    d = get(a, plan)
    with client.Session() as db:
        from app.models import Vehicle
        db.scalar(select(Vehicle).where(Vehicle.plaque == "BB-100-BB")).capacite_kg = 1000
        db.commit()
    va = route_de(d, "AA-100-AA")
    out = None
    for s in va["arrets"]:
        out = deplacer(a, plan, s["order_id"], route_de(d, "BB-100-BB")["vehicle_id"]).json()
    assert any(x["type"] == "surcharge" and "BB-100-BB" in x["message"] for x in out["alertes"])


def test_edit_is_fast_on_a_big_plan(a, client, calcul):
    for i in range(8):
        camion(a, f"CT-{100 + i}-AA")
    depot(a)
    ajouter_commandes(client, 1, 100)
    pid = lancer(a, temps_max_s=2)
    executer(client, pid)
    d = get(a, pid)
    utilisees = [r for r in d["routes"] if r["arrets"]]
    oid = utilisees[0]["arrets"][0]["order_id"]
    debut = time.time()
    r = deplacer(a, pid, oid, utilisees[1]["vehicle_id"], 0)
    assert r.status_code == 200 and time.time() - debut < 1.0


def test_unknown_order_vehicle_or_bad_payload(a, plan):
    d = get(a, plan)
    assert deplacer(a, plan, 999999, d["routes"][0]["vehicle_id"]).status_code == 404
    oid, _ = une_commande(d, "AA-100-AA")
    assert deplacer(a, plan, oid, 999999).status_code == 404
    assert a.post(f"/api/admin/plans/{plan}/deplacer", json={"order_id": oid, "position": -1}).status_code == 422
    assert a.post(f"/api/admin/plans/{plan}/verrouiller", json={}).status_code == 422


def test_versions_are_independent_copies(a, plan):
    d0 = get(a, plan)
    r = a.post(f"/api/admin/plans/{plan}/versions", json={"nom": "Plan du matin"})
    assert r.status_code == 201
    copie = r.json()
    assert copie["nom"] == "Plan du matin" and copie["id"] != plan and copie["statut"] == "termine"
    assert [refs(r) for r in copie["routes"]] == [refs(r) for r in d0["routes"]]
    oid, _ = une_commande(d0, "AA-100-AA")
    deplacer(a, copie["id"], oid, None)
    assert get(a, plan)["non_affectees"] == []  # l'original n'a pas bougé
    assert {v["id"] for v in get(a, plan)["versions"]} == {plan, copie["id"]}
    assert get(a, plan)["parametres"] == copie["parametres"]
    assert a.post(f"/api/admin/plans/{plan}/versions", json={"nom": ""}).status_code == 422


def test_reoptimisation_keeps_locked_routes_and_stops(a, client, plan):
    d = get(a, plan)
    locked_vid = route_de(d, "BB-100-BB")["vehicle_id"]
    a.post(f"/api/admin/plans/{plan}/verrouiller", json={"vehicle_id": locked_vid, "verrouille": True})
    avant_verrouillee = refs(route_de(get(a, plan), "BB-100-BB"))
    oid, va = une_commande(d, "AA-100-AA")
    a.post(f"/api/admin/plans/{plan}/verrouiller", json={"order_id": oid, "verrouille": True})
    deplacer_libre = [s["order_id"] for s in route_de(d, "AA-100-AA")["arrets"] if s["order_id"] != oid][0]
    a.post(f"/api/admin/plans/{plan}/deplacer", json={"order_id": deplacer_libre, "vehicle_id": None})
    r = a.post(f"/api/admin/plans/{plan}/reoptimiser")
    assert r.status_code == 202 and get(a, plan)["statut"] == "en_attente"
    executer(client, plan)
    out = get(a, plan)
    assert out["statut"] == "termine" and out["message"] is None
    assert refs(route_de(out, "BB-100-BB")) == avant_verrouillee  # tournée verrouillée intacte
    assert oid in [s["order_id"] for s in route_de(out, "AA-100-AA")["arrets"]]  # arrêt verrouillé resté sur son camion
    assert deplacer_libre in [s["order_id"] for r in out["routes"] for s in r["arrets"]]  # la commande retirée est replacée
    assert out["peut_annuler"] is True
    a.post(f"/api/admin/plans/{plan}/annuler")
    assert [n["order_id"] for n in get(a, plan)["non_affectees"]] == [deplacer_libre]  # l'annulation restaure l'état d'avant


def test_reoptimisation_with_everything_locked_explains_itself_and_keeps_the_plan(a, client, plan):
    for v in {r["vehicle_id"] for r in get(a, plan)["routes"]}:
        a.post(f"/api/admin/plans/{plan}/verrouiller", json={"vehicle_id": v, "verrouille": True})
    avant = get(a, plan)
    a.post(f"/api/admin/plans/{plan}/reoptimiser")
    executer(client, plan)
    out = get(a, plan)
    assert out["statut"] == "termine" and "verrouillées" in out["message"]
    assert [refs(r) for r in out["routes"]] == [refs(r) for r in avant["routes"]]


def test_reoptimisation_queue_down_restores_the_plan(a, plan, monkeypatch):
    def panne(_):
        raise ConnectionError("redis")
    monkeypatch.setattr(plans_api, "enqueue_plan", panne)
    assert a.post(f"/api/admin/plans/{plan}/reoptimiser").status_code == 503
    assert get(a, plan)["statut"] == "termine"


def test_editing_requires_a_finished_plan(a, calcul):
    pid = lancer(a)  # jamais calculé
    for url, corps in [("deplacer", {"order_id": 1}), ("verrouiller", {"vehicle_id": 1}), ("annuler", None), ("retablir", None), ("versions", {"nom": "x"})]:
        r = a.post(f"/api/admin/plans/{pid}/{url}", json=corps) if corps is not None else a.post(f"/api/admin/plans/{pid}/{url}")
        assert r.status_code == 409, url


def test_editing_is_isolated_between_companies(a, b, plan):
    d = get(a, plan)
    oid, vid = une_commande(d, "AA-100-AA")
    for url, corps in [("deplacer", {"order_id": oid, "vehicle_id": vid}), ("verrouiller", {"vehicle_id": vid}), ("annuler", None),
                       ("retablir", None), ("versions", {"nom": "x"}), ("reoptimiser", None)]:
        r = b.post(f"/api/admin/plans/{plan}/{url}", json=corps) if corps is not None else b.post(f"/api/admin/plans/{plan}/{url}")
        assert r.status_code == 404, url
    assert get(a, plan)["peut_annuler"] is False


def test_deleting_a_plan_removes_its_history(a, client, plan):
    oid, _ = une_commande(get(a, plan), "AA-100-AA")
    deplacer(a, plan, oid, None)
    a.delete(f"/api/admin/plans/{plan}")
    with client.Session() as db:
        assert db.scalars(select(PlanSnapshot)).all() == []


def test_edit_routes_require_login(client):
    for url in ("deplacer", "verrouiller", "annuler", "retablir", "versions", "reoptimiser"):
        assert client.post(f"/api/admin/plans/1/{url}", json={}).status_code == 401
