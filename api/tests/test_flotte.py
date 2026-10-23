import io
import re
import time
from datetime import datetime, timedelta, timezone

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app import badge as badge_mod
from app import main as main_module
from app.models import Alert, Check, Company, Driver, Vehicle
from helpers import make_admin, reponses, send

BASE = {"plaque": "FG-482-KL", "type": "poids_lourd", "hauteur_m": 3.9, "largeur_m": 2.55, "longueur_m": 16.5,
        "ptac_kg": 40000, "charge_utile_kg": 25000, "essieux": 5, "palettes": 33, "capacite_kg": 25000,
        "capacite_m3": 90, "adr": False, "frigo": True}


def creer(c, **extra):
    return c.post("/api/admin/vehicules", json={**BASE, **extra})


# --- CRUD véhicules ---


def test_fleet_routes_require_login(client):
    for method, url in [("get", "/api/admin/vehicules"), ("post", "/api/admin/vehicules"),
                        ("patch", "/api/admin/vehicules/1"), ("delete", "/api/admin/vehicules/1"),
                        ("get", "/api/admin/vehicules/qr.pdf"), ("post", "/api/admin/vehicules/import"),
                        ("post", "/api/admin/vehicules/import/apercu"), ("get", "/api/admin/conducteurs"),
                        ("post", "/api/admin/conducteurs"), ("patch", "/api/admin/conducteurs/1"),
                        ("delete", "/api/admin/conducteurs/1")]:
        assert getattr(client, method)(url).status_code == 401, (method, url)


def test_create_vehicle_with_gauge_and_capacity(a):
    r = creer(a, plaque=" fg-482-kl ")
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["plaque"] == "FG-482-KL" and v["hauteur_m"] == 3.9 and v["frigo"] is True and len(v["token"]) >= 10
    assert any(x["plaque"] == "FG-482-KL" for x in a.get("/api/admin/vehicules").json())


@pytest.mark.parametrize("extra", [
    {"plaque": "!"}, {"plaque": ""}, {"hauteur_m": 9}, {"hauteur_m": 0.2}, {"largeur_m": 6}, {"essieux": 1},
    {"ptac_kg": 100}, {"type": "fusée"}, {"palettes": -1},
])
def test_create_vehicle_validation(a, extra):
    assert creer(a, **extra).status_code == 422


def test_duplicate_plate_rejected_per_company(a, b):
    assert creer(a).status_code == 201
    assert creer(a).status_code == 409
    assert creer(b).status_code == 201  # une autre société peut avoir la même plaque


def test_patch_vehicle_partial_and_clear(a):
    vid = creer(a).json()["id"]
    r = a.patch(f"/api/admin/vehicules/{vid}", json={"hauteur_m": 4.0, "frigo": False})
    assert r.json()["hauteur_m"] == 4.0 and r.json()["frigo"] is False and r.json()["ptac_kg"] == 40000
    assert a.patch(f"/api/admin/vehicules/{vid}", json={"ptac_kg": ""}).json()["ptac_kg"] is None
    assert a.patch(f"/api/admin/vehicules/{vid}", json={"plaque": ""}).status_code == 422
    assert a.patch(f"/api/admin/vehicules/{vid}", json={"plaque": "AA-111-AA"}).status_code == 409


def test_new_vehicle_type_gets_default_checklist(a):
    token = creer(a, type="utilitaire").json()["token"]
    r = a.get(f"/api/controle/{token}")
    assert r.status_code == 200 and len(r.json()["checklist"]) > 0


def test_deactivated_vehicle_leaves_dashboard_and_qr_code(a):
    vid = creer(a).json()["id"]
    token = next(v["token"] for v in a.get("/api/admin/vehicules").json() if v["id"] == vid)
    a.patch(f"/api/admin/vehicules/{vid}", json={"actif": False})
    assert a.get(f"/api/controle/{token}").status_code == 404
    assert "FG-482-KL" not in [v["plaque"] for v in a.get("/api/admin/tableau").json()["vehicules"]]
    pdf = a.get("/api/admin/vehicules/qr.pdf", params={"ids": str(vid)})
    assert pdf.status_code == 404  # rien à imprimer


