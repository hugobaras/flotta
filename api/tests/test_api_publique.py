"""API publique (clés), webhooks signés, réessais et isolation."""
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app import api_publique, geocodage, webhooks
from app.models import Order, Webhook, WebhookLivraison
from test_commandes import FauxGeocodeur  # noqa: F401
from test_offres import abonner
from test_tournees import MAINTENANT, decor, evenement, horloge, ouverte, publier  # noqa: F401
from test_plans import calcul, camion, depot, executer  # noqa: F401
from helpers import make_admin

CMD = {"reference": "R1", "client": "Acme", "adresse": "1 rue de la Paix Nantes", "date_livraison": "2026-11-02"}


@pytest.fixture(autouse=True)
def reseau(monkeypatch):
    api_publique._appels.clear()
    # Les adresses de test se résolvent vers une IP publique : pas d'accès réseau dans les tests.
    monkeypatch.setattr(webhooks.socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", ("93.184.216.34", port))])
    monkeypatch.setattr(geocodage, "geocoder_une", lambda db, adresse: geocodage.Resultat(lat=47.2, lng=-1.55, score=0.95, libelle="1 rue de la Paix"))


@pytest.fixture
def pro(a, client):
    make_admin(client, "a@a.fr")
    abonner(client, "A", "pro")
    return a


def cle(c, nom="TMS"):
    r = c.post("/api/admin/integrations/cles", json={"nom": nom})
    assert r.status_code == 201, r.text
    return r.json()


def entete(k):
    return {"Authorization": f"Bearer {k['cle']}"}


def test_cle_affichee_une_seule_fois_et_stockee_hachee(pro, client):
    k = cle(pro)
    assert k["cle"].startswith("flt_")
    liste = pro.get("/api/admin/integrations/cles").json()
    assert liste[0]["apercu"] == k["cle"][:10] and "cle" not in liste[0]
    from app.models import ApiKey
    with client.Session() as db:
        assert db.scalar(select(ApiKey)).hash != k["cle"]


def test_authentification_et_revocation(pro, client):
    k = cle(pro)
    assert client.get("/api/v1/commandes").status_code == 401
    assert client.get("/api/v1/commandes", headers={"Authorization": "Bearer flt_faux"}).status_code == 401
    assert client.get("/api/v1/commandes", headers=entete(k)).status_code == 200
    assert pro.delete(f"/api/admin/integrations/cles/{k['id']}").status_code == 204
    assert client.get("/api/v1/commandes", headers=entete(k)).status_code == 401


def test_api_reservee_a_loffre_pro(a, client):
    make_admin(client, "a@a.fr")
    abonner(client, "A", "essentiel")
    assert a.post("/api/admin/integrations/cles", json={"nom": "x"}).status_code == 403
    assert a.post("/api/admin/integrations/webhooks", json={"url": "https://x.fr/h", "evenements": ["plan.publie"]}).status_code == 403


def test_creation_de_cle_reservee_aux_administrateurs(a, client):
    abonner(client, "A", "pro")
    assert a.post("/api/admin/integrations/cles", json={"nom": "x"}).status_code == 403


def test_limite_de_debit(pro, client, monkeypatch):
    monkeypatch.setattr(api_publique, "LIMITE_PAR_MINUTE", 3)
    k = cle(pro)
    assert [client.get("/api/v1/commandes", headers=entete(k)).status_code for _ in range(4)] == [200, 200, 200, 429]
    assert "Retry-After" in client.get("/api/v1/commandes", headers=entete(k)).headers


def test_commandes_par_api_et_isolation(pro, client, b):
    k = cle(pro)
    r = client.post("/api/v1/commandes", json=CMD, headers=entete(k))
    assert r.status_code == 201 and r.json()["geo_statut"] == "ok"
    oid = r.json()["id"]
    assert client.post("/api/v1/commandes", json=CMD, headers=entete(k)).status_code == 409
    assert client.patch(f"/api/v1/commandes/{oid}", json={"palettes": 3}, headers=entete(k)).json()["palettes"] == 3
    assert [o["reference"] for o in client.get("/api/v1/commandes?date=2026-11-02", headers=entete(k)).json()] == ["R1"]
    # La société B, avec sa propre clé, ne voit ni ne modifie la commande de A.
    make_admin(client, "b@b.fr")
    abonner(client, "B", "pro")
    kb = cle(b)
    assert b.get("/api/v1/commandes", headers=entete(kb)).json() == []
    assert b.get(f"/api/v1/commandes/{oid}", headers=entete(kb)).status_code == 404
    assert b.patch(f"/api/v1/commandes/{oid}", json={"palettes": 9}, headers=entete(kb)).status_code == 404


def test_documentation_openapi_limitee_a_lapi_publique(client):
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "/api/v1/commandes" in paths and not any(p.startswith("/api/admin") for p in paths)
    assert client.get("/api/v1/docs").status_code == 200


# ------------------------------------------------------------------ Webhooks


@pytest.mark.parametrize("url", ["http://exemple.fr/h", "ftp://exemple.fr/h", "https://user:pw@exemple.fr/h", "https:///h"])
def test_adresses_de_webhook_refusees(pro, url):
    assert pro.post("/api/admin/integrations/webhooks", json={"url": url, "evenements": ["plan.publie"]}).status_code == 422


def test_adresse_privee_refusee(pro, monkeypatch):
    monkeypatch.setattr(webhooks.socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", ("169.254.169.254", port))])
    assert pro.post("/api/admin/integrations/webhooks", json={"url": "https://exemple.fr/h", "evenements": ["plan.publie"]}).status_code == 422


def test_evenement_inconnu_refuse(pro):
    assert pro.post("/api/admin/integrations/webhooks", json={"url": "https://exemple.fr/h", "evenements": ["x.y"]}).status_code == 422


def creer_webhook(c, events=("controle.defaut_critique", "plan.publie", "arret.livre")):
    r = c.post("/api/admin/integrations/webhooks", json={"url": "https://exemple.fr/h", "evenements": list(events)})
    assert r.status_code == 201, r.text
    return r.json()


def test_signature_valide_rejouee_ou_alteree():
    corps = b'{"a":1}'
    entete_ = webhooks.signer("sec", corps, 1000)
    assert webhooks.verifier("sec", entete_, corps, 1100)
    assert not webhooks.verifier("sec", entete_, corps + b" ", 1100)  # corps modifié
    assert not webhooks.verifier("autre", entete_, corps, 1100)  # mauvais secret
    assert not webhooks.verifier("sec", entete_, corps, 1000 + 301)  # rejeu trop tardif
    assert not webhooks.verifier("sec", "n'importe quoi", corps, 1000)


class Receveur:
    def __init__(self, monkeypatch, code=200):
        self.recus, self.code = [], code
        monkeypatch.setattr(webhooks.httpx, "post", self._post)

    def _post(self, url, content, headers, **kw):
        self.recus.append((url, content, headers))
        if self.code is None:
            raise httpx.ConnectError("coupé")
        return httpx.Response(self.code)


def declencher(client, company=1, event="plan.publie"):
    with client.Session() as db:
        webhooks.declencher(db, company, event, {"x": 1})
        return db.scalar(select(WebhookLivraison.id).order_by(WebhookLivraison.id.desc()))


def test_envoi_signe_et_verifiable(pro, client, monkeypatch):
    w = creer_webhook(pro)
    rec = Receveur(monkeypatch)
    lid = declencher(client)
    with client.Session() as db:
        assert webhooks.envoyer(db, lid) == "ok"
    url, corps, h = rec.recus[0]
    assert url == "https://exemple.fr/h" and h["X-Flotta-Evenement"] == "plan.publie"
    assert webhooks.verifier(w["secret"], h["X-Flotta-Signature"], corps)


def test_reessais_a_delai_croissant_puis_abandon(pro, client, monkeypatch):
    creer_webhook(pro)
    Receveur(monkeypatch, code=500)
    lid = declencher(client)
    now = MAINTENANT
    with client.Session() as db:
        attendus = []
        for k in range(len(webhooks.DELAIS)):
            assert webhooks.envoyer(db, lid, now) == "en_attente"
            l = db.get(WebhookLivraison, lid)
            attendus.append(l.prochaine_tentative.replace(tzinfo=None) - now.replace(tzinfo=None))
            now = l.prochaine_tentative.replace(tzinfo=now.tzinfo)
        assert attendus == [timedelta(seconds=s) for s in webhooks.DELAIS]
        assert webhooks.envoyer(db, lid, now) == "echec"  # 6e échec : abandon
        assert db.get(WebhookLivraison, lid).tentatives == 6


def test_pas_de_double_envoi_avant_lheure(pro, client, monkeypatch):
    creer_webhook(pro)
    rec = Receveur(monkeypatch, code=503)
    lid = declencher(client)
    with client.Session() as db:
        webhooks.envoyer(db, lid, MAINTENANT)
        assert webhooks.envoyer(db, lid, MAINTENANT + timedelta(seconds=10)) == "ignore"  # pas encore dû
    assert len(rec.recus) == 1


def test_relance_periodique_reprend_les_livraisons_dues(pro, client, monkeypatch):
    creer_webhook(pro)
    rec = Receveur(monkeypatch, code=None)  # réseau coupé
    declencher(client)
    with client.Session() as db:
        assert webhooks.relancer_dus(db, MAINTENANT + timedelta(hours=1)) == 1
        assert webhooks.relancer_dus(db, MAINTENANT + timedelta(hours=1, seconds=5)) == 0  # replanifié
    rec.code = 200
    rec.__init__(monkeypatch, 200)
    with client.Session() as db:
        assert webhooks.relancer_dus(db, MAINTENANT + timedelta(hours=2)) == 1
        assert db.scalar(select(WebhookLivraison)).statut == "ok"


def test_adresse_devenue_privee_au_moment_de_lenvoi(pro, client, monkeypatch):
    creer_webhook(pro)
    rec = Receveur(monkeypatch)
    lid = declencher(client)
    monkeypatch.setattr(webhooks.socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", ("10.0.0.5", port))])
    with client.Session() as db:
        assert webhooks.envoyer(db, lid) == "en_attente"
        assert db.get(WebhookLivraison, lid).derniere_erreur == "Adresse non publique refusée"
    assert rec.recus == []


def test_abonnement_aux_evenements_et_isolation(pro, client, b):
    creer_webhook(pro, ["arret.livre"])
    make_admin(client, "b@b.fr")
    abonner(client, "B", "pro")
    creer_webhook(b, ["plan.publie"])
    with client.Session() as db:
        webhooks.declencher(db, 1, "plan.publie", {})  # A n'est pas abonnée à cet événement ; B ne reçoit rien d'A
        assert db.scalar(select(WebhookLivraison)) is None
    assert pro.get("/api/admin/integrations/webhooks").json()["webhooks"][0]["evenements"] == ["arret.livre"]
    assert b.get("/api/admin/integrations/webhooks/1/livraisons").json() == []


def test_essentiel_ne_declenche_pas_de_webhook(client):
    abonner(client, "A", "essentiel")
    with client.Session() as db:
        db.add(Webhook(company_id=1, url="https://exemple.fr/h", secret="s", evenements=["plan.publie"]))
        db.commit()
        webhooks.declencher(db, 1, "plan.publie", {})
        assert db.scalar(select(WebhookLivraison)) is None


def test_evenements_metier_declenchent_les_webhooks(pro, client, ouverte, a, monkeypatch):
    creer_webhook(pro)
    assert publier(a, ouverte["plan"]).status_code == 200
    arret = ouverte["arrets"][0]
    assert evenement(a, ouverte["token"], arret["order_id"], "arrive").status_code == 201
    assert evenement(a, ouverte["token"], arret["order_id"], "livre").status_code == 201
    with client.Session() as db:
        evs = sorted(l.evenement for l in db.scalars(select(WebhookLivraison)))
    assert "arret.livre" in evs
    assert "plan.publie" in evs


def test_defaut_critique_declenche_un_webhook(pro, client):
    creer_webhook(pro)
    from helpers import send
    send(client, "tok-a", "freins")
    with client.Session() as db:
        l = db.scalar(select(WebhookLivraison).where(WebhookLivraison.evenement == "controle.defaut_critique"))
        assert l.payload["data"]["plaque"] == "AA-111-AA"
