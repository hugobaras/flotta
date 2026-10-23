"""Suivi en direct et replanification proposée : scénarios de retard, de commande urgente et de panne."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app import livraisons, plans, trafic
from app.models import LivraisonEvenement, Order, Plan, PlanSnapshot
from test_plans import calcul, camion, depot, executer  # noqa: F401
from test_plans_edition import get, route_de

JOUR = date(2026, 11, 2)  # lundi
MAINTENANT = datetime(2026, 11, 2, 8, 30, tzinfo=timezone.utc)  # 9 h 30 à Paris
DEPOT = (47.2184, -1.5536)


@pytest.fixture(autouse=True)
def horloge(monkeypatch):
    monkeypatch.setattr(livraisons, "maintenant", lambda: MAINTENANT)


def _commande(client, ref, decalage_lat, fin=None, debut=None, jour=JOUR, statut="a_planifier", lat=True):
    with client.Session() as db:
        o = Order(company_id=1, reference=ref, client=ref, adresse=f"{ref} rue", lat=DEPOT[0] + decalage_lat if lat else None, lng=DEPOT[1] if lat else None,
                  geo_statut="ok" if lat else "introuvable", poids_kg=100, palettes=1, volume_m3=1, duree_service_min=15, date_livraison=jour,
                  fenetre_fin=fin, fenetre_debut=debut, statut=statut)
        db.add(o)
        db.commit()
        return o.id


def forcer(client, pid, tournees, non_affectees=()):
    """Remplace l'état du plan par un agencement choisi : {véhicule: [commandes]}."""
    with client.Session() as db:
        plan = db.get(Plan, pid)
        etat = {"routes": [{"vehicle_id": v, "verrouille": False, "conducteur_id": None, "arrets": [{"order_id": o, "verrouille": False} for o in ids]}
                           for v, ids in tournees.items()], "non_affectees": [{"order_id": o, "raison": "test"} for o in non_affectees]}
        plans.pousser(db, plan, etat, "Agencement de test")
        db.commit()


def evenement(client, pid, vehicle_id, order_id, statut, fait_le):
    with client.Session() as db:
        db.add(LivraisonEvenement(company_id=1, plan_id=pid, order_id=order_id, vehicle_id=vehicle_id, statut=statut, fait_le=fait_le, recu_le=fait_le))
        db.commit()


@pytest.fixture
def monde(a, client, calcul):  # noqa: F811
    """Deux camions, un dépôt, six commandes au nord (A) et au sud (B) du dépôt ; plan calculé puis agencement forcé."""
    va, vb = camion(a, "AA-100-AA"), camion(a, "BB-100-BB")
    depot(a)
    ids = {n: _commande(client, n, d, **kw) for n, d, kw in [
        ("A1", 0.10, {}), ("A2", 0.20, {"fin": "10:00"}), ("A3", 0.30, {}), ("B1", -0.10, {}), ("B2", -0.20, {}), ("B3", -0.30, {})]}
    pid = a.post("/api/admin/plans", json={"jour": JOUR.isoformat(), "temps_max_s": 1}).json()["id"]
    executer(client, pid)
    return {"va": va, "vb": vb, "ids": ids, "plan": pid}


def propositions(c, pid, **corps):
    return c.post(f"/api/admin/plans/{pid}/propositions", json=corps)


def etat_brut(a, pid):
    d = get(a, pid)
    return [(r["plaque"], [s["order_id"] for s in r["arrets"]]) for r in d["routes"]], d["non_affectees"], d["peut_annuler"]


# ---------------------------------------------------------------- Retard : prévisions


