"""Temps de conduite dans les plans : conducteurs, historiques, pauses insérées, alertes d'infraction."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import ActiviteConducteur, Order
from test_plans import calcul, camion, depot, executer  # noqa: F401
from test_plans_edition import deplacer, get, route_de

@pytest.fixture(autouse=True)
def horloge(monkeypatch):
    """Les historiques sont datés de novembre 2026 : on fige « maintenant » au vendredi 6 novembre 2026."""
    from datetime import datetime, timezone
    from app import conducteurs
    monkeypatch.setattr(conducteurs, "maintenant", lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc))


LUNDI = "2026-11-02"  # un lundi (heure d'hiver : Paris = UTC+1)
VENDREDI = "2026-11-06"


def conducteur(c, nom="Karim Benali", **extra):
    r = c.post("/api/admin/conducteurs", json={"nom": nom, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def declarer(c, cid, *activites):
    r = c.post(f"/api/admin/conducteurs/{cid}/activites", json={"activites": [{"type": t, "debut": d, "fin": f} for t, d, f in activites]})
    assert r.status_code == 201, r.text
    return r.json()


def commande(client, ref, lat, lng, jour=date(2026, 11, 2), company=1, **extra):
    with client.Session() as db:
        o = Order(company_id=company, reference=ref, adresse=f"{ref} rue", lat=lat, lng=lng, geo_statut="ok", poids_kg=100, palettes=1, volume_m3=1,
                  duree_service_min=extra.pop("service", 15), date_livraison=jour, **extra)
        db.add(o)
        db.commit()
        return o.id


def planifier(c, jour=LUNDI, **extra):
    r = c.post("/api/admin/plans", json={"jour": jour, "temps_max_s": 2, **extra})
    assert r.status_code == 202, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- Activités déclarées


def test_activity_routes_require_login(client):
    for method, url in [("get", "/api/admin/conducteurs/1/activites"), ("post", "/api/admin/conducteurs/1/activites"),
                        ("delete", "/api/admin/conducteurs/1/activites/1"), ("get", "/api/admin/conducteurs/1/compteurs")]:
        assert getattr(client, method)(url).status_code == 401


def test_declare_list_and_delete_activities(a):
    d = conducteur(a)["id"]
    cree = declarer(a, d, ("conduite", "2026-11-04T07:00:00+01:00", "2026-11-04T11:30:00+01:00"), ("repos", "2026-11-04T11:30:00+01:00", "2026-11-04T12:15:00+01:00"))
    assert len(cree) == 2 and cree[0]["type"] == "conduite"
    assert [x["type"] for x in a.get(f"/api/admin/conducteurs/{d}/activites").json()] == ["conduite", "repos"]
    assert a.delete(f"/api/admin/conducteurs/{d}/activites/{cree[0]['id']}").status_code == 204
    assert len(a.get(f"/api/admin/conducteurs/{d}/activites").json()) == 1


@pytest.mark.parametrize("corps", [
    {"type": "sieste", "debut": "2026-10-22T07:00:00+02:00", "fin": "2026-10-22T08:00:00+02:00"},
    {"type": "conduite", "debut": "2026-10-22T08:00:00+02:00", "fin": "2026-10-22T07:00:00+02:00"},
    {"type": "conduite", "debut": "2026-10-22T07:00:00", "fin": "2026-10-22T08:00:00"},  # sans fuseau
    {"type": "conduite", "debut": "2026-10-20T07:00:00+02:00", "fin": "2026-10-21T09:00:00+02:00"},  # plus de 24 h
])
def test_activity_validation(a, corps):
    d = conducteur(a)["id"]
    assert a.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": [corps]}).status_code == 422


def test_activities_too_old_or_in_the_far_future_are_refused(a):
    d = conducteur(a)["id"]
    ancien = {"type": "conduite", "debut": "2020-01-01T07:00:00+01:00", "fin": "2020-01-01T08:00:00+01:00"}
    assert a.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": [ancien]}).status_code == 422
    futur = {"type": "conduite", "debut": "2099-01-01T07:00:00+01:00", "fin": "2099-01-01T08:00:00+01:00"}
    assert a.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": [futur]}).status_code == 422
    assert a.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": []}).status_code == 422


def test_overlapping_activities_are_refused(a):
    d = conducteur(a)["id"]
    declarer(a, d, ("conduite", "2026-10-22T07:00:00+02:00", "2026-10-22T09:00:00+02:00"))
    chevauche = {"type": "travail", "debut": "2026-10-22T08:00:00+02:00", "fin": "2026-10-22T10:00:00+02:00"}
    assert a.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": [chevauche]}).status_code == 409
    entre_elles = [{"type": "travail", "debut": "2026-10-21T08:00:00+02:00", "fin": "2026-10-21T10:00:00+02:00"},
                   {"type": "conduite", "debut": "2026-10-21T09:00:00+02:00", "fin": "2026-10-21T11:00:00+02:00"}]
    assert a.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": entre_elles}).status_code == 409
    assert declarer(a, d, ("repos", "2026-10-22T09:00:00+02:00", "2026-10-22T09:45:00+02:00"))  # bout à bout : autorisé


def test_activities_are_isolated_between_companies(a, b):
    d = conducteur(a)["id"]
    cree = declarer(a, d, ("conduite", "2026-10-22T07:00:00+02:00", "2026-10-22T09:00:00+02:00"))
    assert b.get(f"/api/admin/conducteurs/{d}/activites").status_code == 404
    assert b.post(f"/api/admin/conducteurs/{d}/activites", json={"activites": [{"type": "travail", "debut": "2026-10-21T08:00:00+02:00", "fin": "2026-10-21T09:00:00+02:00"}]}).status_code == 404
    assert b.delete(f"/api/admin/conducteurs/{d}/activites/{cree[0]['id']}").status_code == 404
    assert b.get(f"/api/admin/conducteurs/{d}/compteurs").status_code == 404


def test_counters_endpoint_reflects_the_declared_history(a):
    d = conducteur(a)["id"]
    declarer(a, d, ("conduite", "2026-10-22T07:00:00+02:00", "2026-10-22T10:00:00+02:00"))
    r = a.get(f"/api/admin/conducteurs/{d}/compteurs", params={"instant": "2026-10-22T10:00:00+02:00"}).json()
    assert r["conduite_continue_min"] == 90 and r["pause_necessaire_min"] == 45
    assert r["conduite_jour_normale_min"] == 540 - 180 and r["conduite_jour_min"] == 600 - 180 and r["extensions_restantes"] == 2
    assert r["conduite_semaine_min"] == 3360 - 180 and r["infractions"] == []
    assert a.get(f"/api/admin/conducteurs/{d}/compteurs", params={"instant": "2026-10-22T10:00:00"}).status_code == 422


def test_counters_report_infractions_found_in_the_history(a):
    d = conducteur(a)["id"]
    declarer(a, d, ("conduite", "2026-10-22T06:00:00+02:00", "2026-10-22T12:00:00+02:00"))  # 6 h sans pause
    r = a.get(f"/api/admin/conducteurs/{d}/compteurs", params={"instant": "2026-10-22T12:00:00+02:00"}).json()
    assert [i["code"] for i in r["infractions"]] == ["PAUSE_MANQUANTE"]


# ---------------------------------------------------------------- Plans avec temps de conduite


def test_plan_assigns_the_usual_driver_and_exposes_remaining_times(a, client, calcul):
    vid = camion(a, "AA-100-AA")
    depot(a)
    d = conducteur(a, vehicule_habituel_id=vid)
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a)
    executer(client, pid)
    plan = get(a, pid)
    assert route_de(plan, "AA-100-AA")["conducteur_id"] == d["id"] and route_de(plan, "AA-100-AA")["plafond_conduite_min"] == 600
    info = next(x for x in plan["conducteurs"] if x["id"] == d["id"])
    assert info["vehicle_id"] == vid and info["conduite_jour_normale_min"] == 540 and info["conduite_semaine_min"] == 3360 and info["extensions_restantes"] == 2


def test_plan_without_driver_applies_the_rules_per_route(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a)
    executer(client, pid)
    r = route_de(get(a, pid), "AA-100-AA")
    assert r["conducteur_id"] is None and r["plafond_conduite_min"] == 540 and r["conduite_min"] > 0 and r["pauses"] == []


def test_long_route_gets_a_mandatory_break_visible_in_the_plan(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    commande(client, "LOIN", 48.6, -1.55)  # environ 150 km : 3 h 15 à l'aller, 6 h 30 aller-retour
    pid = planifier(a)
    executer(client, pid)
    plan = get(a, pid)
    r = route_de(plan, "AA-100-AA")
    assert len(r["arrets"]) == 1 and len(r["pauses"]) == 1
    debut, fin = r["pauses"][0]
    assert fin - debut == 45
    assert abs((r["retour_min"] - r["depart_min"]) - (r["conduite_min"] + 45 + 15)) < 0.5  # conduite + pause + service
    assert plan["alertes"] == []


def test_a_far_order_beyond_the_daily_limit_is_left_out_with_the_driving_reason(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    commande(client, "TRESLOIN", 49.6, -1.55)  # plus de 9 h de conduite aller-retour
    pid = planifier(a)
    executer(client, pid)
    plan = get(a, pid)
    assert plan["routes"][0]["arrets"] == [] and plan["non_affectees"][0]["raison"].startswith("Temps de conduite")


def test_manual_edit_creating_an_infraction_is_flagged_red(a, client, calcul):
    camion(a, "AA-100-AA", capacite_kg=50000)
    camion(a, "BB-100-BB", capacite_kg=50000)
    depot(a)
    commande(client, "NEAR", 47.3, -1.55)
    loin = commande(client, "TRESLOIN", 49.6, -1.55)
    pid = planifier(a)
    executer(client, pid)
    plan = get(a, pid)
    assert [n["reference"] for n in plan["non_affectees"]] == ["TRESLOIN"] and plan["resume"]["nb_infractions"] == 0
    vid = route_de(plan, "BB-100-BB")["vehicle_id"]
    out = deplacer(a, pid, loin, vid).json()
    infractions = [x for x in out["alertes"] if x["gravite"] == "infraction"]
    assert infractions and infractions[0]["type"] == "conduite_jour" and "BB-100-BB" in infractions[0]["message"]
    assert out["resume"]["nb_infractions"] >= 1 and len(route_de(out, "BB-100-BB")["pauses"]) == 2  # plus de 9 h : deux pauses


def test_between_9_and_10_hours_is_a_warning_extension_not_an_infraction(a, client, calcul):
    camion(a, "AA-100-AA", capacite_kg=50000)
    camion(a, "BB-100-BB", capacite_kg=50000)
    depot(a)
    commande(client, "NEAR", 47.3, -1.55)
    moyen = commande(client, "MOYEN", 49.15, -1.55)  # 9 h 20 aller-retour environ
    pid = planifier(a)
    executer(client, pid)
    plan = get(a, pid)
    assert [n["reference"] for n in plan["non_affectees"]] == ["MOYEN"]
    out = deplacer(a, pid, moyen, route_de(plan, "BB-100-BB")["vehicle_id"]).json()
    assert [x["type"] for x in out["alertes"] if x["gravite"] == "infraction"] == []
    assert 540 < route_de(out, "BB-100-BB")["conduite_min"] <= 600
    assert any(x["type"] == "extension" and x["gravite"] == "avertissement" for x in out["alertes"])


def test_driver_with_little_weekly_time_left_limits_the_route(a, client, calcul):
    vid = camion(a, "AA-100-AA")
    depot(a)
    d = conducteur(a, vehicule_habituel_id=vid)["id"]
    declarer(a, d, *[("conduite", f"2026-11-0{j}T06:00:00+01:00", f"2026-11-0{j}T19:30:00+01:00") for j in (2, 3, 4, 5)])  # 54 h du lundi au jeudi
    for ref, lat in (("A", 47.4), ("B", 47.9)):
        commande(client, ref, lat, -1.55, jour=date(2026, 11, 6))
    pid = planifier(a, jour=VENDREDI)
    executer(client, pid)
    plan = get(a, pid)
    info = next(x for x in plan["conducteurs"] if x["id"] == d)
    assert info["conduite_semaine_min"] == 3360 - 54 * 60  # 2 h de conduite hebdomadaire restantes
    r = route_de(plan, "AA-100-AA")
    assert r["conduite_min"] <= 120 + 1 and len(plan["non_affectees"]) >= 1  # le plus lointain ne tient pas
    assert all(n["raison"].startswith("Temps de conduite") or "Capacité" in n["raison"] for n in plan["non_affectees"])


def test_driver_who_finished_late_yesterday_starts_late(a, client, calcul):
    vid = camion(a, "AA-100-AA")
    depot(a)
    d = conducteur(a, vehicule_habituel_id=vid)["id"]
    declarer(a, d, ("travail", "2026-11-01T13:00:00+01:00", "2026-11-01T23:00:00+01:00"))  # repos de 11 h : départ possible à 10 h
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a)
    executer(client, pid)
    assert route_de(get(a, pid), "AA-100-AA")["depart_min"] >= 10 * 60 - 1e-6


def test_extensions_already_used_cap_the_driver_at_9_hours(a, client, calcul):
    vid = camion(a, "AA-100-AA")
    depot(a)
    d = conducteur(a, vehicule_habituel_id=vid)["id"]
    jours = [("2026-11-02", "06:00", "10:00"), ("2026-11-03", "06:00", "10:00")]  # deux journées de 10 h de conduite (lundi, mardi)
    declarer(a, d, *[("conduite", f"{j}T{debut}:00+01:00", f"{j}T{fin}:00+01:00") for j, debut, fin in [("2026-11-02", "04:00", "14:00"), ("2026-11-03", "04:00", "14:00")]])
    commande(client, "C1", 47.25, -1.55, jour=date(2026, 11, 4))
    pid = planifier(a, jour="2026-11-04")
    executer(client, pid)
    plan = get(a, pid)
    info = next(x for x in plan["conducteurs"] if x["id"] == d)
    assert info["extensions_restantes"] == 0 and info["conduite_jour_min"] == 540
    assert route_de(plan, "AA-100-AA")["plafond_conduite_min"] == 540


# ---------------------------------------------------------------- Affectation à la main


def test_assign_and_unassign_a_driver_with_history(a, client, calcul):
    v1, v2 = camion(a, "AA-100-AA"), camion(a, "BB-100-BB")
    depot(a)
    d1, d2 = conducteur(a, "Sophie Lambert")["id"], conducteur(a, "Julien Moreau")["id"]
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a)
    executer(client, pid)
    out = a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1, "conducteur_id": d1}).json()
    assert route_de(out, "AA-100-AA")["conducteur_id"] == d1 and out["peut_annuler"] is True
    assert a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v2, "conducteur_id": d1}).status_code == 409  # déjà affecté ailleurs
    assert a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v2, "conducteur_id": d2}).status_code == 200
    out = a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1, "conducteur_id": None}).json()
    assert route_de(out, "AA-100-AA")["conducteur_id"] is None
    retour = a.post(f"/api/admin/plans/{pid}/annuler").json()
    assert route_de(retour, "AA-100-AA")["conducteur_id"] == d1


def test_assigning_a_driver_out_of_hours_raises_an_infraction(a, client, calcul):
    v1 = camion(a, "AA-100-AA")
    depot(a)
    d = conducteur(a)["id"]
    declarer(a, d, *[("conduite", f"2026-11-0{j}T06:00:00+01:00", f"2026-11-0{j}T19:55:00+01:00") for j in (2, 3, 4, 5)])  # 55 h 40
    commande(client, "C1", 47.6, -1.55, jour=date(2026, 11, 6))
    pid = planifier(a, jour=VENDREDI)
    executer(client, pid)
    assert get(a, pid)["alertes"] == []
    out = a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1, "conducteur_id": d}).json()
    assert any(x["type"] == "conduite_semaine" and x["gravite"] == "infraction" for x in out["alertes"]) or out["routes"][0]["arrets"] == []


def test_assignment_validation_and_isolation(a, b, client, calcul):
    v1 = camion(a, "AA-100-AA")
    depot(a)
    d = conducteur(a)["id"]
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a)
    executer(client, pid)
    d_b = conducteur(b, "Zoé Martin")["id"]
    assert a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1, "conducteur_id": d_b}).status_code == 404
    assert a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": 99999, "conducteur_id": d}).status_code == 404
    a.patch(f"/api/admin/conducteurs/{d}", json={"actif": False})
    assert a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1, "conducteur_id": d}).status_code == 404
    assert b.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1}).status_code == 404
    a.post(f"/api/admin/plans/{pid}/verrouiller", json={"vehicle_id": v1})
    a.patch(f"/api/admin/conducteurs/{d}", json={"actif": True})
    assert a.post(f"/api/admin/plans/{pid}/affecter", json={"vehicle_id": v1, "conducteur_id": d}).status_code == 409  # tournée verrouillée


def test_explicit_assignment_at_plan_creation_beats_the_usual_vehicle(a, client, calcul):
    v1, v2 = camion(a, "AA-100-AA"), camion(a, "BB-100-BB")
    depot(a)
    d = conducteur(a, vehicule_habituel_id=v1)["id"]
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a, affectations={str(v2): d})
    executer(client, pid)
    plan = get(a, pid)
    assert route_de(plan, "BB-100-BB")["conducteur_id"] == d and route_de(plan, "AA-100-AA")["conducteur_id"] is None


def test_counters_only_use_the_drivers_own_history(a, b, client, calcul):
    v = camion(a, "AA-100-AA")
    depot(a)
    d_a = conducteur(a, vehicule_habituel_id=v)["id"]
    d_b = conducteur(b, "Zoé Martin")["id"]
    declarer(b, d_b, ("conduite", "2026-11-02T04:00:00+01:00", "2026-11-02T10:00:00+01:00"))
    commande(client, "C1", 47.25, -1.55)
    pid = planifier(a)
    executer(client, pid)
    info = next(x for x in get(a, pid)["conducteurs"] if x["id"] == d_a)
    assert info["conduite_jour_normale_min"] == 540  # l'historique de la société B n'existe pas pour A
