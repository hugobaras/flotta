import io
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
from helpers import PNG, SIGNATURE, login, make_admin, paris, reponses, send, upload














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
    r = client.post(f"/api/admin/vehicules/{vid}/debloquer", json={"commentaire": "Freins vérifiés"})
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
    ("get", "/api/admin/tableau"),
    ("get", "/api/admin/controles/1"),
    ("get", "/api/admin/photos/1"),
    ("get", "/api/admin/deblocages"),
    ("get", "/api/admin/rappels"),
    ("get", "/api/admin/controles/1/pdf"),
    ("get", "/api/admin/logo"),
    ("post", "/api/admin/logo"),
    ("get", "/api/admin/parametres"),
    ("patch", "/api/admin/parametres"),
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
    assert sorted(v["plaque"] for v in a.get("/api/admin/vehicules").json()) == ["AA-111-AA", "ZZ-999-ZZ"]
    assert a.get("/api/admin/controles").json() == []
    b_vehicle = b.get("/api/admin/vehicules").json()[0]
    assert b_vehicle["bloque"] is True
    assert a.post(f"/api/admin/vehicules/{b_vehicle['id']}/debloquer", json={"commentaire": "intrus"}).status_code == 404
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
    saved = a.get(f"/api/admin/controles/{a.get('/api/admin/controles').json()[0]['id']}").json()
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
        has_defaut = c.exec_driver_sql("select has_defaut from checks").scalar()
    old = json.loads(reponses_json)[0]
    assert old["libelle"].startswith("Freins : pédale ferme") and old["critique"] is True and old["ok"] is False
    assert n_items == len(DEFAULT_ITEMS)
    assert has_defaut == 1  # recalculé pour les anciens contrôles


# --- Exploitation : déblocage, tableau de bord, détail, photos, rappel, purge ---

import io  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from app import photos  # noqa: E402
from app import main as main_module  # noqa: E402
from app.exploitation import sans_controle  # noqa: E402
from app.models import Check, CheckPhoto  # noqa: E402
from app.retention import purge  # noqa: E402







def blocked_vehicle(a):
    send(a, "tok-a", "freins")
    return next(v for v in a.get("/api/admin/vehicules").json() if v["token"] == "tok-a")["id"]


def test_unblock_requires_comment(a):
    vid = blocked_vehicle(a)
    url = f"/api/admin/vehicules/{vid}/debloquer"
    assert a.post(url, json={}).status_code == 422
    assert a.post(url, json={"commentaire": "   "}).status_code == 422
    assert a.get("/api/admin/vehicules").json()[0]["bloque"] is True


def test_unblock_is_traced(a):
    vid = blocked_vehicle(a)
    assert a.post(f"/api/admin/vehicules/{vid}/debloquer", json={"commentaire": "Plaquettes changées"}).status_code == 200
    (row,) = a.get("/api/admin/deblocages").json()
    assert row["plaque"] == "AA-111-AA" and row["par"] == "a@a.fr" and row["commentaire"] == "Plaquettes changées"
    assert row["created_at"]
    again = a.post(f"/api/admin/vehicules/{vid}/debloquer", json={"commentaire": "deuxième fois"})
    assert again.status_code == 409  # pas de déblocage fantôme dans l'historique
    assert len(a.get("/api/admin/deblocages").json()) == 1


def statuts(c, **params):
    return {v["plaque"]: v["statut"] for v in c.get("/api/admin/tableau", params=params).json()["vehicules"]}


def test_dashboard_statuses(a):
    assert statuts(a) == {"AA-111-AA": "non_controle", "ZZ-999-ZZ": "non_controle"}
    send(a, "tok-a2")
    assert statuts(a)["ZZ-999-ZZ"] == "controle"
    send(a, "tok-a2", "retros")  # défaut mineur : le dernier contrôle du jour l'emporte
    assert statuts(a)["ZZ-999-ZZ"] == "defaut"
    send(a, "tok-a", "freins")
    assert statuts(a)["AA-111-AA"] == "bloque"
    # un autre jour : pas de contrôle, mais le blocage est un état courant du véhicule
    assert statuts(a, date="2000-01-01") == {"AA-111-AA": "bloque", "ZZ-999-ZZ": "non_controle"}


def test_dashboard_only_own_vehicles(a, b):
    assert sorted(statuts(b)) == ["BB-222-BB"]
    assert "BB-222-BB" not in statuts(a)


def test_controls_filters(a):
    send(a, "tok-a")
    send(a, "tok-a2", "retros")
    a.post("/api/controle/tok-a2", json={"conducteur": "Zoé Martin", "reponses": reponses(a, "tok-a2")})
    ids = {v["token"]: v["id"] for v in a.get("/api/admin/vehicules").json()}
    get = lambda **p: a.get("/api/admin/controles", params=p).json()  # noqa: E731
    assert len(get()) == 3
    assert {c["plaque"] for c in get(vehicule_id=ids["tok-a"])} == {"AA-111-AA"}
    assert [c["conducteur"] for c in get(conducteur="zoé")] == ["Zoé Martin"]
    assert len(get(conducteur="%")) == 0  # le joker n'est pas interprété
    assert [c["plaque"] for c in get(defaut=True)] == ["ZZ-999-ZZ"]
    assert len(get(date="2000-01-01")) == 0


def test_check_detail_with_signature_and_position(a):
    cid = send(a, "tok-a", signature=SIGNATURE, lat=47.2, lng=-1.55)["id"]
    d = a.get(f"/api/admin/controles/{cid}").json()
    assert d["plaque"] == "AA-111-AA" and d["signature"] == SIGNATURE
    assert (d["lat"], d["lng"]) == (47.2, -1.55) and len(d["reponses"]) == len(DEFAULT_ITEMS)


