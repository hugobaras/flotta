import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_BYTES = 5 * 1024 * 1024
MAX_PER_CHECK = 5
# Type déduit du contenu, jamais du nom ni du Content-Type envoyés par le client.
MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png"}


def detect_ext(data: bytes) -> str | None:
    return next((ext for sig, ext in MAGIC.items() if data.startswith(sig)), None)


def save(company_id: int, data: bytes, ext: str) -> str:
    folder = UPLOAD_DIR / str(company_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (folder / name).write_bytes(data)
    return name


def path(company_id: int, name: str) -> Path:
    return UPLOAD_DIR / str(company_id) / name
