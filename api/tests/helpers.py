import io
from datetime import datetime, timezone

from app.checklists import DEFAULT_ITEMS
from app.models import User

def login(client, email, password="motdepasse-ok"):
    return client.post("/api/auth/login", json={"email": email, "password": password})

KEYS = {"pneus": 0, "freins": 1, "feux": 2, "niveaux": 3, "retros": 4, "docs": 5}

def reponses(client, token, *ko):
    """Réponses complètes pour la checklist servie au chauffeur ; `ko` = clés des points en défaut."""
    items = client.get(f"/api/controle/{token}").json()["checklist"]
    ko_libelles = {DEFAULT_ITEMS[KEYS[k]][0] for k in ko}
    return [{"id": i["id"], "ok": i["libelle"] not in ko_libelles} for i in items]

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

SIGNATURE = "data:image/png;base64,iVBORw0KGgo="

def send(c, token, *ko, **extra):
    r = c.post(f"/api/controle/{token}", json={"conducteur": "Paul Durand", "reponses": reponses(c, token, *ko), **extra})
    assert r.status_code == 201, r.text
    return r.json()

def upload(c, check_id, data=PNG, token="tok-a", name="p.png"):
    return c.post(f"/api/controle/{token}/{check_id}/photos", files={"photo": (name, io.BytesIO(data), "image/png")})

def paris(h, m=0):
    """Instant UTC correspondant à h:m heure de Paris le 15 janvier 2026 (UTC+1)."""
    return datetime(2026, 1, 15, h - 1, m, tzinfo=timezone.utc)

def make_admin(client, email):
    with client.Session() as db:
        db.query(User).filter_by(email=email).update({"role": "admin"})
        db.commit()
