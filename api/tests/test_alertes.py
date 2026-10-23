import io
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from reportlab import rl_config

from app import notifications, photos, worker
from app import main as main_module
from app.models import Alert, Check, Company
from helpers import PNG, make_admin, paris, reponses, send, upload

class Mail(list):
    state: dict


@pytest.fixture
def mail(monkeypatch):
    """Brevo configuré, envoi simulé ; `mail.fail` fait échouer les envois."""
    monkeypatch.setenv("BREVO_API_KEY", "cle-test")
    monkeypatch.setenv("BREVO_SENDER", "alertes@flotta.test")
    sent, state = Mail(), {"fail": False}

    def fake(to, subject, html):
        if state["fail"]:
            raise httpx.ConnectError("réseau coupé")
        sent.append((to, subject, html))

    monkeypatch.setattr(notifications, "send_email", fake)
    monkeypatch.setattr(main_module, "enqueue_alert", lambda alert_id: None)  # pas de Redis dans les tests
    sent.state = state
    return sent


def set_recipients(client, emails):
    with client.Session() as db:
        db.get(Company, 1).alert_emails = emails
        db.commit()


def alerts(client):
    with client.Session() as db:
        return [(a.id, a.statut, a.tentatives, a.erreur) for a in db.query(Alert).order_by(Alert.id)]


# --- Création de l'alerte à l'envoi du contrôle ---