def test_forecast_flags_a_stop_that_will_miss_its_window(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A3"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})  # A2 (fenêtre 10 h) passe en dernier
    s = a.get(f"/api/admin/plans/{m['plan']}/suivi").json()
    assert s["trafic"] == {"actif": False, "fournisseur": None, "indisponible": False}
    (r,) = s["retards"]
    assert r["reference"] == "A2" and r["retard_min"] > 30 and "fenêtre close à 10:00" in r["message"] and r["plaque"] == "AA-100-AA"
    route_a = next(x for x in s["routes"] if x["plaque"] == "AA-100-AA")
    assert [x["reference"] for x in route_a["restants"]] == ["A1", "A3", "A2"] and abs(route_a["restants"][2]["retard_fenetre_min"] - r["retard_min"]) <= 0.5
    assert s["resume"]["nb_retards"] == 1


def test_forecast_restarts_from_the_real_position_and_time(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    with client.Session() as db:
        db.get(Order, m["ids"]["A2"]).fenetre_fin = "09:40"
        db.commit()
    # A1 livré à 9 h 25 (très en retard sur le plan) : A2, 14 min plus loin, sera atteint vers 9 h 44, après la fin de fenêtre (9 h 40)
    evenement(client, m["plan"], m["va"], m["ids"]["A1"], "arrive", datetime(2026, 11, 2, 8, 10, tzinfo=timezone.utc))
    evenement(client, m["plan"], m["va"], m["ids"]["A1"], "livre", datetime(2026, 11, 2, 8, 25, tzinfo=timezone.utc))
    s = a.get(f"/api/admin/plans/{m['plan']}/suivi").json()
    route_a = next(x for x in s["routes"] if x["plaque"] == "AA-100-AA")
    assert route_a["faits"] == 1 and [x["reference"] for x in route_a["restants"]] == ["A2"]
    assert abs(route_a["restants"][0]["arrivee_prevue_min"] - (9 * 60 + 30 + 14.4)) < 0.5
    (r,) = s["retards"]
    assert r["reference"] == "A2" and 3 <= r["retard_min"] <= 5
    assert route_a["depuis"]["lat"] == pytest.approx(DEPOT[0] + 0.10)


def test_a_truck_on_site_finishes_its_service_before_leaving(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    evenement(client, m["plan"], m["va"], m["ids"]["A1"], "arrive", datetime(2026, 11, 2, 8, 25, tzinfo=timezone.utc))  # arrivé à 9 h 25, service de 15 min
    s = a.get(f"/api/admin/plans/{m['plan']}/suivi").json()
    route_a = next(x for x in s["routes"] if x["plaque"] == "AA-100-AA")
    assert route_a["restants"][0]["reference"] == "A2" and route_a["restants"][0]["arrivee_prevue_min"] > 9 * 60 + 40 + 14  # 9 h 40 de fin de service + trajet


def test_no_forecast_delay_when_everything_is_on_time(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A2"], m["ids"]["A1"]], m["vb"]: [m["ids"]["B1"]]})  # A2 (fenêtre 10 h) en premier : atteint à 9 h 59
    assert a.get(f"/api/admin/plans/{m['plan']}/suivi").json()["retards"] == []


# ---------------------------------------------------------------- Retard : propositions chiffrées


def test_delay_proposals_are_ranked_quantified_and_change_nothing(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A3"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"], m["ids"]["B2"]]})
    avant = etat_brut(a, m["plan"])
    r = propositions(a, m["plan"], type="retard")
    assert r.status_code == 200 and "Rien n'est modifié" in r.json()["avertissement"]
    props = r.json()["propositions"]
    assert 2 <= len(props) <= 3
    meilleure = props[0]
    assert meilleure["impact"]["avant"]["nb_retards"] == 1 and meilleure["impact"]["apres"]["nb_retards"] == 0
    assert meilleure["impact"]["apres"]["retard_total_min"] == 0 and "retards : 1 → 0" in meilleure["description"]
    assert all(p["impact"]["apres"]["nb_retards"] <= p["impact"]["avant"]["nb_retards"] for p in props)
    assert any(len(p["actions"]) == 1 and p["actions"][0]["order_id"] == m["ids"]["A2"] for p in props)
    keys = [(p["impact"]["apres"]["reportes"], p["impact"]["apres"]["nb_retards"], p["impact"]["apres"]["retard_total_min"], p["impact"]["apres"]["km"]) for p in props]
    assert keys == sorted(keys)  # classées du meilleur au moins bon
    assert etat_brut(a, m["plan"]) == avant  # simple lecture : le plan n'a pas bougé


def test_validating_a_proposal_applies_it_in_one_undoable_step(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A3"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    avant = get(a, m["plan"])
    choix = propositions(a, m["plan"], type="retard").json()["propositions"][0]
    r = a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "retard", "actions": choix["actions"]})
    assert r.status_code == 200 and r.json()["peut_annuler"] is True
    assert a.get(f"/api/admin/plans/{m['plan']}/suivi").json()["retards"] == []
    retour = a.post(f"/api/admin/plans/{m['plan']}/annuler").json()
    assert [[s["order_id"] for s in x["arrets"]] for x in retour["routes"]] == [[s["order_id"] for s in x["arrets"]] for x in avant["routes"]]