def test_delete_vehicle_without_history_and_with_history(a):
    vid = creer(a).json()["id"]
    assert a.delete(f"/api/admin/vehicules/{vid}").status_code == 204
    avec_historique = a.get("/api/admin/vehicules").json()[0]["id"]
    send(a, "tok-a")
    assert a.delete(f"/api/admin/vehicules/{avec_historique}").status_code == 409


def test_fleet_isolation(a, b):
    vid_a = a.get("/api/admin/vehicules").json()[0]["id"]
    assert [v["plaque"] for v in b.get("/api/admin/vehicules").json()] == ["BB-222-BB"]
    assert b.patch(f"/api/admin/vehicules/{vid_a}", json={"actif": False}).status_code == 404
    assert b.delete(f"/api/admin/vehicules/{vid_a}").status_code == 404
    assert b.get("/api/admin/vehicules/qr.pdf", params={"ids": str(vid_a)}).status_code == 404


# --- Import CSV / Excel ---


def csv_bytes(texte: str, encodage="utf-8"):
    return {"fichier": ("flotte.csv", io.BytesIO(texte.encode(encodage)), "text/csv")}


def apercu(c, texte, **kw):
    return c.post("/api/admin/vehicules/import/apercu", files=csv_bytes(texte, **kw))


CSV_OK = ("Plaque;Type;Hauteur (m);Largeur;Longueur;PTAC;Essieux;Palettes;ADR;Frigo;Commentaire\n"
          "FG-482-KL;poids_lourd;3,9;2,55;16,5;40000;5;33;non;oui;ignoré\n"
          "HN-907-PQ;porteur;3,6;2,5;9;19000;2;18;oui;non;\n")


def test_import_preview_french_csv(a):
    r = apercu(a, CSV_OK, encodage="cp1252")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 2 and d["valides"] == 2 and d["en_erreur"] == 0
    assert "Commentaire" in d["colonnes_ignorees"] and "Plaque" in d["colonnes_reconnues"]
    assert [l["action"] for l in d["lignes"]] == ["creer", "creer"]
    assert len(a.get("/api/admin/vehicules").json()) == 2  # l'aperçu n'écrit rien


def test_import_applies_valid_rows_and_reports_errors_line_by_line(a):
    texte = ("plaque;hauteur;essieux;frigo\n"
             "FG-482-KL;3,9;5;oui\n"        # ligne 2 : ok
             "??;3,9;5;non\n"               # ligne 3 : plaque invalide
             "HN-907-PQ;abc;2;non\n"        # ligne 4 : nombre invalide
             "CC-215-RT;3,8;1;non\n"        # ligne 5 : essieux hors limites
             "FG-482-KL;3,9;5;non\n"        # ligne 6 : doublon dans le fichier
             "EB-660-MV;3,5;2;peut-être\n"  # ligne 7 : booléen invalide
             "AA-111-AA;3,7;2;non\n")       # ligne 8 : plaque existante -> mise à jour
    r = a.post("/api/admin/vehicules/import", files=csv_bytes(texte))
    d = r.json()
    assert (d["crees"], d["mis_a_jour"], d["ignores"]) == (1, 1, 5)
    par_ligne = {l["ligne"]: l for l in d["lignes"]}
    assert par_ligne[2]["action"] == "creer" and par_ligne[8]["action"] == "mettre_a_jour"
    for n in (3, 4, 5, 6, 7):
        assert par_ligne[n]["erreurs"] and par_ligne[n]["action"] is None, n
    plaques = {v["plaque"]: v for v in a.get("/api/admin/vehicules").json()}
    assert "FG-482-KL" in plaques and "HN-907-PQ" not in plaques and plaques["AA-111-AA"]["hauteur_m"] == 3.7


