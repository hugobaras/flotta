"""Audit, droits RGPD des conducteurs, conservation, en-têtes de sécurité, débit, santé, journaux."""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import retention, securite
from app.db import get_db
from app.main import app
from app.models import ActiviteConducteur, AuditLog, Check, Driver, LivraisonEvenement, WebhookLivraison, Webhook
from helpers import make_admin, send

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def debit():
    securite._ip.clear()


def conducteur(client, nom="Paul Durand", company_id=1):
    with client.Session() as db:
        d = Driver(company_id=company_id, nom=nom, pin_hash=f"h-{nom}", email="p@x.fr")
        db.add(d)
        db.commit()
        return d.id


# ---------------------------------------------------------------- Audit


def test_deblocage_est_journalise_et_isole(a, b, client):
    make_admin(client, "a@a.fr")
    make_admin(client, "b@b.fr")
    send(client, "tok-a", "freins")
    vid = a.get("/api/admin/vehicules").json()[0]["id"]
    assert a.post(f"/api/admin/vehicules/{vid}/debloquer", json={"commentaire": "Freins changés"}).status_code == 200
    journal = a.get("/api/admin/audit").json()
    assert journal[0]["action"] == "deblocage_vehicule" and "Freins changés" in journal[0]["cible"] and journal[0]["par"] == "a@a.fr"
    assert b.get("/api/admin/audit").json() == []  # B ne voit pas le journal d'A


def test_journal_reserve_aux_administrateurs(a):
    assert a.get("/api/admin/audit").status_code == 403


def test_suppressions_journalisees(a, client):
    make_admin(client, "a@a.fr")
    did = conducteur(client)
    assert a.delete(f"/api/admin/conducteurs/{did}").status_code == 204
    assert [x["action"] for x in a.get("/api/admin/audit").json()] == ["suppression_conducteur"]


# ---------------------------------------------------------------- RGPD


def test_export_et_effacement_dun_conducteur(a, b, client):
    make_admin(client, "a@a.fr")
    did = conducteur(client)
    with client.Session() as db:
        db.add(Check(company_id=1, vehicle_id=1, conducteur="Paul Durand", conducteur_id=did, reponses=[], signature="data:image/png;base64,AAAA", lat=47.2, lng=-1.5))
        db.add(ActiviteConducteur(company_id=1, conducteur_id=did, type="conduite", debut=NOW, fin=NOW + timedelta(hours=2)))
        db.commit()
    exp = a.get(f"/api/admin/conducteurs/{did}/export").json()
    assert exp["conducteur"]["nom"] == "Paul Durand" and len(exp["controles"]) == 1 and len(exp["activites"]) == 1
    assert "pin_hash" not in json.dumps(exp)
    assert a.delete(f"/api/admin/conducteurs/{did}/donnees").status_code == 204
    with client.Session() as db:
        c = db.scalar(select(Check))
        assert (c.conducteur, c.conducteur_id, c.signature, c.lat) == ("Conducteur supprimé", None, None, None)
        assert db.get(Driver, did) is None and db.scalar(select(ActiviteConducteur)) is None
    assert "effacement_conducteur" in [x["action"] for x in a.get("/api/admin/audit").json()]


def test_droits_rgpd_reserves_aux_admins_et_isoles(a, b, client):
    did = conducteur(client)
    assert a.get(f"/api/admin/conducteurs/{did}/export").status_code == 403  # pas administrateur
    make_admin(client, "b@b.fr")
    assert b.get(f"/api/admin/conducteurs/{did}/export").status_code == 404  # conducteur d'une autre société
    assert b.delete(f"/api/admin/conducteurs/{did}/donnees").status_code == 404


# ---------------------------------------------------------------- Conservation


def test_purge_etendue_aux_livraisons_activites_et_webhooks(client):
    vieux = NOW - timedelta(days=1096 + 5)
    did = conducteur(client)
    with client.Session() as db:
        db.add(LivraisonEvenement(company_id=1, plan_id=1, order_id=1, vehicle_id=1, statut="livre", fait_le=vieux, recu_le=vieux))
        db.add(LivraisonEvenement(company_id=1, plan_id=1, order_id=2, vehicle_id=1, statut="livre", fait_le=NOW, recu_le=NOW))
        db.add(ActiviteConducteur(company_id=1, conducteur_id=did, type="conduite", debut=vieux, fin=vieux + timedelta(hours=1)))
        db.add(Webhook(company_id=1, url="https://x.fr", secret="s", evenements=[]))
        db.flush()
        db.add(WebhookLivraison(company_id=1, webhook_id=1, evenement="plan.publie", payload={}, cree_le=NOW - timedelta(days=91)))
        db.commit()
        retention.purge(db, NOW)
        assert [e.order_id for e in db.scalars(select(LivraisonEvenement))] == [2]
        assert db.scalar(select(ActiviteConducteur)) is None and db.scalar(select(WebhookLivraison)) is None


# ---------------------------------------------------------------- Sécurité, santé, journaux


def test_entetes_de_securite(client):
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "same-origin"


def test_hsts_seulement_en_production(client, monkeypatch):
    assert "strict-transport-security" not in client.get("/api/health").headers
    monkeypatch.setenv("COOKIE_SECURE", "1")
    assert "strict-transport-security" in client.get("/api/health").headers


def test_limite_par_adresse_sans_toucher_chauffeurs_ni_sante(client, monkeypatch):
    monkeypatch.setattr(securite, "LIMITE_IP", 2)
    codes = [client.get("/api/auth/me").status_code for _ in range(4)]
    assert codes == [401, 401, 429, 429]
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/controle/tok-a").status_code == 200


def test_sante_503_si_la_base_est_hors_service(client):
    class Casse:
        def execute(self, *a, **k):
            raise RuntimeError("base coupée")

    app.dependency_overrides[get_db] = lambda: Casse()
    r = client.get("/api/health")
    assert r.status_code == 503 and r.json() == {"ok": False, "base": False}


def test_journaux_structures():
    rec = logging.LogRecord("x", logging.WARNING, "f", 1, "Bonjour %s", ("à vous",), None)
    d = json.loads(securite.JsonFormatter().format(rec))
    assert d["niveau"] == "WARNING" and d["message"] == "Bonjour à vous"