def test_critical_defect_creates_pending_alert(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    assert [(s, t) for _, s, t, _ in alerts(client)] == [("en_attente", 0)]


def test_no_alert_without_critical_defect(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "retros")
    send(a, "tok-a2")
    assert alerts(client) == []


def test_alert_without_recipients_is_recorded_not_queued(a, client, mail, monkeypatch):
    queued = []
    monkeypatch.setattr(main_module, "enqueue_alert", queued.append)
    send(a, "tok-a", "freins")
    assert [s for _, s, _, _ in alerts(client)] == ["sans_destinataire"] and queued == []


def test_alert_is_queued_after_response(a, client, mail, monkeypatch):
    set_recipients(client, ["chef@a.fr"])
    queued = []
    monkeypatch.setattr(main_module, "enqueue_alert", queued.append)
    send(a, "tok-a", "freins")
    assert queued == [alerts(client)[0][0]]


def test_redis_down_never_blocks_driver(a, client, monkeypatch):
    set_recipients(client, ["chef@a.fr"])

    def boom(*args, **kwargs):
        raise ConnectionError("redis indisponible")

    monkeypatch.setattr(main_module.send_critical_alert, "apply_async", boom)
    r = a.post("/api/controle/tok-a", json={"conducteur": "P", "reponses": reponses(a, "tok-a", "freins")})
    assert r.status_code == 201 and r.json()["bloque"] is True
    assert [s for _, s, _, _ in alerts(client)] == ["en_attente"]  # relancée plus tard par le worker


# --- Envoi, réessais, idempotence ---


def process(client, alert_id, last=False):
    with client.Session() as db:
        return notifications.process_alert(db, alert_id, last)


def test_alert_email_sent_with_defect_details(a, client, mail):
    set_recipients(client, ["chef@a.fr", "garage@a.fr"])
    send(a, "tok-a", "freins")
    assert process(client, 1) is True
    (to, subject, html), = mail
    assert to == ["chef@a.fr", "garage@a.fr"] and "AA-111-AA" in subject
    assert "Freins" in html and "Paul Durand" in html and "Niveaux" not in html
    assert alerts(client)[0][1] == "envoye"


def test_alert_html_escapes_user_input(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    a.post("/api/controle/tok-a", json={"conducteur": "<script>x</script>", "reponses": reponses(a, "tok-a", "freins")})
    process(client, 1)
    assert "<script>" not in mail[0][2] and "&lt;script&gt;" in mail[0][2]


def test_alert_not_sent_twice(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    process(client, 1)
    process(client, 1)  # tâche rejouée par Celery
    assert len(mail) == 1


def test_failure_retries_then_gives_up(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    mail.state["fail"] = True
    assert process(client, 1) is False  # à réessayer
    assert alerts(client)[0][1:3] == ("en_attente", 1) and "réseau coupé" in alerts(client)[0][3]
    assert process(client, 1, last=True) is True  # dernière tentative : on abandonne
    assert alerts(client)[0][1:3] == ("echec", 2)
    mail.state["fail"] = False
    process(client, 1)
    assert mail == []  # une alerte en échec n'est plus renvoyée par erreur


def test_recovers_after_transient_failure(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    mail.state["fail"] = True
    process(client, 1)
    mail.state["fail"] = False
    assert process(client, 1) is True and len(mail) == 1 and alerts(client)[0][1] == "envoye"


def test_missing_brevo_key_is_recorded(a, client, mail, monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY")
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    assert process(client, 1) is True and mail == [] and alerts(client)[0][1] == "non_configure"


def test_recipients_removed_before_sending(a, client, mail):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    set_recipients(client, [])
    process(client, 1)
    assert mail == [] and alerts(client)[0][1] == "sans_destinataire"


def test_brevo_request_shape(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "secret-key")
    monkeypatch.setenv("BREVO_SENDER", "alertes@flotta.test")
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return httpx.Response(201, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    notifications.send_email(["x@y.fr"], "Sujet", "<p>Corps</p>")
    assert seen["url"] == "https://api.brevo.com/v3/smtp/email" and seen["headers"]["api-key"] == "secret-key"
    assert seen["json"]["to"] == [{"email": "x@y.fr"}] and seen["json"]["sender"] == {"email": "alertes@flotta.test"}


def test_brevo_error_status_raises(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("BREVO_SENDER", "s@x.fr")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(401, request=httpx.Request("POST", url)))
    with pytest.raises(httpx.HTTPStatusError):
        notifications.send_email(["x@y.fr"], "S", "<p>c</p>")


def test_unsent_alerts_requeued_once_old_enough(a, client, mail, monkeypatch):
    set_recipients(client, ["chef@a.fr"])
    send(a, "tok-a", "freins")
    queued = []
    monkeypatch.setattr(worker.send_critical_alert, "apply_async", lambda args, retry: queued.append(args[0]))
    now = datetime.now(timezone.utc)
    with client.Session() as db:
        assert worker.requeue_unsent_alerts(db, now) == 0  # trop récente
        assert worker.requeue_unsent_alerts(db, now + timedelta(minutes=6)) == 1
    assert queued == [1]


# --- Rappel quotidien ---


def add_check(client, vehicle_id, at):
    with client.Session() as db:
        db.add(Check(company_id=1, vehicle_id=vehicle_id, conducteur="P", reponses=[], created_at=at))
        db.commit()


def run_reminders(client, now):
    with client.Session() as db:
        return worker.send_reminders(db, now)


def test_reminder_sent_once_per_day(client, mail):
    set_recipients(client, ["chef@a.fr"])
    assert run_reminders(client, paris(7, 59)) == 0  # avant l'heure
    assert run_reminders(client, paris(8, 0)) == 1
    assert "2 camion(s)" in mail[0][1] and "AA-111-AA" in mail[0][2] and "ZZ-999-ZZ" in mail[0][2]
    assert run_reminders(client, paris(9, 0)) == 0  # déjà envoyé aujourd'hui
    assert run_reminders(client, paris(8, 0) + timedelta(days=1)) == 1  # le lendemain, à nouveau


def test_reminder_lists_only_unchecked_and_skips_when_all_done(client, mail):
    set_recipients(client, ["chef@a.fr"])
    add_check(client, 1, paris(6, 0))
    run_reminders(client, paris(9))
    assert "AA-111-AA" not in mail[0][2] and "ZZ-999-ZZ" in mail[0][2]
    mail.clear()
    with client.Session() as db:
        db.get(Company, 1).rappel_envoye_le = None
        db.commit()
    add_check(client, 2, paris(6, 30))
    assert run_reminders(client, paris(10)) == 0 and mail == []


def test_reminder_needs_recipients_and_brevo(client, mail, monkeypatch):
    assert run_reminders(client, paris(9)) == 0  # pas de destinataire
    set_recipients(client, ["chef@a.fr"])
    monkeypatch.delenv("BREVO_API_KEY")
    assert run_reminders(client, paris(9)) == 0 and mail == []


def test_reminder_failure_retried_next_pass(client, mail):
    set_recipients(client, ["chef@a.fr"])
    mail.state["fail"] = True
    assert run_reminders(client, paris(9)) == 0
    mail.state["fail"] = False
    assert run_reminders(client, paris(9, 5)) == 1  # pas marqué comme envoyé après l'échec


def test_reminder_isolated_per_company(client, mail):
    set_recipients(client, ["chef@a.fr"])  # B n'a aucun destinataire
    run_reminders(client, paris(9))
    assert len(mail) == 1 and all("BB-222-BB" not in m[2] for m in mail)


# --- Paramètres : destinataires ---


def test_alert_emails_setting_validated_and_normalized(a, client):
    make_admin(client, "a@a.fr")
    url = "/api/admin/parametres"
    assert a.patch(url, json={"alert_emails": ["pas-un-email"]}).status_code == 422
    assert a.patch(url, json={"alert_emails": [f"u{i}@a.fr" for i in range(11)]}).status_code == 422
    r = a.patch(url, json={"alert_emails": [" Chef@A.fr ", "chef@a.fr", "garage@a.fr"]})
    assert r.json()["alert_emails"] == ["chef@a.fr", "garage@a.fr"]


def test_alert_emails_not_visible_to_other_company(a, b, client):
    set_recipients(client, ["chef@a.fr"])
    assert b.get("/api/admin/parametres").json()["alert_emails"] == []


# --- Logo ---


def post_logo(c, data=PNG, name="logo.png"):
    return c.post("/api/admin/logo", files={"logo": (name, io.BytesIO(data), "image/png")})


def test_logo_admin_only(a, client, upload_dir):
    assert post_logo(a).status_code == 403
    make_admin(client, "a@a.fr")
    assert post_logo(a).status_code == 200
    assert a.get("/api/admin/logo").content == PNG
    assert a.get("/api/admin/parametres").json()["logo"] is True


def test_logo_rejects_bad_content_and_size(a, client, upload_dir):
    make_admin(client, "a@a.fr")
    assert post_logo(a, b"<svg onload=alert(1)>", "logo.png").status_code == 415
    assert post_logo(a, PNG + b"0" * (1024 * 1024)).status_code == 413
    assert list(upload_dir.rglob("*.*")) == []


def test_logo_replacement_removes_old_file(a, client, upload_dir):
    make_admin(client, "a@a.fr")
    post_logo(a)
    post_logo(a, PNG + b"1")
    assert len(list(upload_dir.rglob("*.png"))) == 1


def test_logo_isolation(a, b, client, upload_dir):
    make_admin(client, "a@a.fr")
    post_logo(a)
    assert b.get("/api/admin/logo").status_code == 404
    assert b.get("/api/admin/parametres").json()["logo"] is False


# --- PDF ---


@pytest.fixture
def plain_pdf(monkeypatch):
    monkeypatch.setattr(rl_config, "pageCompression", 0)  # texte lisible dans les octets du PDF


def test_pdf_contains_check_details(a, plain_pdf, upload_dir):
    cid = send(a, "tok-a", "freins", lat=47.2, lng=-1.5)["id"]
    r = a.get(f"/api/admin/controles/{cid}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and "controle-AA-111-AA-" in r.headers["content-disposition"]
    for text in (b"AA-111-AA", b"Paul Durand", b"FAUT", b"Position"):
        assert text in r.content


def test_pdf_with_logo_photos_and_broken_images(a, client, upload_dir):
    make_admin(client, "a@a.fr")
    post_logo(a)  # faux PNG : illisible pour le rendu, ne doit pas casser le PDF
    cid = send(a, "tok-a", "pneus", signature="data:image/png;base64,iVBORw0KGgo=")["id"]
    upload(a, cid)
    upload(a, cid)
    upload(a, cid)
    r = a.get(f"/api/admin/controles/{cid}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_pdf_with_real_images(a, client, upload_dir):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "red").save(buf, "PNG")
    make_admin(client, "a@a.fr")
    post_logo(a, buf.getvalue())
    cid = send(a, "tok-a", signature="data:image/png;base64,"
               + __import__("base64").b64encode(buf.getvalue()).decode())["id"]
    upload(a, cid, buf.getvalue())
    assert a.get(f"/api/admin/controles/{cid}/pdf").status_code == 200


def test_pdf_survives_markup_in_user_text(a):
    a.post("/api/controle/tok-a", json={
        "conducteur": "<b>Paul & fils</b>",
        "reponses": [{**r, "commentaire": "</para><x>"} for r in reponses(a, "tok-a")]})
    cid = a.get("/api/admin/controles").json()[0]["id"]
    assert a.get(f"/api/admin/controles/{cid}/pdf").status_code == 200


def test_pdf_isolation(a, b):
    cid = send(b, "tok-b")["id"]
    assert a.get(f"/api/admin/controles/{cid}/pdf").status_code == 404
