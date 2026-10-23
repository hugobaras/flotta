import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth
from app.auth import hasher
from app.checklists import DEFAULT_ITEMS, create_default_template
from app.db import Base, get_db
from app.main import app
from app.models import Company, User, Vehicle


@pytest.fixture
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session() as db:
        a = Company(nom="A")
        b = Company(nom="B")
        db.add_all([a, b])
        db.flush()
        pw = hasher.hash("motdepasse-ok")
        db.add_all([
            User(company_id=a.id, email="a@a.fr", password_hash=pw),
            User(company_id=b.id, email="b@b.fr", password_hash=pw),
        ])
        create_default_template(db, a.id)
        create_default_template(db, b.id)
        db.add_all([
            Vehicle(company_id=a.id, plaque="AA-111-AA", token="tok-a"),
            Vehicle(company_id=b.id, plaque="BB-222-BB", token="tok-b"),
        ])
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    auth._failures.clear()
    yield TestClient(app)  # sans lifespan : pas de seed sur la vraie base
    app.dependency_overrides.clear()


def login(client, email, password="motdepasse-ok"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def a(client):
    assert login(client, "a@a.fr").status_code == 200
    return client


@pytest.fixture
def b():
    c = TestClient(app)  # second client, cookies séparés
    assert login(c, "b@b.fr").status_code == 200
    return c


KEYS = {"pneus": 0, "freins": 1, "feux": 2, "niveaux": 3, "retros": 4, "docs": 5}


def reponses(client, token, *ko):
    """Réponses complètes pour la checklist servie au chauffeur ; `ko` = clés des points en défaut."""
    items = client.get(f"/api/controle/{token}").json()["checklist"]
    ko_libelles = {DEFAULT_ITEMS[KEYS[k]][0] for k in ko}
    return [{"id": i["id"], "ok": i["libelle"] not in ko_libelles} for i in items]


def test_driver_sees_checklist_without_account(client):
    r = client.get("/api/controle/tok-a")
    assert r.status_code == 200
    assert r.json()["plaque"] == "AA-111-AA"
    assert len(r.json()["checklist"]) == len(DEFAULT_ITEMS)


def test_unknown_token(client):
    assert client.get("/api/controle/nope").status_code == 404


def test_critical_defect_blocks_vehicle_and_unblock(a):
    client = a
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses(client, "tok-a", "freins")})
    assert r.status_code == 201 and r.json()["bloque"] is True
    vid = client.get("/api/admin/vehicules").json()[0]["id"]
    r = client.post(f"/api/admin/vehicules/{vid}/debloquer")
    assert r.json()["bloque"] is False


def test_minor_defect_does_not_block(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses(client, "tok-a", "retros")})
    assert r.json() == {"id": 1, "defaut_critique": False, "bloque": False}


def test_incomplete_checklist_rejected(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses(client, "tok-a")[:2]})
    assert r.status_code == 422


ADMIN_ROUTES = [
    ("get", "/api/admin/vehicules"),
    ("get", "/api/admin/controles"),
    ("post", "/api/admin/vehicules/1/debloquer"),
]


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
def test_admin_routes_require_login(client, method, url):
    assert getattr(client, method)(url).status_code == 401


def test_bad_password_and_unknown_user(client):
    assert login(client, "a@a.fr", "mauvais").status_code == 401
    assert login(client, "inconnu@x.fr").status_code == 401


def test_logout_invalidates_session(a):
    assert a.get("/api/auth/me").json()["email"] == "a@a.fr"
    a.post("/api/auth/logout")
    assert a.get("/api/admin/vehicules").status_code == 401


def test_login_rate_limited(client):
    for _ in range(auth.MAX_FAILURES):
        assert login(client, "a@a.fr", "mauvais").status_code == 401
    assert login(client, "a@a.fr").status_code == 429  # même le bon mot de passe


def test_session_cookie_is_httponly(client):
    r = login(client, "a@a.fr")
    assert "httponly" in r.headers["set-cookie"].lower()


def test_tenant_isolation(a, b):
    b.post("/api/controle/tok-b", json={"conducteur": "Zoé", "reponses": reponses(b, "tok-b", "pneus")})
    assert [v["plaque"] for v in a.get("/api/admin/vehicules").json()] == ["AA-111-AA"]
    assert a.get("/api/admin/controles").json() == []
    b_vehicle = b.get("/api/admin/vehicules").json()[0]
    assert b_vehicle["bloque"] is True
    assert a.post(f"/api/admin/vehicules/{b_vehicle['id']}/debloquer").status_code == 404
    assert b.get("/api/admin/vehicules").json()[0]["bloque"] is True
    assert len(b.get("/api/admin/controles").json()) == 1


