"""Plan du chauffeur sur téléphone : publication, lien personnel, contrôle du jour, statuts d'arrêts, preuves."""
import io
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import livraisons, notifications
from app.models import Check, Order, PlanLien
from test_plans import calcul, camion, depot, executer  # noqa: F401
from test_plans_edition import deplacer, get, route_de

JOUR = date(2026, 11, 2)  # lundi
MAINTENANT = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)  # 10 h à Paris
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff" + b"0" * 64
SIGNATURE = "data:image/png;base64,iVBORw0KGgo="


@pytest.fixture(autouse=True)
def horloge(monkeypatch):
    monkeypatch.setattr(livraisons, "maintenant", lambda: MAINTENANT)


@pytest.fixture
def decor(a, client, calcul, upload_dir):  # noqa: F811
    """Un camion, un dépôt, quatre commandes du lundi 2 novembre, plan calculé."""
    vid = camion(a, "AA-100-AA")
    depot(a)
    with client.Session() as db:
        for i in range(4):
            db.add(Order(company_id=1, reference=f"C{i}", client=f"Client {i}", adresse=f"{i} rue Test", lat=47.2 + i * 0.01, lng=-1.55, geo_statut="ok",
                         poids_kg=100, palettes=1, volume_m3=1, date_livraison=JOUR, contact_nom="Mme Durand", contact_telephone="0601020304",
                         consignes="Quai 3, sonner à l'interphone"))
        db.commit()
    pid = a.post("/api/admin/plans", json={"jour": JOUR.isoformat(), "temps_max_s": 2}).json()["id"]
    executer(client, pid)
    return {"vid": vid, "plan": pid}


def publier(c, pid):
    return c.post(f"/api/admin/plans/{pid}/publier")


def token_de(c, pid, plaque="AA-100-AA"):
    return next(l["token"] for l in publier(c, pid).json()["liens"] if l["plaque"] == plaque)


def controle_fait(client, vehicle_id, quand=None, vehicule_bloque=False):
    with client.Session() as db:
        from app.models import Vehicle
        db.add(Check(company_id=1, vehicle_id=vehicle_id, conducteur="Karim", reponses=[], created_at=quand or datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc),
                     recu_le=quand or datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)))
        db.get(Vehicle, vehicle_id).bloque = vehicule_bloque
        db.commit()


def lire(c, token):
    return c.get(f"/api/tournee/{token}")


def evenement(c, token, order_id, statut, **extra):
    return c.post(f"/api/tournee/{token}/evenements", json={"order_id": order_id, "statut": statut, **extra})


@pytest.fixture
def ouverte(a, client, decor):
    """Tournée publiée et déverrouillée (contrôle du jour fait) : jeton, premier arrêt."""
    tok = token_de(a, decor["plan"])
    controle_fait(client, decor["vid"])
    arrets = lire(a, tok).json()["arrets"]
    assert len(arrets) == 4
    return {"token": tok, "arrets": arrets, **decor}


# ---------------------------------------------------------------- Publication


def test_publication_requires_login_and_a_finished_plan(a, client, decor):
    assert client.__class__(client.app).post(f"/api/admin/plans/{decor['plan']}/publier").status_code == 401
    en_attente = a.post("/api/admin/plans", json={"jour": "2026-11-03"}).json()["id"]
    assert publier(a, en_attente).status_code == 409


def test_plan_list_tells_which_plan_is_published(a, decor):
    avant = a.get("/api/admin/plans").json()
    assert all(p["publie_le"] is None for p in avant)
    publier(a, decor["plan"])
    assert {p["id"]: p["publie_le"] is not None for p in a.get("/api/admin/plans").json()}[decor["plan"]] is True


def test_publish_creates_a_personal_link_per_route(a, decor):
    r = publier(a, decor["plan"])
    assert r.status_code == 200 and r.json()["publie_le"]
    (lien,) = r.json()["liens"]
    assert lien["plaque"] == "AA-100-AA" and lien["url"].endswith(f"/t/{lien['token']}") and len(lien["token"]) >= 30
    assert publier(a, decor["plan"]).json()["liens"][0]["token"] == lien["token"]  # republier ne change pas les liens
    assert a.get(f"/api/admin/plans/{decor['plan']}/liens").json()["liens"][0]["token"] == lien["token"]
    assert a.get(f"/api/admin/plans/{decor['plan']}").json()["publie_le"]


