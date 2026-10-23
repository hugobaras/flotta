import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, photos
from app.auth import hasher
from app.checklists import create_default_template
from app.db import Base, get_db
from app.main import app
from app.models import Company, User, Vehicle
from helpers import login

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
            Vehicle(company_id=a.id, plaque="ZZ-999-ZZ", token="tok-a2"),
            Vehicle(company_id=b.id, plaque="BB-222-BB", token="tok-b"),
        ])
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    auth._failures.clear()
    c = TestClient(app)  # sans lifespan : pas de seed sur la vraie base
    c.Session = Session  # pour les tests qui touchent directement la base
    yield c
    app.dependency_overrides.clear()

@pytest.fixture
def a(client):
    assert login(client, "a@a.fr").status_code == 200
    return client

@pytest.fixture
def b():
    c = TestClient(app)  # second client, cookies séparés
    assert login(c, "b@b.fr").status_code == 200
    return c

@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(photos, "UPLOAD_DIR", tmp_path)
    return tmp_path
