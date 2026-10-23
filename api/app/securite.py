"""En-têtes de sécurité, limite de débit par adresse, journaux structurés et Sentry (optionnel)."""
import json
import logging
import os
import time

from fastapi import Request
from fastapi.responses import JSONResponse

LIMITE_IP = int(os.getenv("LIMITE_IP_PAR_MINUTE", "600"))
# shortcut: compteur en mémoire par adresse (un seul worker) ; Caddy ajoute X-Forwarded-For (TRUSTED_PROXY=1).
_ip: dict[str, list[float]] = {}


def ip_client(request: Request) -> str:
    if os.getenv("TRUSTED_PROXY") == "1" and request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return request.client.host if request.client else "?"


def installer(app):
    @app.middleware("http")
    async def securite(request: Request, call_next):
        # Les routes chauffeur sont exemptées : une cabine derrière un NAT d'opérateur ne doit jamais être bloquée.
        if request.url.path.startswith("/api/") and request.url.path != "/api/health" and not request.url.path.startswith(("/api/controle", "/api/tournee")):
            now = time.monotonic()
            ip = ip_client(request)
            recents = [t for t in _ip.get(ip, []) if now - t < 60]
            if len(recents) >= LIMITE_IP:
                _ip[ip] = recents
                return JSONResponse({"detail": "Trop de requêtes"}, status_code=429, headers={"Retry-After": "60"})
            recents.append(now)
            _ip[ip] = recents
        r = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["X-Frame-Options"] = "DENY"
        r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        if os.getenv("COOKIE_SECURE") == "1":
            r.headers["Strict-Transport-Security"] = "max-age=31536000"
        return r


class JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {"t": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "niveau": record.levelname, "logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            d["exception"] = self.formatException(record.exc_info)
        return json.dumps(d, ensure_ascii=False)


def configurer_journaux():
    if os.getenv("LOG_JSON") == "1":
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        logging.basicConfig(level=logging.INFO, handlers=[h], force=True)
    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0, environment=os.getenv("SENTRY_ENV", "production"))