def test_publishing_a_plan_with_no_stops_is_refused(a, client, calcul):
    camion(a, "AA-100-AA")
    depot(a)
    with client.Session() as db:
        db.add(Order(company_id=1, reference="SANS", adresse="x", date_livraison=JOUR, geo_statut="introuvable"))
        db.commit()
    pid = a.post("/api/admin/plans", json={"jour": JOUR.isoformat(), "temps_max_s": 1}).json()["id"]
    executer(client, pid)
    assert publier(a, pid).status_code == 409


def test_a_new_published_plan_retires_the_old_links(a, client, decor):
    ancien = token_de(a, decor["plan"])
    nouveau = a.post(f"/api/admin/plans/{decor['plan']}/versions", json={"nom": "Révisé"}).json()["id"]
    publier(a, nouveau)
    r = lire(a, ancien)
    assert r.status_code == 410 and "plus d'actualité" in r.json()["detail"]
    assert a.get(f"/api/admin/plans/{decor['plan']}").json()["publie_le"] is None


def test_publication_emails_the_drivers_who_have_an_address(a, decor, monkeypatch):
    d = a.post("/api/admin/conducteurs", json={"nom": "Karim Benali", "vehicule_habituel_id": decor["vid"], "email": " Karim@Exemple.fr "}).json()
    assert d["email"] == "karim@exemple.fr"
    pid2 = a.post(f"/api/admin/plans/{decor['plan']}/versions", json={"nom": "Avec conducteur"}).json()["id"]
    a.post(f"/api/admin/plans/{pid2}/affecter", json={"vehicle_id": decor["vid"], "conducteur_id": d["id"]})
    envoyes = []
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("BREVO_SENDER", "alertes@flotta.test")
    monkeypatch.setattr(notifications, "send_email", lambda to, subject, html: envoyes.append((to, subject, html)))
    r = publier(a, pid2).json()
    assert r["liens"][0]["conducteur"] == "Karim Benali" and len(envoyes) == 1
    assert envoyes[0][0] == ["karim@exemple.fr"] and r["liens"][0]["url"] in envoyes[0][2] and "AA-100-AA" in envoyes[0][1]


def test_no_email_without_brevo_or_without_address(a, decor, monkeypatch):
    envoyes = []
    monkeypatch.setattr(notifications, "send_email", lambda *x: envoyes.append(x))
    publier(a, decor["plan"])
    assert envoyes == []


def test_driver_email_is_validated(a):
    assert a.post("/api/admin/conducteurs", json={"nom": "Sophie Lambert", "email": "pas-un-email"}).status_code == 422
    d = a.post("/api/admin/conducteurs", json={"nom": "Sophie Lambert", "email": ""}).json()
    assert d["email"] is None
    assert a.patch(f"/api/admin/conducteurs/{d['id']}", json={"email": "s@l.fr"}).json()["email"] == "s@l.fr"


# ---------------------------------------------------------------- Lecture par le chauffeur et contrôle du jour


def test_unknown_link(client):
    assert lire(client, "nimportequoi").status_code == 404


def test_route_is_locked_until_the_daily_check_is_done(a, client, decor):
    tok = token_de(a, decor["plan"])
    d = lire(a, tok).json()
    assert d["verrouillee"] is True and "contrôle" in d["raison"] and d["arrets"] == [] and d["controle_token"]
    assert evenement(a, tok, 1, "arrive").status_code == 409  # pas d'envoi de statut tant que c'est verrouillé
    controle_fait(client, decor["vid"])
    d = lire(a, tok).json()
    assert d["verrouillee"] is False and len(d["arrets"]) == 4 and d["raison"] is None


def test_a_check_from_another_day_does_not_unlock(a, client, decor):
    tok = token_de(a, decor["plan"])
    controle_fait(client, decor["vid"], quand=datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc))
    assert lire(a, tok).json()["verrouillee"] is True


def test_blocked_vehicle_keeps_the_route_locked_even_after_a_check(a, client, decor):
    tok = token_de(a, decor["plan"])
    controle_fait(client, decor["vid"], vehicule_bloque=True)
    d = lire(a, tok).json()
    assert d["verrouillee"] is True and "bloqué" in d["raison"] and d["arrets"] == []
    assert evenement(a, tok, 1, "livre").status_code == 409