def test_no_proposal_when_nothing_improves_the_delay(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    with client.Session() as db:
        db.get(Order, m["ids"]["A2"]).fenetre_fin = "09:40"
        db.commit()
    evenement(client, m["plan"], m["va"], m["ids"]["A1"], "livre", datetime(2026, 11, 2, 8, 25, tzinfo=timezone.utc))
    assert a.get(f"/api/admin/plans/{m['plan']}/suivi").json()["retards"]
    assert propositions(a, m["plan"], type="retard").json()["propositions"] == []  # le camion est déjà le mieux placé


def test_delay_proposals_never_touch_locked_routes(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A3"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    a.post(f"/api/admin/plans/{m['plan']}/verrouiller", json={"vehicle_id": m["vb"]})
    props = propositions(a, m["plan"], type="retard").json()["propositions"]
    assert props and all(act["vehicle_id"] != m["vb"] for p in props for act in p["actions"])
    a.post(f"/api/admin/plans/{m['plan']}/verrouiller", json={"vehicle_id": m["va"]})
    assert propositions(a, m["plan"], type="retard").json()["propositions"] == []  # tout est verrouillé


# ---------------------------------------------------------------- Commande urgente


def test_urgent_order_is_inserted_at_the_best_place_and_only_on_validation(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A3"]], m["vb"]: [m["ids"]["B1"], m["ids"]["B3"]]})
    urgente = _commande(client, "URGENT", 0.20)  # entre A1 et A3, sur la route du nord
    avant, matrices_avant = etat_brut(a, m["plan"]), None
    with client.Session() as db:
        matrices_avant = len(db.get(Plan, m["plan"]).matrices["commandes"])
    r = propositions(a, m["plan"], type="urgence", order_id=urgente)
    assert r.status_code == 200
    props = r.json()["propositions"]
    meilleure = props[0]
    assert meilleure["actions"][0]["order_id"] == urgente and meilleure["actions"][0]["vehicle_id"] == m["va"] and meilleure["actions"][0]["position"] == 1
    assert len(props) >= 2 and props[0]["impact"]["apres"]["km"] <= props[1]["impact"]["apres"]["km"]
    assert etat_brut(a, m["plan"]) == avant
    with client.Session() as db:
        assert len(db.get(Plan, m["plan"]).matrices["commandes"]) == matrices_avant  # proposer n'étend rien en base
        assert db.get(Order, urgente).statut == "a_planifier"
    out = a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "urgence", "order_id": urgente, "actions": meilleure["actions"]}).json()
    assert [s["order_id"] for s in route_de(out, "AA-100-AA")["arrets"]] == [m["ids"]["A1"], urgente, m["ids"]["A3"]]
    with client.Session() as db:
        assert db.get(Order, urgente).statut == "planifie" and urgente in db.get(Plan, m["plan"]).matrices["commandes"]
    assert a.post(f"/api/admin/plans/{m['plan']}/annuler").status_code == 200


def test_urgent_order_validation(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"]], m["vb"]: [m["ids"]["B1"]]})
    deja = m["ids"]["A1"]
    autre_jour = _commande(client, "DEMAIN", 0.1, jour=date(2026, 11, 3))
    sans_gps = _commande(client, "SANSGPS", 0, lat=False)
    livree = _commande(client, "LIVREE", 0.1, statut="livre")
    for oid, code in [(deja, 409), (autre_jour, 409), (sans_gps, 409), (livree, 409), (999999, 404), (None, 422)]:
        corps = {"type": "urgence"} | ({"order_id": oid} if oid else {})
        assert propositions(a, m["plan"], **corps).status_code == code, oid
    ok = _commande(client, "OK", 0.1)
    assert a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer",
                  json={"type": "urgence", "order_id": ok, "actions": [{"order_id": m["ids"]["B1"], "vehicle_id": m["va"]}]}).status_code == 422


def test_urgent_order_cannot_be_priced_when_routing_is_down(a, client, monde, monkeypatch):
    from app import matrices
    from app.routage import RouteurIndisponible
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"]], m["vb"]: [m["ids"]["B1"]]})
    urgente = _commande(client, "URGENT", 0.2)

    def panne(*_):
        raise RouteurIndisponible("coupé")
    monkeypatch.setattr(matrices, "fournisseur", panne)
    r = propositions(a, m["plan"], type="urgence", order_id=urgente)
    assert r.status_code == 503 and "routage" in r.json()["detail"]


def test_an_unassigned_order_can_be_inserted_without_new_routing_call(a, client, monde, monkeypatch):
    from app import matrices
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"]], m["vb"]: [m["ids"]["B1"]]}, non_affectees=[m["ids"]["A3"]])
    monkeypatch.setattr(matrices, "fournisseur", lambda *_: (_ for _ in ()).throw(AssertionError("pas d'appel au routage")))
    # A3 est déjà dans les matrices (non affectée) : mais la route d'urgence exige qu'elle ne soit pas déjà dans une tournée, ce qui est vrai ici.
    r = propositions(a, m["plan"], type="urgence", order_id=m["ids"]["A3"])
    assert r.status_code == 200 and r.json()["propositions"]


# ---------------------------------------------------------------- Panne


def test_breakdown_redistributes_remaining_stops_only_after_validation(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"], m["ids"]["A3"]], m["vb"]: [m["ids"]["B1"], m["ids"]["B2"]]})
    evenement(client, m["plan"], m["va"], m["ids"]["A1"], "livre", datetime(2026, 11, 2, 8, 10, tzinfo=timezone.utc))  # A1 déjà livré
    with client.Session() as db:
        db.get(Order, m["ids"]["A1"]).statut = "livre"
        db.commit()
    avant = etat_brut(a, m["plan"])
    r = propositions(a, m["plan"], type="panne", vehicle_id=m["va"])
    props = r.json()["propositions"]
    assert r.status_code == 200 and props
    meilleure = props[0]
    deplaces = {act["order_id"] for act in meilleure["actions"]}
    assert deplaces == {m["ids"]["A2"], m["ids"]["A3"]} and m["ids"]["A1"] not in deplaces  # l'arrêt livré reste là où il est
    assert all(act["vehicle_id"] in (m["vb"], None) for act in meilleure["actions"])
    assert etat_brut(a, m["plan"]) == avant
    out = a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "panne", "vehicle_id": m["va"], "actions": meilleure["actions"]}).json()
    camion_a, camion_b = route_de(out, "AA-100-AA"), route_de(out, "BB-100-BB")
    assert [s["order_id"] for s in camion_a["arrets"]] == [m["ids"]["A1"]] and camion_a["verrouille"] is True
    assert {m["ids"]["A2"], m["ids"]["A3"]} <= {s["order_id"] for s in camion_b["arrets"]}
    assert out["resume"]["nb_non_affectees"] == 0


