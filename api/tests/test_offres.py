import pytest

from app import offres
from app.auth import hasher
from app.models import Company, Subscription, User
from helpers import login


def abonner(client, nom, offre, camions=10, statut="actif"):
    with client.Session() as db:
        cid = db.query(Company).filter_by(nom=nom).one().id
        db.add(Subscription(company_id=cid, offre=offre, camions_factures=camions, statut=statut))
        db.commit()
        return cid


def operateur(client):
    with client.Session() as db:
        cid = db.query(Company).filter_by(nom="A").one().id
        db.add(User(company_id=cid, email="op@flotta.fr", password_hash=hasher.hash("motdepasse-ok"), role="plateforme"))
        db.commit()
    assert login(client, "op@flotta.fr").status_code == 200
    return client


def test_vingt_camions_pro_annuel():
    m = offres.calculer("pro", 20, "annuel", 10, 20)
    assert m["mensuel_ht"] == 150000 and m["brut_ht"] == 1800000 and m["remise"] == 180000
    assert (m["ht"], m["tva"], m["ttc"]) == (1620000, 324000, 1944000)


@pytest.mark.parametrize("offre,camions,attendu", [("essentiel", 5, 50000), ("essentiel", 20, 90000), ("pro", 5, 90000), ("pro", 12, 90000), ("pro", 13, 97500)])
def test_minimum_de_facturation(offre, camions, attendu):
    assert offres.calculer(offre, camions, "mensuel", 0, 20)["mensuel_ht"] == attendu


def test_grille_modifiable_par_configuration(monkeypatch):
    monkeypatch.setenv("OFFRES_JSON", '{"pro": {"prix_eur": 80}}')
    assert offres.calculer("pro", 20, "mensuel", 0, 0)["mensuel_ht"] == 160000


def test_fonctions_pro_refusees_en_essentiel(a):
    abonner(a, "A", "essentiel")
    assert a.get("/api/admin/plans/1/suivi").status_code == 403
    assert a.post("/api/admin/plans/1/propositions", json={"type": "retard"}).status_code == 403
    assert a.get("/api/admin/conducteurs/1/compteurs").status_code == 403
    assert a.get("/api/auth/me").json()["fonctions"] == []


def test_fonctions_pro_ouvertes_en_pro_et_sans_abonnement(a, b):
    abonner(a, "A", "pro")
    assert a.get("/api/admin/plans/1/suivi").status_code == 404  # passe la porte de l'offre, plan inconnu
    assert b.get("/api/admin/plans/1/suivi").status_code == 404  # B sans abonnement : tout reste disponible


def test_societe_suspendue_bloquee_mais_pas_les_chauffeurs(a):
    abonner(a, "A", "pro", statut="suspendu")
    assert a.get("/api/admin/vehicules").status_code == 403
    assert a.get("/api/controle/tok-a").status_code == 200


def test_back_office_reserve_a_la_plateforme(a):
    assert a.get("/api/plateforme/societes").status_code == 403
    assert a.get("/api/plateforme/tableau").status_code == 403
    assert a.post("/api/plateforme/societes/1/documents", json={"type": "devis"}).status_code == 403


def test_creation_modification_et_mrr(client):
    op = operateur(client)
    r = op.post("/api/plateforme/societes", json={"nom": "Nouveau", "offre": "pro", "camions_factures": 20, "statut": "actif"})
    assert r.status_code == 201 and r.json()["mensuel_ht"] == 150000
    cid = r.json()["id"]
    op.post("/api/plateforme/societes", json={"nom": "Essai", "offre": "essentiel", "camions_factures": 3, "statut": "essai"})
    t = op.get("/api/plateforme/tableau").json()
    assert (t["mrr_ht"], t["camions_factures"], t["clients_actifs"], t["clients_en_essai"]) == (150000, 20, 1, 1)
    r = op.patch(f"/api/plateforme/societes/{cid}/abonnement", json={"statut": "suspendu"})
    assert r.json()["statut"] == "suspendu"
    assert op.get("/api/plateforme/tableau").json()["mrr_ht"] == 0


def test_facture_pdf_numerotation_et_montants(client):
    op = operateur(client)
    cid = op.post("/api/plateforme/societes", json={"nom": "Gros", "offre": "pro", "camions_factures": 20, "statut": "actif"}).json()["id"]
    f1 = op.post(f"/api/plateforme/societes/{cid}/documents", json={"type": "facture", "periode": "annuel", "remise_pct": 10}).json()
    f2 = op.post(f"/api/plateforme/societes/{cid}/documents", json={"type": "facture"}).json()
    d = op.post(f"/api/plateforme/societes/{cid}/documents", json={"type": "devis"}).json()
    assert f1["numero"].startswith("FA-") and f1["numero"].endswith("-0001") and f2["numero"].endswith("-0002") and d["numero"].startswith("DE-") and d["numero"].endswith("-0001")
    assert (f1["ht"], f1["ttc"]) == (1620000, 1944000)
    pdf = op.get(f"/api/plateforme/documents/{f1['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_place_utilisateur_essentiel(client):
    cid = abonner(client, "A", "essentiel")
    with client.Session() as db:
        assert offres.place_utilisateur(db, cid)  # 1 exploitant sur 2
        db.add(User(company_id=cid, email="x@a.fr", password_hash="x"))
        db.commit()
        assert not offres.place_utilisateur(db, cid)


def test_grille_publique_sans_connexion(client):
    r = client.get("/api/offres")
    assert r.status_code == 200
    o = {x["id"]: x for x in r.json()["offres"]}
    assert (o["essentiel"]["prix_eur"], o["pro"]["prix_eur"], o["pro"]["minimum_eur"]) == (45, 75, 900) and o["pro"]["inclus"]