@pytest.mark.parametrize("extra", [
    {"signature": "data:text/html;base64,PHNjcmlwdD4="},
    {"lat": 47.2},
    {"lat": 95, "lng": 0},
    {"lat": 0, "lng": 181},
])
def test_invalid_signature_or_position_rejected(a, extra):
    r = a.post("/api/controle/tok-a", json={"conducteur": "P", "reponses": reponses(a, "tok-a"), **extra})
    assert r.status_code == 422




def test_photo_upload_and_download(a, b, upload_dir):
    cid = send(a, "tok-a", "pneus")["id"]
    pid = upload(a, cid).json()["id"]
    assert a.get(f"/api/admin/controles/{cid}").json()["photos"] == [pid]
    got = a.get(f"/api/admin/photos/{pid}")
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert b.get(f"/api/admin/photos/{pid}").status_code == 404  # autre société


def test_photo_rejects_wrong_content_even_with_image_name(a, upload_dir):
    cid = send(a, "tok-a")["id"]
    assert upload(a, cid, b"<script>alert(1)</script>", name="x.png").status_code == 415
    assert upload(a, cid, PNG + b"0" * photos.MAX_BYTES).status_code == 413
    assert list(upload_dir.rglob("*.*")) == []


def test_photo_limit_per_check(a, upload_dir):
    cid = send(a, "tok-a")["id"]
    for _ in range(photos.MAX_PER_CHECK):
        assert upload(a, cid).status_code == 201
    assert upload(a, cid).status_code == 409


def test_photo_only_on_own_vehicle_and_recent_check(a, upload_dir, monkeypatch):
    cid = send(a, "tok-a")["id"]
    assert upload(a, cid, token="tok-a2").status_code == 404  # contrôle d'un autre camion
    monkeypatch.setattr(main_module, "PHOTO_WINDOW", timedelta(seconds=-1))
    assert upload(a, cid).status_code == 403


def test_photo_cross_tenant_token(a, b, upload_dir):
    cid = send(a, "tok-a")["id"]
    assert upload(b, cid, token="tok-b").status_code == 404


def test_check_detail_isolation(a, b):
    cid = send(b, "tok-b")["id"]
    assert a.get(f"/api/admin/controles/{cid}").status_code == 404
    assert [c["plaque"] for c in a.get("/api/admin/controles").json()] == []


def test_deblocages_isolation(a, b):
    vid_b = next(v["id"] for v in b.get("/api/admin/vehicules").json())
    send(b, "tok-b", "pneus")
    b.post(f"/api/admin/vehicules/{vid_b}/debloquer", json={"commentaire": "Pneu changé"})
    assert a.get("/api/admin/deblocages").json() == []
    assert len(b.get("/api/admin/deblocages").json()) == 1




def test_reminder_lists_unchecked_vehicles_after_threshold(a, client):
    with client.Session() as db:
        company = db.get(Company, 1)
        assert company.heure_rappel == "08:00"
        assert sans_controle(db, company, paris(7, 59)) == []
        assert {v.plaque for v in sans_controle(db, company, paris(8, 0))} == {"AA-111-AA", "ZZ-999-ZZ"}
        db.add(Check(company_id=1, vehicle_id=1, conducteur="P", reponses=[], created_at=paris(6, 30)))
        db.commit()
        assert [v.plaque for v in sans_controle(db, company, paris(9))] == ["ZZ-999-ZZ"]
        # un contrôle de la veille ne compte pas
        db.add(Check(company_id=1, vehicle_id=2, conducteur="P", reponses=[], created_at=paris(9) - timedelta(days=1)))
        db.commit()
        assert [v.plaque for v in sans_controle(db, company, paris(9))] == ["ZZ-999-ZZ"]




def test_settings_admin_only_and_validated(a, client):
    assert a.get("/api/admin/parametres").json() == {
        "heure_rappel": "08:00", "retention_jours": 1095, "alert_emails": [], "logo": False,
        "cout_km_eur": 0, "conso_l_100km": 32, "prix_carburant_eur_l": 1.7, "peage_eur_km": 0}
    assert a.patch("/api/admin/parametres", json={"heure_rappel": "07:30"}).status_code == 403
    make_admin(client, "a@a.fr")
    assert a.patch("/api/admin/parametres", json={"heure_rappel": "25:00"}).status_code == 422
    assert a.patch("/api/admin/parametres", json={"retention_jours": 5}).status_code == 422
    r = a.patch("/api/admin/parametres", json={"heure_rappel": "07:30", "retention_jours": 365})
    assert (r.json()["heure_rappel"], r.json()["retention_jours"]) == ("07:30", 365)


def test_purge_respects_each_company_retention(a, client, upload_dir):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    old, recent = now - timedelta(days=1200), now - timedelta(days=100)
    with client.Session() as db:
        db.get(Company, 2).retention_jours = 30
        old_a = Check(company_id=1, vehicle_id=1, conducteur="P", reponses=[], created_at=old)
        new_a = Check(company_id=1, vehicle_id=1, conducteur="P", reponses=[], created_at=recent)
        old_b = Check(company_id=2, vehicle_id=3, conducteur="P", reponses=[], created_at=recent)
        db.add_all([old_a, new_a, old_b])
        db.flush()
        name = photos.save(1, PNG, "png")
        db.add(CheckPhoto(company_id=1, check_id=old_a.id, fichier=name))
        db.commit()
        assert (upload_dir / "1" / name).exists()
        assert purge(db, now) == 2  # vieux contrôle de A (3 ans) + contrôle de B (durée 30 jours)
        left = db.query(Check).all()
        assert [c.id for c in left] == [new_a.id]
        assert db.query(CheckPhoto).count() == 0 and not (upload_dir / "1" / name).exists()