def test_breakdown_with_no_other_truck_leaves_the_stops_out_explicitly(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    a.post(f"/api/admin/plans/{m['plan']}/verrouiller", json={"vehicle_id": m["vb"]})  # l'autre camion est verrouillé
    props = propositions(a, m["plan"], type="panne", vehicle_id=m["va"]).json()["propositions"]
    assert props and all(act["vehicle_id"] is None for p in props for act in p["actions"]) and props[0]["impact"]["apres"]["reportes"] == 2
    out = a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "panne", "vehicle_id": m["va"], "actions": props[0]["actions"]}).json()
    assert {n["order_id"] for n in out["non_affectees"]} == {m["ids"]["A1"], m["ids"]["A2"]}


def test_breakdown_strategies_can_differ_and_report_what_cannot_arrive_on_time(a, client, monde):
    m = monde
    with client.Session() as db:
        db.get(Order, m["ids"]["A3"]).fenetre_fin = "09:45"  # impossible à tenir par un autre camion à 9 h 30
        db.commit()
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"], m["ids"]["A3"]], m["vb"]: [m["ids"]["B1"]]})
    props = propositions(a, m["plan"], type="panne", vehicle_id=m["va"]).json()["propositions"]
    assert len(props) >= 2
    assert any(p["impact"]["apres"]["reportes"] > 0 for p in props)  # une variante laisse de côté ce qui ne peut pas passer
    assert props == sorted(props, key=lambda p: (p["impact"]["apres"]["reportes"], p["impact"]["apres"]["nb_retards"]))