def test_driver_sees_ordered_stops_with_contact_and_instructions(ouverte, a):
    d = lire(a, ouverte["token"]).json()
    assert d["plaque"] == "AA-100-AA" and d["jour"] == "2026-11-02" and d["jour_du_plan"] is True
    arrets = d["arrets"]
    assert [x["ordre"] for x in arrets] == [1, 2, 3, 4]
    assert arrets[0]["contact_nom"] == "Mme Durand" and arrets[0]["contact_telephone"] == "0601020304" and "Quai 3" in arrets[0]["consignes"]
    heures = [x["arrivee_min"] for x in arrets]
    assert heures == sorted(heures) and all(x["statut"] is None for x in arrets) and "absent" in d["motifs"]


def test_other_day_is_flagged(a, client, decor, monkeypatch):
    tok = token_de(a, decor["plan"])
    controle_fait(client, decor["vid"])
    monkeypatch.setattr(livraisons, "maintenant", lambda: MAINTENANT + timedelta(days=2))
    assert lire(a, tok).json()["jour_du_plan"] is False


def test_qr_code_of_the_truck_leads_to_todays_route(a, client, decor):
    with client.Session() as db:
        from app.models import Vehicle
        vtoken = db.get(Vehicle, decor["vid"]).token
    assert a.get(f"/api/controle/{vtoken}").json()["tournee_token"] is None
    tok = token_de(a, decor["plan"])
    assert a.get(f"/api/controle/{vtoken}").json()["tournee_token"] == tok


# ---------------------------------------------------------------- Statuts d'arrêts


def test_arrive_then_delivered_with_recipient_and_signature(ouverte, a, client):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    r1 = evenement(a, token, oid, "arrive", lat=47.2, lng=-1.55)
    assert r1.status_code == 201 and r1.json()["statut"] == "arrive"
    assert lire(a, token).json()["arrets"][0]["statut"] == "arrive"
    r2 = evenement(a, token, oid, "livre", nom_destinataire="Mme Durand", signature=SIGNATURE, lat=47.2, lng=-1.55)
    assert r2.status_code == 201
    assert lire(a, token).json()["arrets"][0]["statut"] == "livre"
    with client.Session() as db:
        assert db.get(Order, oid).statut == "livre"
    suivi = next(s for r in get(a, ouverte["plan"])["routes"] for s in r["arrets"] if s["order_id"] == oid)["livraison"]
    assert suivi["statut"] == "livre" and suivi["arrive_le"] and suivi["termine_le"] and suivi["nom_destinataire"] == "Mme Durand" and suivi["a_signature"] is True


def test_delivery_without_arrival_event_is_accepted(ouverte, a):
    assert evenement(a, ouverte["token"], ouverte["arrets"][1]["order_id"], "livre").status_code == 201


def test_undeliverable_needs_a_reason_and_marks_the_order(ouverte, a, client):
    oid = ouverte["arrets"][2]["order_id"]
    assert evenement(a, ouverte["token"], oid, "impossible").status_code == 422
    assert evenement(a, ouverte["token"], oid, "impossible", motif="inconnu").status_code == 422
    r = evenement(a, ouverte["token"], oid, "impossible", motif="absent", commentaire="Personne sur place")
    assert r.status_code == 201
    d = lire(a, ouverte["token"]).json()["arrets"][2]
    assert d["statut"] == "impossible" and d["motif"] == "absent"
    with client.Session() as db:
        assert db.get(Order, oid).statut == "echec"


def test_closed_stop_cannot_change_but_same_status_is_idempotent(ouverte, a):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    evenement(a, token, oid, "livre")
    assert evenement(a, token, oid, "livre").status_code == 200  # même statut : rien de nouveau
    assert evenement(a, token, oid, "impossible", motif="absent").status_code == 409
    assert evenement(a, token, oid, "arrive").status_code == 409


def test_second_arrival_event_returns_the_first(ouverte, a):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    premier = evenement(a, token, oid, "arrive").json()
    second = evenement(a, token, oid, "arrive")
    assert second.status_code == 200 and second.json()["id"] == premier["id"]


def test_replayed_submission_creates_no_duplicate(ouverte, a, client):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    r1 = evenement(a, token, oid, "arrive", client_id="evt-abcdef-0001")
    r2 = evenement(a, token, oid, "arrive", client_id="evt-abcdef-0001")
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.json()["id"] == r2.json()["id"]
    from app.models import LivraisonEvenement
    with client.Session() as db:
        assert len(db.scalars(select(LivraisonEvenement)).all()) == 1


