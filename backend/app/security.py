"""Passwords (bcrypt), server-side session cookies, and an in-memory rate limiter."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .config import get_settings
from .db import AuthSession, User, get_db

COOKIE = "sarenakh_session"
SESSION_TTL = 30 * 24 * 3600


# --- passwords --------------------------------------------------------------------------------
# bcrypt only reads 72 bytes and Persian letters are 2 bytes each, so we pre-hash with SHA-256.


def _prehash(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode())
    except ValueError:
        return False


# --- sessions ---------------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, response: Response, user: User) -> None:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_token_hash(token), user_id=user.id, expires_at=time.time() + SESSION_TTL))
    response.set_cookie(
        COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax",
        secure=get_settings().cookie_secure, path="/",
    )


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).delete()
    response.delete_cookie(COOKIE, path="/")


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sess = db.get(AuthSession, _token_hash(token))
    if not sess or sess.expires_at < time.time():
        return None
    return db.get(User, sess.user_id)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "برای ادامه وارد حساب کاربری شوید.")
    return user


# --- rate limiting ----------------------------------------------------------------------------


class RateLimiter:
    """Sliding-window limiter, in memory (single worker by design)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: float) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            wait = int(window_s - (now - q[0])) + 1
            raise HTTPException(
                429, f"درخواست‌ها زیاد است. لطفا {wait} ثانیه دیگر دوباره تلاش کنید.",
                headers={"Retry-After": str(wait)},
            )
        q.append(now)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already resolves X-Forwarded-For from Caddy into request.client
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_s: float, per: str = "ip"):
    """Dependency factory: per='ip' or per='user'."""

    def dep(request: Request, user: User | None = Depends(optional_user)) -> None:
        who = f"u{user.id}" if per == "user" and user else client_ip(request)
        limiter.check(f"{name}:{who}", limit, window_s)

    return dep
