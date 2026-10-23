import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth
from app.auth import hasher
from app.checklists import CHECKLIST
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


def reponses(*ko):
    return [{"id": i["id"], "ok": i["id"] not in ko} for i in CHECKLIST]


def test_driver_sees_checklist_without_account(client):
    r = client.get("/api/controle/tok-a")
    assert r.status_code == 200
    assert r.json()["plaque"] == "AA-111-AA"
    assert len(r.json()["checklist"]) == len(CHECKLIST)


def test_unknown_token(client):
    assert client.get("/api/controle/nope").status_code == 404


def test_critical_defect_blocks_vehicle_and_unblock(a):
    client = a
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses("freins")})
    assert r.status_code == 201 and r.json()["bloque"] is True
    vid = client.get("/api/admin/vehicules").json()[0]["id"]
    r = client.post(f"/api/admin/vehicules/{vid}/debloquer")
    assert r.json()["bloque"] is False


def test_minor_defect_does_not_block(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses("retros")})
    assert r.json() == {"id": 1, "defaut_critique": False, "bloque": False}


def test_incomplete_checklist_rejected(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses()[:2]})
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
    b.post("/api/controle/tok-b", json={"conducteur": "Zoé", "reponses": reponses("pneus")})
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