# ---------------------------------------------------------------- Validation, isolation, trafic


def test_invalid_validation_changes_nothing(a, client, monde):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"]], m["vb"]: [m["ids"]["B1"]]})
    avant = etat_brut(a, m["plan"])
    mauvais = [{"order_id": 999999, "vehicle_id": m["va"]}]
    assert a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "retard", "actions": mauvais}).status_code == 404
    a.post(f"/api/admin/plans/{m['plan']}/verrouiller", json={"vehicle_id": m["vb"]})
    avant = etat_brut(a, m["plan"])
    verrou = [{"order_id": m["ids"]["A1"], "vehicle_id": m["vb"], "position": 0}]
    assert a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "retard", "actions": verrou}).status_code == 409
    assert etat_brut(a, m["plan"]) == avant
    assert a.post(f"/api/admin/plans/{m['plan']}/propositions/appliquer", json={"type": "retard", "actions": []}).status_code == 422
    assert propositions(a, m["plan"], type="inconnu").status_code == 422
    assert propositions(a, m["plan"], type="panne").status_code == 404 and propositions(a, m["plan"], type="panne", vehicle_id=99999).status_code == 404


def test_follow_up_routes_require_login_a_finished_plan_and_isolation(a, b, client, monde):
    m = monde
    for method, url in [("get", f"/api/admin/plans/{m['plan']}/suivi"), ("post", f"/api/admin/plans/{m['plan']}/propositions"),
                        ("post", f"/api/admin/plans/{m['plan']}/propositions/appliquer")]:
        assert getattr(client.__class__(client.app), method)(url).status_code == 401
        assert (b.get(url) if method == "get" else b.post(url, json={"type": "retard", "actions": [{"order_id": 1}]})).status_code == 404
    attente = a.post("/api/admin/plans", json={"jour": "2026-11-05"}).json()["id"]
    assert a.get(f"/api/admin/plans/{attente}/suivi").status_code == 409


def test_traffic_is_off_by_default_and_never_called(a, client, monde, monkeypatch):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    monkeypatch.setattr(trafic.HereTrafic, "durees", lambda *_: (_ for _ in ()).throw(AssertionError("appelé alors que désactivé")))
    monkeypatch.setattr(trafic.TomTomTrafic, "durees", lambda *_: (_ for _ in ()).throw(AssertionError("appelé alors que désactivé")))
    monkeypatch.setenv("HERE_API_KEY", "cle")  # une clé seule n'active rien
    assert trafic.fournisseur() is None
    assert a.get(f"/api/admin/plans/{m['plan']}/suivi").json()["trafic"]["actif"] is False


class FauxTrafic(trafic.FournisseurTrafic):
    nom = "faux"

    def __init__(self, facteur=2.0, panne=False):
        self.facteur, self.panne, self.appels = facteur, panne, 0

    def durees(self, origines, destinations, depart):
        self.appels += 1
        if self.panne:
            raise trafic.TraficIndisponible("coupé")
        return [[0 if o == d else self.facteur * 600 for d in destinations] for o in origines]  # 20 min par trajet avec un facteur 2


