"""Prise en main : étapes, données de démonstration, signalements."""
from sqlalchemy import func, select

from app.models import Check, Driver, Order, Signalement, Vehicle
from helpers import make_admin, send
from test_tournees import decor, horloge  # noqa: F401
from test_plans import calcul, camion, depot, executer  # noqa: F401


def etapes(c):
    return {e["id"]: e["fait"] for e in c.get("/api/admin/demarrage").json()["etapes"]}


def test_etapes_suivent_les_donnees(a, client):
    e = etapes(a)
    assert e["flotte"] is True and e["conducteurs"] is False and e["commandes"] is False and e["controle"] is False  # le client de test a 2 camions
    assert e["checklists"] is None and e["qr"] is None  # non constatables
    send(client, "tok-a")
    assert etapes(a)["controle"] is True


def test_etapes_isolees_par_societe(a, b, client):
    make_admin(client, "a@a.fr")
    a.post("/api/admin/demo")
    assert etapes(b)["commandes"] is False and etapes(a)["commandes"] is True


def test_demo_cree_15_camions_et_80_commandes_et_se_retire(a, client):
    make_admin(client, "a@a.fr")
    r = a.post("/api/admin/demo")
    assert r.status_code == 201 and r.json() == {"vehicules": 15, "conducteurs": 15, "commandes": 80}
    with client.Session() as db:
        assert db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.plaque.startswith("DM-"))) == 15
        assert db.scalar(select(func.count()).select_from(Order).where(Order.company_id == 1)) == 80
        assert all(o.lat is not None and o.geo_statut == "ok" for o in db.scalars(select(Order)))
    assert a.get("/api/admin/demarrage").json()["demo"] is True
    assert a.post("/api/admin/demo").status_code == 409  # une seule fois
    assert a.delete("/api/admin/demo").status_code == 204
    with client.Session() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0 and db.scalar(select(func.count()).select_from(Driver)) == 0
        assert [v.plaque for v in db.scalars(select(Vehicle).where(Vehicle.company_id == 1))] == ["AA-111-AA", "ZZ-999-ZZ"]  # le reste est intact


def test_demo_reservee_aux_administrateurs_et_isolee(a, b, client):
    assert a.post("/api/admin/demo").status_code == 403
    make_admin(client, "a@a.fr")
    a.post("/api/admin/demo")
    make_admin(client, "b@b.fr")
    assert b.delete("/api/admin/demo").status_code == 204  # ne retire rien chez A
    with client.Session() as db:
        assert db.scalar(select(func.count()).select_from(Order).where(Order.company_id == 1)) == 80


def test_retrait_de_la_demo_avec_un_controle(a, client):
    make_admin(client, "a@a.fr")
    a.post("/api/admin/demo")
    with client.Session() as db:
        v = db.scalar(select(Vehicle).where(Vehicle.plaque == "DM-001-AA"))
        db.add(Check(company_id=1, vehicle_id=v.id, conducteur="x", reponses=[]))
        db.commit()
    assert a.delete("/api/admin/demo").status_code == 204
    with client.Session() as db:
        assert db.scalar(select(func.count()).select_from(Check)) == 0


def test_signalement_capture_le_contexte(a, client):
    r = a.post("/api/admin/signalements", json={"message": "Le planning ne charge pas", "page": "/admin/planning", "navigateur": "Safari"})
    assert r.status_code == 201
    with client.Session() as db:
        s = db.scalar(select(Signalement))
        assert s.contexte["page"] == "/admin/planning" and s.contexte["societe"] == "A" and s.contexte["version"] and s.user_email == "a@a.fr"
    assert a.post("/api/admin/signalements", json={"message": "x"}).status_code == 422


def test_signalements_lus_par_la_plateforme_seulement(a, client):
    a.post("/api/admin/signalements", json={"message": "Problème de test"})
    assert a.get("/api/plateforme/signalements").status_code == 403
    from test_offres import operateur
    op = operateur(client)
    assert [s["message"] for s in op.get("/api/plateforme/signalements").json()] == ["Problème de test"]
