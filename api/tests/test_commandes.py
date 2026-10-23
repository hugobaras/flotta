import csv
import io
import json
from datetime import date, datetime

import httpx
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app import geocodage
from app.commandes import parse_date, parse_heure
from app.models import ColumnMapping, GeocodeCache, Order

JOUR = "2026-11-02"


class FauxGeocodeur:
    """Remplace l'API Adresse : « introuvable » -> aucun résultat, « douteux » -> score 0,6, le reste -> 0,95."""

    def __init__(self, monkeypatch):
        self.appels, self.lignes_envoyees, self.panne = 0, 0, False
        monkeypatch.setattr(geocodage.httpx, "post", self._post)

    def _post(self, url, files, data, timeout):
        self.appels += 1
        if self.panne:
            raise httpx.ConnectError("service coupé")
        lignes = list(csv.DictReader(io.StringIO(files["data"][1].decode())))
        self.lignes_envoyees += len(lignes)
        sortie = io.StringIO()
        w = csv.writer(sortie)
        w.writerow(["cle", "adresse", "latitude", "longitude", "result_score", "result_label"])
        for l in lignes:
            a = l["adresse"].lower()
            if "introuvable" in a:
                w.writerow([l["cle"], l["adresse"], "", "", "", ""])
            else:
                score = 0.6 if "douteux" in a else 0.95
                h = abs(hash(l["cle"])) % 1000
                w.writerow([l["cle"], l["adresse"], 47 + h / 10000, -1.5 - h / 10000, score, l["adresse"]])
        return httpx.Response(200, text=sortie.getvalue(), request=httpx.Request("POST", url))


@pytest.fixture
def geo(monkeypatch):
    return FauxGeocodeur(monkeypatch)


def fichier(lignes, entetes=("Référence", "Client", "Adresse", "CP", "Ville", "Poids", "Palettes", "Début", "Fin", "Frigo")):
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(entetes)
    w.writerows(lignes)
    return {"fichier": ("commandes.csv", io.BytesIO(sortie.getvalue().encode("cp1252")), "text/csv")}


MAPPING = {"reference": "Référence", "client": "Client", "adresse": "Adresse", "code_postal": "CP", "ville": "Ville",
           "poids_kg": "Poids", "palettes": "Palettes", "fenetre_debut": "Début", "fenetre_fin": "Fin", "frigo": "Frigo"}


def importer(c, lignes, mapping=MAPPING, defaut=JOUR, chemin="import", **extra):
    return c.post(f"/api/admin/commandes/{chemin}", files=fichier(lignes), data={"mapping": json.dumps(mapping), "date_defaut": defaut, **extra})


def ligne(n, adresse="12 rue des Lilas", **kw):
    return [f"CMD-{n:04d}", f"Client {n}", adresse, "44000", "Nantes", "250", "2", "08:00", "12:00", "non"]


# --- Analyse des valeurs ---


@pytest.mark.parametrize("texte,attendu", [("8", "08:00"), ("8h", "08:00"), ("8h30", "08:30"), ("08:15", "08:15"),
                                           (" 17:05 ", "17:05"), ("", None), ("23h59", "23:59")])
def test_parse_heure(texte, attendu):
    assert parse_heure(texte) == attendu


@pytest.mark.parametrize("texte", ["25h", "8:75", "midi", "8h3", "-1"])
def test_parse_heure_invalid(texte):
    with pytest.raises(ValueError):
        parse_heure(texte)


@pytest.mark.parametrize("texte,attendu", [("02/11/2026", date(2026, 11, 2)), ("2026-11-02", date(2026, 11, 2)),
                                           ("02-11-2026", date(2026, 11, 2)), ("2026-11-02 00:00:00", date(2026, 11, 2)),
                                           ("", None)])
def test_parse_date(texte, attendu):
    assert parse_date(texte) == attendu


def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("32/13/2026")


# --- Mappage de colonnes ---


def test_columns_suggested_from_headers(a):
    r = a.post("/api/admin/commandes/import/colonnes", files=fichier([ligne(1)]))
    d = r.json()
    assert d["mapping_propose"]["reference"] == "Référence" and d["mapping_propose"]["code_postal"] == "CP"
    assert d["mapping_propose"]["fenetre_debut"] == "Début" and d["total"] == 1 and len(d["exemple"]) == 1
    assert {c["cle"] for c in d["champs"] if c["obligatoire"]} == {"reference", "adresse"}


