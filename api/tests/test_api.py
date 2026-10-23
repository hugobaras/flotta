import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.checklists import CHECKLIST
from app.db import Base, get_db
from app.main import app
from app.models import Company, Vehicle


@pytest.fixture
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session() as db:
        a = Company(nom="A", api_key="key-a")
        b = Company(nom="B", api_key="key-b")
        db.add_all([a, b])
        db.flush()
        db.add_all([
            Vehicle(company_id=a.id, plaque="AA-111-AA", token="tok-a"),
            Vehicle(company_id=b.id, plaque="BB-222-BB", token="tok-b"),
        ])
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield TestClient(app)  # sans lifespan : pas de seed, pas de create_all sur la vraie base
    app.dependency_overrides.clear()


def reponses(*ko):
    return [{"id": i["id"], "ok": i["id"] not in ko} for i in CHECKLIST]


def test_driver_sees_checklist_without_account(client):
    r = client.get("/api/controle/tok-a")
    assert r.status_code == 200
    assert r.json()["plaque"] == "AA-111-AA"
    assert len(r.json()["checklist"]) == len(CHECKLIST)


def test_unknown_token(client):
    assert client.get("/api/controle/nope").status_code == 404


def test_critical_defect_blocks_vehicle_and_unblock(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses("freins")})
    assert r.status_code == 201 and r.json()["bloque"] is True
    vid = client.get("/api/admin/vehicules", headers={"x-api-key": "key-a"}).json()[0]["id"]
    r = client.post(f"/api/admin/vehicules/{vid}/debloquer", headers={"x-api-key": "key-a"})
    assert r.json()["bloque"] is False


def test_minor_defect_does_not_block(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses("retros")})
    assert r.json() == {"id": 1, "defaut_critique": False, "bloque": False}


def test_incomplete_checklist_rejected(client):
    r = client.post("/api/controle/tok-a", json={"conducteur": "Paul", "reponses": reponses()[:2]})
    assert r.status_code == 422


def test_admin_requires_valid_key(client):
    assert client.get("/api/admin/vehicules").status_code == 422
    assert client.get("/api/admin/vehicules", headers={"x-api-key": "bad"}).status_code == 401


def test_tenant_isolation(client):
    client.post("/api/controle/tok-b", json={"conducteur": "Zoé", "reponses": reponses("pneus")})
    a = {"x-api-key": "key-a"}
    assert [v["plaque"] for v in client.get("/api/admin/vehicules", headers=a).json()] == ["AA-111-AA"]
    assert client.get("/api/admin/controles", headers=a).json() == []
    b_vid = client.get("/api/admin/vehicules", headers={"x-api-key": "key-b"}).json()[0]["id"]
    assert client.post(f"/api/admin/vehicules/{b_vid}/debloquer", headers=a).status_code == 404