def test_live_traffic_replaces_travel_times_when_enabled_and_falls_back_when_down(a, client, monde, monkeypatch):
    m = monde
    forcer(client, m["plan"], {m["va"]: [m["ids"]["A1"], m["ids"]["A2"]], m["vb"]: [m["ids"]["B1"]]})
    base = a.get(f"/api/admin/plans/{m['plan']}/suivi").json()
    faux = FauxTrafic(facteur=3.0)
    monkeypatch.setattr(trafic, "fournisseur", lambda: faux)
    live = a.get(f"/api/admin/plans/{m['plan']}/suivi").json()
    assert live["trafic"] == {"actif": True, "fournisseur": "faux", "indisponible": False} and faux.appels >= 1
    arr = lambda s: next(x for x in s["routes"] if x["plaque"] == "AA-100-AA")["restants"][0]["arrivee_prevue_min"]  # noqa: E731
    assert arr(live) == pytest.approx(9 * 60 + 30 + 30, abs=0.5) and arr(live) != arr(base)  # 30 min de trajet observé au lieu de ~14
    monkeypatch.setattr(trafic, "fournisseur", lambda: FauxTrafic(panne=True))
    repli = a.get(f"/api/admin/plans/{m['plan']}/suivi").json()
    assert repli["trafic"]["indisponible"] is True and arr(repli) == arr(base)  # on retombe sur les durées du plan


def test_here_request_shape_and_parsing(monkeypatch):
    vu = {}

    def faux_post(url, params, json, timeout):
        vu.update(url=url, params=params, json=json)
        return httpx.Response(200, json={"matrix": {"numOrigins": 2, "numDestinations": 2, "travelTimes": [0, 600, 660, 0]}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(trafic.httpx, "post", faux_post)
    m = trafic.HereTrafic("k").durees([(47.0, -1.0), (47.1, -1.1)], [(47.0, -1.0), (47.1, -1.1)], MAINTENANT)
    assert m == [[0.0, 600.0], [660.0, 0.0]]
    assert vu["url"].startswith("https://matrix.router.hereapi.com/v8/matrix") and vu["params"]["apiKey"] == "k" and vu["json"]["transportMode"] == "truck"
    assert vu["json"]["origins"][0] == {"lat": 47.0, "lng": -1.0}


def test_tomtom_request_shape_and_parsing(monkeypatch):
    vu = {}

    def faux_post(url, params, json, timeout):
        vu.update(url=url, params=params, json=json)
        data = [{"originIndex": 0, "destinationIndex": 1, "routeSummary": {"travelTimeInSeconds": 540}}, {"originIndex": 1, "destinationIndex": 0}]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(trafic.httpx, "post", faux_post)
    m = trafic.TomTomTrafic("k").durees([(47.0, -1.0), (47.1, -1.1)], [(47.0, -1.0), (47.1, -1.1)], MAINTENANT)
    assert m == [[None, 540.0], [None, None]]
    assert vu["url"] == "https://api.tomtom.com/routing/matrix/2" and vu["params"]["key"] == "k"
    assert vu["json"]["options"]["travelMode"] == "truck" and vu["json"]["options"]["traffic"] == "live"


def test_traffic_provider_errors_are_wrapped(monkeypatch):
    monkeypatch.setattr(trafic.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("coupé")))
    with pytest.raises(trafic.TraficIndisponible):
        trafic.HereTrafic("k").durees([(47.0, -1.0)], [(47.0, -1.0)], MAINTENANT)
    monkeypatch.setattr(trafic.httpx, "post", lambda url, **k: httpx.Response(200, json={"pas": "bon"}, request=httpx.Request("POST", url)))
    with pytest.raises(trafic.TraficIndisponible):
        trafic.TomTomTrafic("k").durees([(47.0, -1.0)], [(47.0, -1.0)], MAINTENANT)


@pytest.mark.parametrize("env,attendu", [({}, None), ({"TRAFIC_ACTIF": "0", "HERE_API_KEY": "k"}, None), ({"TRAFIC_ACTIF": "1"}, None),
                                          ({"TRAFIC_ACTIF": "1", "HERE_API_KEY": "k"}, "here"), ({"TRAFIC_ACTIF": "oui", "TRAFIC_FOURNISSEUR": "tomtom", "TOMTOM_API_KEY": "k"}, "tomtom"),
                                          ({"TRAFIC_ACTIF": "1", "TRAFIC_FOURNISSEUR": "autre", "HERE_API_KEY": "k"}, None)])
def test_traffic_feature_flag(monkeypatch, env, attendu):
    for k in ("TRAFIC_ACTIF", "TRAFIC_FOURNISSEUR", "HERE_API_KEY", "TOMTOM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    f = trafic.fournisseur()
    assert (f.nom if f else None) == attendu
