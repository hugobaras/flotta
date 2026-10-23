"""Crée une commande par l'API puis écoute un webhook.
FLOTTA_URL, FLOTTA_CLE : adresse et clé API. Pour le test en local : WEBHOOKS_AUTORISER_LOCAL=1 côté API,
et un webhook enregistré sur http://host.docker.internal:9000/ avec le secret passé dans WEBHOOK_SECRET."""
import hashlib, hmac, json, os, time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

URL, CLE = os.environ["FLOTTA_URL"], os.environ["FLOTTA_CLE"]
SECRET = os.getenv("WEBHOOK_SECRET", "")


def verifier(entete: str, corps: bytes) -> bool:
    p = dict(x.split("=", 1) for x in entete.split(","))
    attendu = hmac.new(SECRET.encode(), p["t"].encode() + b"." + corps, hashlib.sha256).hexdigest()
    return abs(time.time() - int(p["t"])) <= 300 and hmac.compare_digest(attendu, p["v1"])


class Recepteur(BaseHTTPRequestHandler):
    def do_POST(self):
        corps = self.rfile.read(int(self.headers["Content-Length"]))
        ok = verifier(self.headers.get("X-Flotta-Signature", ""), corps)
        print("signature", "valide" if ok else "INVALIDE", json.loads(corps)["evenement"])
        self.send_response(200 if ok else 401)
        self.end_headers()


if __name__ == "__main__":
    r = httpx.post(f"{URL}/api/v1/commandes", headers={"Authorization": f"Bearer {CLE}"},
                   json={"reference": f"EX-{int(time.time())}", "client": "Exemple", "adresse": "1 rue de la Paix, Nantes", "date_livraison": "2026-11-02"})
    print(r.status_code, r.json())
    HTTPServer(("0.0.0.0", 9000), Recepteur).serve_forever()
