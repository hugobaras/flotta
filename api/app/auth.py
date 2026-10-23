import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models import Session, User

router = APIRouter(prefix="/api/auth")
hasher = PasswordHasher()
COOKIE = "session"
SESSION_DAYS = 7
MAX_FAILURES, WINDOW = 5, 15 * 60

# shortcut: compteur en mémoire, valable pour un seul worker ; passer sur Redis à l'étape 3.
_failures: dict[str, list[float]] = {}


def _recent_failures(email: str) -> list[float]:
    now = time.monotonic()
    recent = [t for t in _failures.get(email, []) if now - t < WINDOW]
    _failures[email] = recent
    return recent


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(session: str | None = Cookie(default=None), db: DbSession = Depends(get_db)) -> User:
    row = db.get(Session, _digest(session)) if session else None
    if not row or row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "Non connecté")
    return db.get(User, row.user_id)


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response, db: DbSession = Depends(get_db)):
    email = body.email.strip().lower()
    if len(_recent_failures(email)) >= MAX_FAILURES:
        raise HTTPException(429, "Trop de tentatives, réessayez plus tard")
    user = db.scalar(select(User).where(User.email == email))
    try:
        if not user:
            raise VerifyMismatchError
        hasher.verify(user.password_hash, body.password)
    except VerifyMismatchError:
        _failures[email].append(time.monotonic())
        raise HTTPException(401, "Identifiants invalides")
    _failures.pop(email, None)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.add(Session(id=_digest(token), user_id=user.id, expires_at=expires))
    db.commit()
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_DAYS * 86400,
        secure=os.getenv("COOKIE_SECURE", "0") == "1",
    )
    return {"email": user.email, "role": user.role}


@router.post("/logout")
def logout(response: Response, session: str | None = Cookie(default=None), db: DbSession = Depends(get_db)):
    if session:
        db.execute(delete(Session).where(Session.id == _digest(session)))
        db.commit()
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "role": user.role}