def test_mapping_is_remembered_per_company(a, b, geo):
    entetes = ("N°", "Lieu")
    mapping = {"reference": "N°", "adresse": "Lieu"}
    r = a.post("/api/admin/commandes/import", files=fichier([["A1", "3 quai Duguay-Trouin Nantes"]], entetes),
               data={"mapping": json.dumps(mapping), "date_defaut": JOUR})
    assert r.status_code == 200 and r.json()["crees"] == 1
    propose = a.post("/api/admin/commandes/import/colonnes", files=fichier([["A2", "x"]], entetes)).json()["mapping_propose"]
    assert propose == mapping  # les noms de colonnes ne sont pas reconnus tout seuls : c'est bien la mémoire qui parle
    autre = b.post("/api/admin/commandes/import/colonnes", files=fichier([["A2", "x"]], entetes)).json()["mapping_propose"]
    assert autre == {}


def test_forgetting_the_mapping_when_asked(a, geo):
    importer(a, [ligne(1)], memoriser="false")
    r = a.post("/api/admin/commandes/import/colonnes", files=fichier([ligne(2)], ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")))
    assert r.json()["mapping_propose"] == {}


@pytest.mark.parametrize("mapping,code", [("pas du json", 422), ('{"inconnu": "X"}', 422), ('{"reference": "Absente", "adresse": "Adresse"}', 422),
                                          ('{"adresse": "Adresse"}', 422), ('{"reference": "Référence"}', 422)])
def test_bad_mapping_rejected(a, geo, mapping, code):
    r = a.post("/api/admin/commandes/import/apercu", files=fichier([ligne(1)]), data={"mapping": mapping, "date_defaut": JOUR})
    assert r.status_code == code


# --- Aperçu et import ---


def test_preview_reports_errors_per_line_and_writes_nothing(a, geo, client):
    sans_adresse = ligne(2, adresse="")
    sans_adresse[3] = sans_adresse[4] = ""  # ni code postal ni ville
    poids_illisible = ligne(3)
    poids_illisible[5] = "abc"
    lignes = [ligne(1), sans_adresse, poids_illisible, ligne(4), ligne(4)]  # la dernière double la référence CMD-0004
    d = importer(a, lignes, chemin="import/apercu").json()
    assert (d["total"], d["valides"], d["en_erreur"]) == (5, 2, 3)
    erreurs = {l["ligne"]: l["erreurs"] for l in d["lignes"]}
    assert not erreurs[2] and erreurs[3] and erreurs[4] and not erreurs[5] and erreurs[6]
    assert geo.appels == 0
    with client.Session() as db:
        assert db.scalars(select(Order)).all() == []


def test_window_and_service_validation(a, geo):
    mauvaise = ligne(1)
    mauvaise[7], mauvaise[8] = "14:00", "09:00"
    d = importer(a, [mauvaise, ligne(2)], chemin="import/apercu").json()
    assert d["lignes"][0]["erreurs"] and d["lignes"][1]["action"] == "creer"


def test_date_from_column_or_default_or_error(a, geo):
    m = {**MAPPING, "date_livraison": "Jour"}
    entetes = ("Référence", "Client", "Adresse", "CP", "Ville", "Poids", "Palettes", "Début", "Fin", "Frigo", "Jour")
    avec = a.post("/api/admin/commandes/import/apercu", files=fichier([ligne(1) + ["03/11/2026"], ligne(2) + [""]], entetes),
                  data={"mapping": json.dumps(m), "date_defaut": JOUR})
    assert [l["erreurs"] for l in avec.json()["lignes"]] == [[], []]
    sans = a.post("/api/admin/commandes/import/apercu", files=fichier([ligne(3) + [""]], entetes), data={"mapping": json.dumps(m)})
    assert sans.json()["lignes"][0]["erreurs"]  # ni date dans le fichier, ni date par défaut


def test_import_100_orders_95_percent_geocoded_and_the_rest_fixable(a, geo, client):
    lignes = [ligne(i, f"{i + 1} rue des Lilas") for i in range(95)]
    lignes += [ligne(95, "rue douteux"), ligne(96, "rue douteux 2"), ligne(97, "impasse introuvable"),
               ligne(98, "chemin introuvable 2"), ligne(99, "zz introuvable 3")]
    d = importer(a, lignes).json()
    assert d["crees"] == 100 and d["geocodage"]["ok"] == 95
    assert d["geocodage"]["douteux"] == 2 and d["geocodage"]["introuvable"] == 3
    assert geo.appels == 1 and geo.lignes_envoyees == 100  # un seul appel groupé pour tout le fichier
    a_corriger = a.get("/api/admin/commandes", params={"geo": "introuvable"}).json()
    assert len(a_corriger) == 3 and a_corriger[0]["lat"] is None
    r = a.patch(f"/api/admin/commandes/{a_corriger[0]['id']}", json={"lat": 47.21, "lng": -1.55})
    assert r.json()["geo_statut"] == "manuel" and r.json()["lat"] == 47.21
    assert len(a.get("/api/admin/commandes", params={"geo": "introuvable"}).json()) == 2


def test_geocode_cache_avoids_second_call(a, geo, client):
    importer(a, [ligne(1), ligne(2)])
    appels = geo.appels
    importer(a, [ligne(3), ligne(4)], defaut="2026-11-03")  # mêmes adresses, autre jour
    assert geo.appels == appels
    with client.Session() as db:
        assert db.scalar(select(GeocodeCache).where(GeocodeCache.adresse_norm == geocodage.normaliser("12 rue des Lilas 44000 Nantes"))) is not None


def test_service_down_import_succeeds_then_retry(a, geo):
    geo.panne = True
    d = importer(a, [ligne(1), ligne(2)]).json()
    assert d["crees"] == 2 and d["geocodage_indisponible"] is True and d["geocodage"]["a_geocoder"] == 2
    assert a.post("/api/admin/commandes/geocoder").status_code == 503
    geo.panne = False
    assert a.post("/api/admin/commandes/geocoder").json() == {"traitees": 2}
    assert {o["geo_statut"] for o in a.get("/api/admin/commandes").json()} == {"ok"}
    assert a.post("/api/admin/commandes/geocoder").json() == {"traitees": 0}


def test_reimport_updates_and_regeocodes_changed_address(a, geo):
    importer(a, [ligne(1)])
    d = importer(a, [ligne(1, "8 rue neuve")]).json()
    assert (d["crees"], d["mis_a_jour"]) == (0, 1)
    commandes = a.get("/api/admin/commandes").json()
    assert len(commandes) == 1 and "8 rue neuve" in commandes[0]["adresse"] and commandes[0]["geo_statut"] == "ok"


def test_import_excel_with_date_and_time_cells(a, geo):
    wb = Workbook()
    ws = wb.active
    ws.append(["Référence", "Adresse", "Date", "Palettes", "Frigo"])
    ws.append(["X1", "5 rue Crébillon 44000 Nantes", datetime(2026, 11, 4), 6, "oui"])
    buf = io.BytesIO()
    wb.save(buf)
    m = {"reference": "Référence", "adresse": "Adresse", "date_livraison": "Date", "palettes": "Palettes", "frigo": "Frigo"}
    r = a.post("/api/admin/commandes/import", files={"fichier": ("c.xlsx", io.BytesIO(buf.getvalue()), "application/octet-stream")},
               data={"mapping": json.dumps(m)})
    assert r.status_code == 200 and r.json()["crees"] == 1
    assert r.json()["premiere_date"] == "2026-11-04"  # l'écran se positionne sur ce jour après l'import
    o = a.get("/api/admin/commandes").json()[0]
    assert o["date_livraison"] == "2026-11-04" and o["palettes"] == 6 and o["frigo"] is True


# --- CRUD ---


def commande(c, **extra):
    return c.post("/api/admin/commandes", json={"reference": "R1", "adresse": "5 rue de Verdun Nantes", "date_livraison": JOUR, **extra})


def test_create_update_delete_order(a, geo):
    r = commande(a, poids_kg=500, fenetre_debut="08:00", fenetre_fin="10:00")
    assert r.status_code == 201 and r.json()["geo_statut"] == "ok"
    oid = r.json()["id"]
    assert commande(a).status_code == 409
    assert a.patch(f"/api/admin/commandes/{oid}", json={"frigo": True, "palettes": 4}).json()["palettes"] == 4
    assert a.patch(f"/api/admin/commandes/{oid}", json={"fenetre_debut": "11:00"}).status_code == 422  # après la fin
    assert a.patch(f"/api/admin/commandes/{oid}", json={"lat": 47.0}).status_code == 422  # latitude sans longitude
    avant = geo.appels
    a.patch(f"/api/admin/commandes/{oid}", json={"adresse": "9 rue introuvable"})
    assert a.get("/api/admin/commandes").json()[0]["geo_statut"] == "introuvable" and geo.appels == avant + 1
    assert a.delete(f"/api/admin/commandes/{oid}").status_code == 204
    assert a.get("/api/admin/commandes").json() == []


@pytest.mark.parametrize("extra", [{"poids_kg": -1}, {"palettes": 500}, {"fenetre_debut": "25:00"}, {"adresse": "x"},
                                   {"fenetre_debut": "10:00", "fenetre_fin": "09:00"}, {"reference": ""}])
def test_create_order_validation(a, geo, extra):
    assert commande(a, **extra).status_code == 422


def test_list_filters(a, geo):
    importer(a, [ligne(1), ligne(2, "x introuvable")])
    importer(a, [ligne(3)], defaut="2026-11-05")
    get = lambda **p: a.get("/api/admin/commandes", params=p).json()  # noqa: E731
    assert len(get()) == 3 and len(get(date="2026-11-05")) == 1 and len(get(geo="introuvable")) == 1
    assert [o["reference"] for o in get(q="CMD-0001")] == ["CMD-0001"]
    assert get(q="%") == []  # le joker n'est pas interprété


# --- Dépôts ---


def depot(c, **extra):
    return c.post("/api/admin/depots", json={"nom": "Dépôt Nantes", "adresse": "1 rue du Port 44000 Nantes", **extra})


def test_first_depot_is_default_and_only_one_default(a, geo):
    d1 = depot(a).json()
    d2 = depot(a, nom="Dépôt Rennes").json()
    assert d1["par_defaut"] is True and d2["par_defaut"] is False and d1["lat"] is not None
    a.patch(f"/api/admin/depots/{d2['id']}", json={"par_defaut": True})
    assert {d["nom"]: d["par_defaut"] for d in a.get("/api/admin/depots").json()} == {"Dépôt Nantes": False, "Dépôt Rennes": True}
    assert a.patch(f"/api/admin/depots/{d2['id']}", json={"par_defaut": False}).status_code == 409


def test_cannot_delete_last_depot_and_default_is_promoted(a, geo):
    d1, d2 = depot(a).json(), depot(a, nom="Dépôt Rennes").json()
    assert a.delete(f"/api/admin/depots/{d1['id']}").status_code == 204
    assert a.get("/api/admin/depots").json()[0]["par_defaut"] is True
    assert a.delete(f"/api/admin/depots/{d2['id']}").status_code == 409


def test_depot_validation_manual_position_and_address_change(a, geo):
    assert depot(a, ouverture="18:00", fermeture="08:00").status_code == 422
    assert depot(a, ouverture="8h").status_code == 422
    d = depot(a, lat=47.3, lng=-1.6).json()
    assert (d["lat"], d["lng"]) == (47.3, -1.6) and geo.appels == 0
    r = a.patch(f"/api/admin/depots/{d['id']}", json={"adresse": "2 quai de la Fosse Nantes"})
    assert r.json()["lat"] != 47.3 and geo.appels == 1


def test_depot_created_when_geocoder_is_down(a, geo):
    geo.panne = True
    d = depot(a)
    assert d.status_code == 201 and d.json()["lat"] is None


# --- Authentification et isolation ---


def test_new_routes_require_login(client):
    routes = [("get", "/api/admin/commandes"), ("post", "/api/admin/commandes"), ("patch", "/api/admin/commandes/1"),
              ("delete", "/api/admin/commandes/1"), ("post", "/api/admin/commandes/geocoder"),
              ("post", "/api/admin/commandes/import"), ("post", "/api/admin/commandes/import/apercu"),
              ("post", "/api/admin/commandes/import/colonnes"), ("get", "/api/admin/depots"), ("post", "/api/admin/depots"),
              ("patch", "/api/admin/depots/1"), ("delete", "/api/admin/depots/1")]
    for method, url in routes:
        assert getattr(client, method)(url).status_code == 401, (method, url)


def test_orders_and_depots_are_isolated(a, b, geo, client):
    oid = commande(a).json()["id"]
    did = depot(a).json()["id"]
    assert b.get("/api/admin/commandes").json() == [] and b.get("/api/admin/depots").json() == []
    assert b.patch(f"/api/admin/commandes/{oid}", json={"palettes": 9}).status_code == 404
    assert b.delete(f"/api/admin/commandes/{oid}").status_code == 404
    assert b.patch(f"/api/admin/depots/{did}", json={"nom": "Pirate"}).status_code == 404
    assert b.delete(f"/api/admin/depots/{did}").status_code == 404
    assert commande(b).status_code == 201  # même référence, autre société
    geo.panne = True
    a.post("/api/admin/commandes", json={"reference": "R2", "adresse": "7 rue du Test", "date_livraison": JOUR})
    geo.panne = False
    assert b.post("/api/admin/commandes/geocoder").json() == {"traitees": 0}  # ne touche pas aux commandes d'A
    assert a.get("/api/admin/commandes", params={"geo": "a_geocoder"}).json()
    with client.Session() as db:
        assert db.scalar(select(ColumnMapping)) is None