def test_event_validation(ouverte, a):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    for extra in ({"statut": "perdu"}, {"lat": 47.0}, {"client_id": "court"}, {"signature": "data:text/html;base64,AAAA"}, {"lat": 95, "lng": 0}):
        corps = {"order_id": oid, "statut": "arrive", **extra}
        assert a.post(f"/api/tournee/{token}/evenements", json=corps).status_code == 422, extra
    assert evenement(a, token, 999999, "arrive").status_code == 404


def test_event_time_uses_the_phone_clock_when_plausible_and_ignores_absurd_ones(ouverte, a, client):
    from app.models import LivraisonEvenement
    token = ouverte["token"]
    evenement(a, token, ouverte["arrets"][0]["order_id"], "livre", fait_le=(MAINTENANT - timedelta(minutes=30)).isoformat())
    evenement(a, token, ouverte["arrets"][1]["order_id"], "livre", fait_le=(MAINTENANT + timedelta(days=3)).isoformat())
    evenement(a, token, ouverte["arrets"][2]["order_id"], "livre", fait_le=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat())
    with client.Session() as db:
        horaires = [e.fait_le.replace(tzinfo=timezone.utc) for e in db.scalars(select(LivraisonEvenement).order_by(LivraisonEvenement.id))]
    assert horaires[0] == MAINTENANT - timedelta(minutes=30) and horaires[1] == MAINTENANT and horaires[2] == MAINTENANT


def test_a_late_replay_the_next_day_is_still_accepted(ouverte, a, monkeypatch):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    monkeypatch.setattr(livraisons, "maintenant", lambda: MAINTENANT + timedelta(days=1))
    r = evenement(a, token, oid, "livre", client_id="evt-hors-ligne-01", fait_le=(MAINTENANT + timedelta(hours=3)).isoformat())
    assert r.status_code == 201


def test_a_stop_of_another_route_is_refused(a, client, decor):
    with client.Session() as db:
        db.add(Order(company_id=1, reference="AUTRE", adresse="z", lat=48.0, lng=-1.0, geo_statut="ok", date_livraison=JOUR))
        db.commit()
    # Une commande qui ne fait pas partie de la tournée est inconnue du lien.
    tok = token_de(a, decor["plan"])
    controle_fait(client, decor["vid"])
    with client.Session() as db:
        hors_plan = db.scalar(select(Order.id).where(Order.reference == "AUTRE"))
    assert evenement(a, tok, hors_plan, "livre").status_code == 404


# ---------------------------------------------------------------- Preuves : photos


def photo(c, token, event_id, data=JPG, nom="p.jpg"):
    return c.post(f"/api/tournee/{token}/evenements/{event_id}/photos", files={"photo": (nom, io.BytesIO(data), "image/jpeg")})


def test_proof_photos_are_stored_and_visible_to_the_operator(ouverte, a, b):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    eid = evenement(a, token, oid, "livre").json()["id"]
    pid = photo(a, token, eid).json()["id"]
    assert a.get(f"/api/admin/plans/livraisons/photos/{pid}").content == JPG
    assert b.get(f"/api/admin/plans/livraisons/photos/{pid}").status_code == 404
    suivi = next(s for r in get(a, ouverte["plan"])["routes"] for s in r["arrets"] if s["order_id"] == oid)["livraison"]
    assert suivi["photos"] == [pid]


def test_photo_validation_limits_and_window(ouverte, a, monkeypatch):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    eid = evenement(a, token, oid, "livre").json()["id"]
    assert photo(a, token, eid, b"<script>x</script>", "x.jpg").status_code == 415
    assert photo(a, token, eid, JPG + b"0" * (5 * 1024 * 1024)).status_code == 413
    for _ in range(3):
        assert photo(a, token, eid, PNG, "p.png").status_code == 201
    assert photo(a, token, eid).status_code == 409
    eid2 = evenement(a, token, ouverte["arrets"][1]["order_id"], "livre").json()["id"]
    monkeypatch.setattr(livraisons, "maintenant", lambda: MAINTENANT + timedelta(hours=2))
    assert photo(a, token, eid2).status_code == 403
    assert photo(a, token, 999999).status_code == 404


def test_signature_is_served_to_the_operator_only(ouverte, a, b):
    token, oid = ouverte["token"], ouverte["arrets"][0]["order_id"]
    eid = evenement(a, token, oid, "livre", signature="data:image/png;base64,iVBORw0KGgo=").json()["id"]
    assert a.get(f"/api/admin/plans/livraisons/{eid}/signature").headers["content-type"] == "image/png"
    assert b.get(f"/api/admin/plans/livraisons/{eid}/signature").status_code == 404
    sans = evenement(a, token, ouverte["arrets"][1]["order_id"], "livre").json()["id"]
    assert a.get(f"/api/admin/plans/livraisons/{sans}/signature").status_code == 404