def test_migrations_create_schema(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/m.db")
    command.upgrade(Config("alembic.ini"), "head")
    tables = create_engine(f"sqlite:///{tmp_path}/m.db").connect().exec_driver_sql(
        "select name from sqlite_master").fetchall()
    assert {"companies", "users", "sessions", "vehicles", "checks"} <= {t[0] for t in tables}


# --- Checklists configurables ---

def first_template(c):
    return c.get("/api/admin/checklists").json()[0]


def test_checklist_routes_require_login(client):
    assert client.get("/api/admin/checklists").status_code == 401
    assert client.post("/api/admin/checklists/1/items", json={"libelle": "x"}).status_code == 401
    assert client.patch("/api/admin/checklists/items/1", json={"actif": False}).status_code == 401
    assert client.post("/api/admin/checklists/items/1/deplacer", json={"sens": "haut"}).status_code == 401


def test_add_item_appears_for_driver(a):
    t = first_template(a)
    r = a.post(f"/api/admin/checklists/{t['id']}/items", json={"libelle": "Extincteur", "critique": True})
    assert r.status_code == 201 and r.json()["ordre"] == len(DEFAULT_ITEMS)
    libelles = [i["libelle"] for i in a.get("/api/controle/tok-a").json()["checklist"]]
    assert libelles[-1] == "Extincteur"


def test_disabled_item_hidden_and_not_required(a):
    item = first_template(a)["items"][0]
    a.patch(f"/api/admin/checklists/items/{item['id']}", json={"actif": False})
    served = a.get("/api/controle/tok-a").json()["checklist"]
    assert item["id"] not in [i["id"] for i in served]
    r = a.post("/api/controle/tok-a", json={"conducteur": "P", "reponses": reponses(a, "tok-a")})
    assert r.status_code == 201


def test_make_item_critical_blocks_vehicle(a):
    item = next(i for i in first_template(a)["items"] if i["libelle"].startswith("Niveaux"))
    a.patch(f"/api/admin/checklists/items/{item['id']}", json={"critique": True})
    r = a.post("/api/controle/tok-a", json={"conducteur": "P", "reponses": reponses(a, "tok-a", "niveaux")})
    assert r.json()["bloque"] is True


def test_reorder_item(a):
    items = first_template(a)["items"]
    moved = a.post(f"/api/admin/checklists/items/{items[1]['id']}/deplacer", json={"sens": "haut"}).json()
    assert [i["id"] for i in moved][:2] == [items[1]["id"], items[0]["id"]]
    assert [i["ordre"] for i in moved] == list(range(len(items)))
    first = a.get("/api/controle/tok-a").json()["checklist"][0]["id"]
    assert first == items[1]["id"]


def test_history_is_frozen_after_checklist_change(a):
    a.post("/api/controle/tok-a", json={"conducteur": "P", "reponses": reponses(a, "tok-a", "freins")})
    item = next(i for i in first_template(a)["items"] if i["libelle"].startswith("Freins"))
    a.patch(f"/api/admin/checklists/items/{item['id']}", json={"libelle": "Freins (renommé)", "critique": False})
    saved = a.get("/api/admin/controles").json()[0]
    freins = next(r for r in saved["reponses"] if r["id"] == item["id"])
    assert freins["libelle"].startswith("Freins :") and freins["critique"] is True
    assert saved["defaut_critique"] is True


def test_empty_label_rejected(a):
    t = first_template(a)
    assert a.post(f"/api/admin/checklists/{t['id']}/items", json={"libelle": ""}).status_code == 422


def test_no_active_item_returns_409(a):
    for i in first_template(a)["items"]:
        a.patch(f"/api/admin/checklists/items/{i['id']}", json={"actif": False})
    assert a.get("/api/controle/tok-a").status_code == 409


def test_checklist_tenant_isolation(a, b):
    ta, tb = first_template(a), first_template(b)
    assert ta["id"] != tb["id"]
    assert len(a.get("/api/admin/checklists").json()) == 1
    b_item = tb["items"][0]
    assert a.post(f"/api/admin/checklists/{tb['id']}/items", json={"libelle": "intrus"}).status_code == 404
    assert a.patch(f"/api/admin/checklists/items/{b_item['id']}", json={"actif": False}).status_code == 404
    assert a.post(f"/api/admin/checklists/items/{b_item['id']}/deplacer", json={"sens": "bas"}).status_code == 404
    assert first_template(b)["items"][0]["actif"] is True
    assert "intrus" not in [i["libelle"] for i in first_template(b)["items"]]
    # une réponse avec un point d'une autre société est refusée
    answers = reponses(a, "tok-a")
    answers[0]["id"] = b_item["id"]
    assert a.post("/api/controle/tok-a", json={"conducteur": "P", "reponses": answers}).status_code == 422


def test_migration_keeps_old_checks_readable(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path}/m.db"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "8c8df7ad29c4")
    eng = create_engine(url)
    with eng.begin() as c:
        c.exec_driver_sql("insert into companies (id, nom) values (1, 'X')")
        c.exec_driver_sql("insert into vehicles (id, company_id, plaque, token, bloque) values (1, 1, 'P', 't', 0)")
        c.exec_driver_sql(
            "insert into checks (company_id, vehicle_id, conducteur, reponses, defaut_critique, created_at) "
            """values (1, 1, 'Paul', '[{"id": "freins", "ok": false, "commentaire": ""}]', 1, '2026-01-01')""")
    command.upgrade(cfg, "head")
    with eng.connect() as c:
        reponses_json = c.exec_driver_sql("select reponses from checks").scalar()
        n_items = c.exec_driver_sql("select count(*) from checklist_items where company_id = 1").scalar()
    old = json.loads(reponses_json)[0]
    assert old["libelle"].startswith("Freins : pédale ferme") and old["critique"] is True and old["ok"] is False
    assert n_items == len(DEFAULT_ITEMS)