def test_import_excel_file(a):
    wb = Workbook()
    ws = wb.active
    ws.append(["Immatriculation", "Hauteur", "Palettes", "Frigorifique"])
    ws.append(["FG-482-KL", 3.9, 33, "oui"])
    buf = io.BytesIO()
    wb.save(buf)
    r = a.post("/api/admin/vehicules/import", files={"fichier": ("flotte.xlsx", io.BytesIO(buf.getvalue()), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["crees"] == 1
    v = next(v for v in a.get("/api/admin/vehicules").json() if v["plaque"] == "FG-482-KL")
    assert v["hauteur_m"] == 3.9 and v["palettes"] == 33 and v["frigo"] is True


@pytest.mark.parametrize("texte,code", [("", 422), ("plaque\n", 422), ("hauteur;essieux\n3,5;2\n", 422)])
def test_import_rejects_unusable_files(a, texte, code):
    assert apercu(a, texte).status_code == code


def test_import_rejects_oversized_and_garbage_excel(a):
    gros = "plaque\n" + "AB-123-CD\n" * (600_000)
    assert apercu(a, gros).status_code == 413
    faux = a.post("/api/admin/vehicules/import/apercu", files={"fichier": ("x.xlsx", io.BytesIO(b"PKnot a zip"), "application/octet-stream")})
    assert faux.status_code == 422


def test_import_is_scoped_to_company(a, b):
    a.post("/api/admin/vehicules/import", files=csv_bytes("plaque\nZZ-000-ZZ\n"))
    assert "ZZ-000-ZZ" not in [v["plaque"] for v in b.get("/api/admin/vehicules").json()]


# --- Planches de QR codes ---


def pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", pdf))


def test_qr_sheet_six_per_page(a):
    for i in range(6):
        creer(a, plaque=f"QR-{100 + i}-AA")
    r = a.get("/api/admin/vehicules/qr.pdf")  # 2 véhicules d'origine + 6 = 8 -> 2 pages
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert pages(r.content) == 2
    ids = ",".join(str(v["id"]) for v in a.get("/api/admin/vehicules").json()[:6])
    assert pages(a.get("/api/admin/vehicules/qr.pdf", params={"ids": ids}).content) == 1
    assert a.get("/api/admin/vehicules/qr.pdf", params={"ids": "x"}).status_code == 422


def test_qr_code_points_to_driver_page(monkeypatch):
    from app.qr import planche_qr
    scanned = []
    import qrcode
    original = qrcode.make
    monkeypatch.setattr(qrcode, "make", lambda url, **kw: (scanned.append(url), original(url, **kw))[1])
    planche_qr([("AB-123-CD", "jeton123")], "https://flotta.exemple/")
    assert scanned == ["https://flotta.exemple/c/jeton123"]


# --- Conducteurs, PIN, badge ---


def nouveau_conducteur(c, nom="Karim Benali", **extra):
    r = c.post("/api/admin/conducteurs", json={"nom": nom, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_driver_created_with_one_time_pin_and_hashed_in_db(a, client):
    d = nouveau_conducteur(a)
    assert re.fullmatch(r"\d{4}", d["pin"])
    assert "pin" not in a.get("/api/admin/conducteurs").json()[0]
    with client.Session() as db:
        h = db.scalar(select(Driver.pin_hash).where(Driver.id == d["id"]))
    assert h != d["pin"] and len(h) == 64


def test_driver_usual_vehicle_must_belong_to_company(a, b):
    vid_b = b.get("/api/admin/vehicules").json()[0]["id"]
    assert a.post("/api/admin/conducteurs", json={"nom": "Zoé Martin", "vehicule_habituel_id": vid_b}).status_code == 404
    vid_a = a.get("/api/admin/vehicules").json()[0]["id"]
    d = nouveau_conducteur(a, vehicule_habituel_id=vid_a)
    assert d["vehicule_habituel"] == "AA-111-AA"


def test_pins_unique_in_company(a):
    pins = {nouveau_conducteur(a, nom=f"Conducteur {i}")["pin"] for i in range(40)}
    assert len(pins) == 40


def test_driver_update_deactivate_reset_pin(a):
    d = nouveau_conducteur(a)
    r = a.patch(f"/api/admin/conducteurs/{d['id']}", json={"nom": "Karim B.", "reinitialiser_pin": True})
    assert r.json()["nom"] == "Karim B." and re.fullmatch(r"\d{4}", r.json()["pin"])
    r = a.patch(f"/api/admin/conducteurs/{d['id']}", json={"actif": False})
    assert r.json()["actif"] is False and "pin" not in r.json()


def identifier(c, token, pin):
    return c.post(f"/api/controle/{token}/identifier", json={"pin": pin})


def test_identify_with_pin_returns_name_and_badge(a):
    d = nouveau_conducteur(a)
    r = identifier(a, "tok-a", d["pin"])
    assert r.status_code == 200 and r.json()["nom"] == "Karim Benali" and r.json()["badge"].count(".") == 3


def test_identify_rejects_bad_pin_inactive_driver_and_other_company(a, b):
    d = nouveau_conducteur(a)
    mauvais = f"{(int(d['pin']) % 9000) + 1000 + 1}"[:4]
    assert identifier(a, "tok-a", mauvais if mauvais != d["pin"] else "0000").status_code == 401
    assert identifier(b, "tok-b", d["pin"]).status_code == 401  # le PIN d'une autre société ne marche pas
    a.patch(f"/api/admin/conducteurs/{d['id']}", json={"actif": False})
    assert identifier(a, "tok-a", d["pin"]).status_code == 401
    assert identifier(a, "tok-a", "12a4").status_code == 422


def test_identify_is_rate_limited_per_vehicle(a):
    main_module.login_pin_echecs.clear()
    d = nouveau_conducteur(a)
    faux = "0000" if d["pin"] != "0000" else "1111"
    for _ in range(main_module.PIN_MAX_ECHECS):
        assert identifier(a, "tok-a", faux).status_code == 401
    assert identifier(a, "tok-a", d["pin"]).status_code == 429  # même le bon code est refusé
    assert identifier(a, "tok-a2", d["pin"]).status_code == 200  # un autre camion n'est pas bloqué
    main_module.login_pin_echecs.clear()


def test_check_with_badge_records_driver_not_typed_name(a, client):
    d = nouveau_conducteur(a)
    badge = identifier(a, "tok-a", d["pin"]).json()["badge"]
    r = a.post("/api/controle/tok-a", json={"badge": badge, "conducteur": "Usurpateur", "reponses": reponses(a, "tok-a")})
    assert r.status_code == 201
    with client.Session() as db:
        c = db.get(Check, r.json()["id"])
        assert c.conducteur == "Karim Benali" and c.conducteur_id == d["id"]


def test_forged_expired_or_foreign_badge_rejected(a, b):
    d = nouveau_conducteur(a)
    vrai = identifier(a, "tok-a", d["pin"]).json()["badge"]
    expire, _ = badge_mod.signer_badge(d["id"], 1, maintenant=time.time() - 13 * 3600)
    falsifie = vrai[:-4] + ("0000" if not vrai.endswith("0000") else "1111")
    autre_societe, _ = badge_mod.signer_badge(d["id"], 2)
    for mauvais in (expire, falsifie, autre_societe, "n.importe.quoi.ici", "x"):
        r = a.post("/api/controle/tok-a", json={"badge": mauvais, "reponses": reponses(a, "tok-a")})
        assert r.status_code == 401, mauvais
    # un badge de la société A ne sert pas sur un camion de la société B
    r = b.post("/api/controle/tok-b", json={"badge": vrai, "reponses": reponses(b, "tok-b")})
    assert r.status_code == 401


def test_deactivated_driver_badge_stops_working(a):
    d = nouveau_conducteur(a)
    badge = identifier(a, "tok-a", d["pin"]).json()["badge"]
    a.patch(f"/api/admin/conducteurs/{d['id']}", json={"actif": False})
    assert a.post("/api/controle/tok-a", json={"badge": badge, "reponses": reponses(a, "tok-a")}).status_code == 401


def test_name_fallback_still_works_and_something_is_required(a):
    ok = a.post("/api/controle/tok-a", json={"conducteur": "Hors ligne", "reponses": reponses(a, "tok-a")})
    assert ok.status_code == 201
    assert a.post("/api/controle/tok-a", json={"reponses": reponses(a, "tok-a")}).status_code == 422
    assert a.post("/api/controle/tok-a", json={"conducteur": "  ", "reponses": reponses(a, "tok-a")}).status_code == 422


def test_driver_delete_rules(a):
    d = nouveau_conducteur(a)
    assert a.delete(f"/api/admin/conducteurs/{d['id']}").status_code == 204
    d2 = nouveau_conducteur(a, nom="Sophie Lambert")
    badge = identifier(a, "tok-a", d2["pin"]).json()["badge"]
    a.post("/api/controle/tok-a", json={"badge": badge, "reponses": reponses(a, "tok-a")})
    assert a.delete(f"/api/admin/conducteurs/{d2['id']}").status_code == 409


def test_deleting_vehicle_clears_usual_vehicle(a):
    vid = creer(a).json()["id"]
    d = nouveau_conducteur(a, vehicule_habituel_id=vid)
    a.delete(f"/api/admin/vehicules/{vid}")
    assert next(x for x in a.get("/api/admin/conducteurs").json() if x["id"] == d["id"])["vehicule_habituel_id"] is None


def test_driver_isolation(a, b):
    d = nouveau_conducteur(a)
    assert b.get("/api/admin/conducteurs").json() == []
    assert b.patch(f"/api/admin/conducteurs/{d['id']}", json={"actif": False}).status_code == 404
    assert b.delete(f"/api/admin/conducteurs/{d['id']}").status_code == 404


# --- Idempotence et envoi différé (mode hors ligne) ---


def poster(c, token, **extra):
    return c.post(f"/api/controle/{token}", json={"conducteur": "Paul", "reponses": reponses(c, token, *extra.pop("ko", ())), **extra})


def test_replayed_submission_creates_no_duplicate(a, client):
    r1 = poster(a, "tok-a", client_id="abcdefgh-1234", ko=("freins",))
    r2 = poster(a, "tok-a", client_id="abcdefgh-1234", ko=("freins",))
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.json()["id"] == r2.json()["id"]
    with client.Session() as db:
        assert len(db.scalars(select(Check)).all()) == 1
        assert len(db.scalars(select(Alert)).all()) == 1  # pas de seconde alerte


def test_same_client_id_allowed_in_other_company(a, b):
    assert poster(a, "tok-a", client_id="commun-1234").status_code == 201
    assert poster(b, "tok-b", client_id="commun-1234").status_code == 201


def test_client_id_format_validated(a):
    assert poster(a, "tok-a", client_id="court").status_code == 422
    assert poster(a, "tok-a", client_id="a b c d e f g h").status_code == 422


def test_fait_le_sets_real_time_within_limits(a, client):
    hier = datetime.now(timezone.utc) - timedelta(hours=20)
    r = poster(a, "tok-a", fait_le=hier.isoformat())
    with client.Session() as db:
        c = db.get(Check, r.json()["id"])
        cree = c.created_at.replace(tzinfo=timezone.utc)
        recu = c.recu_le.replace(tzinfo=timezone.utc)
    assert abs((cree - hier).total_seconds()) < 2 and (datetime.now(timezone.utc) - recu).total_seconds() < 30


def test_too_old_fait_le_is_ignored(a, client):
    trop_ancien = datetime.now(timezone.utc) - timedelta(days=30)
    r = poster(a, "tok-a", fait_le=trop_ancien.isoformat())
    with client.Session() as db:
        c = db.get(Check, r.json()["id"])
        assert abs((c.created_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()) < 60


def test_future_fait_le_is_ignored(a, client):
    futur = datetime.now(timezone.utc) + timedelta(days=2)
    r = poster(a, "tok-a", fait_le=futur.isoformat())
    with client.Session() as db:
        c = db.get(Check, r.json()["id"])
        assert c.created_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) + timedelta(minutes=1)


def test_late_synced_check_still_accepts_photos(a, upload_dir):
    hier = datetime.now(timezone.utc) - timedelta(hours=20)
    cid = poster(a, "tok-a", fait_le=hier.isoformat()).json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    r = a.post(f"/api/controle/tok-a/{cid}/photos", files={"photo": ("p.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 201  # la fenêtre part de la réception, pas de l'heure du contrôle


def test_offline_check_from_yesterday_counts_for_yesterdays_dashboard(a):
    hier = datetime.now(timezone.utc) - timedelta(hours=26)
    poster(a, "tok-a", fait_le=hier.isoformat())
    jour = hier.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Paris")).date().isoformat()
    ligne = next(v for v in a.get("/api/admin/tableau", params={"date": jour}).json()["vehicules"] if v["plaque"] == "AA-111-AA")
    assert ligne["controle"] is not None