# ---------------------------------------------------------------- Suivi par l'exploitant


def test_operator_sees_progress_and_delays_in_the_plan(ouverte, a):
    token = ouverte["token"]
    evenement(a, token, ouverte["arrets"][0]["order_id"], "livre")
    evenement(a, token, ouverte["arrets"][1]["order_id"], "impossible", motif="ferme")
    evenement(a, token, ouverte["arrets"][2]["order_id"], "arrive")
    plan = get(a, ouverte["plan"])
    av = plan["avancement"]
    assert (av["total"], av["livrees"], av["impossibles"], av["sur_place"]) == (4, 1, 1, 1)
    arrets = route_de(plan, "AA-100-AA")["arrets"]
    assert arrets[3]["retard_min"] is None or arrets[3]["retard_min"] > 15  # 10 h : le dernier arrêt prévu plus tôt est en retard
    assert arrets[0]["retard_min"] is None and arrets[2]["retard_min"] is None  # clôturé ou sur place : pas en retard
    assert av["en_retard"] == sum(1 for s in arrets if s["retard_min"])


def test_a_stop_planned_long_ago_and_not_started_is_late(ouverte, a, monkeypatch):
    monkeypatch.setattr(livraisons, "maintenant", lambda: datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc))  # 16 h à Paris
    plan = get(a, ouverte["plan"])
    arrets = route_de(plan, "AA-100-AA")["arrets"]
    assert all(s["retard_min"] and s["retard_min"] > 15 for s in arrets) and plan["avancement"]["en_retard"] == 4


def test_no_delay_is_reported_on_another_day(ouverte, a, monkeypatch):
    monkeypatch.setattr(livraisons, "maintenant", lambda: MAINTENANT + timedelta(days=3))
    assert get(a, ouverte["plan"])["avancement"]["en_retard"] == 0


def test_status_survives_a_plan_edit_after_publication(ouverte, a, client):
    token, premier = ouverte["token"], ouverte["arrets"][0]["order_id"]
    evenement(a, token, premier, "livre")
    autre = ouverte["arrets"][3]["order_id"]
    deplacer(a, ouverte["plan"], autre, route_de(get(a, ouverte["plan"]), "AA-100-AA")["vehicle_id"], 0)
    statuts = {x["order_id"]: x["statut"] for x in lire(a, token).json()["arrets"]}
    assert statuts[premier] == "livre"
    with client.Session() as db:
        assert db.get(Order, premier).statut == "livre"  # l'édition du plan ne rend pas une commande livrée « planifiée »


def test_tournee_routes_are_isolated_between_companies(ouverte, a, b):
    assert b.post(f"/api/admin/plans/{ouverte['plan']}/publier").status_code == 404
    assert b.get(f"/api/admin/plans/{ouverte['plan']}/liens").status_code == 404
    assert b.get(f"/api/admin/plans/{ouverte['plan']}").status_code == 404


def test_contact_and_instructions_can_be_edited_on_the_order(a, ouverte):
    oid = ouverte["arrets"][0]["order_id"]
    r = a.patch(f"/api/admin/commandes/{oid}", json={"contact_nom": "M. Martin", "contact_telephone": "0611223344", "consignes": "Code 4821"})
    assert r.json()["contact_nom"] == "M. Martin" and r.json()["consignes"] == "Code 4821"
    d = lire(a, ouverte["token"]).json()["arrets"][0]
    assert d["contact_telephone"] == "0611223344" and d["consignes"] == "Code 4821"


def test_import_maps_contact_phone_and_instructions(a, client):
    import json
    texte = "Réf;Adresse;Contact;Tél;Consignes\nX1;3 rue du Port Nantes;M. Roux;0699887766;Quai arrière\n"
    r = a.post("/api/admin/commandes/import", files={"fichier": ("c.csv", io.BytesIO(texte.encode()), "text/csv")},
               data={"mapping": json.dumps({"reference": "Réf", "adresse": "Adresse", "contact_nom": "Contact", "contact_telephone": "Tél", "consignes": "Consignes"}),
                     "date_defaut": "2026-11-02"})
    assert r.status_code == 200 and r.json()["crees"] == 1
    o = a.get("/api/admin/commandes").json()[0]
    assert (o["contact_nom"], o["contact_telephone"], o["consignes"]) == ("M. Roux", "0699887766", "Quai arrière")
