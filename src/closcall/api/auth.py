"""Authentication core (Bible §13 HITL; Contracts §API auth).

Argon2id password hashing + a short-lived signed JWT carried in an HttpOnly/Secure/SameSite=Strict
cookie. Pure and deterministic (the clock is injected), so token minting/verification and expiry are
unit-tested without a running server. RBAC/CSRF/IDOR layer on top of this (Gate 11 piece 2). No
refresh token is stored (Contracts §8): the access token is short-lived and re-issued on login.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

COOKIE_NAME = "closcall_session"
ALGORITHM = "HS256"
DEFAULT_TTL_S = 900  # 15-minute short-lived access token (§8)

_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):  # mismatch or malformed hash -> fail closed
        return False


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


def mint_token(
    user_id: str, role: str, *, secret: str, now: datetime, ttl_s: int = DEFAULT_TTL_S
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_s)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_token(token: str, *, secret: str, now: datetime | None = None) -> Principal | None:
    """Validate signature + expiry (clock injectable for tests). None on any failure."""
    at = now or datetime.now(UTC)
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"verify_exp": False})
    except jwt.PyJWTError:
        return None  # bad signature / malformed / wrong secret
    if int(payload.get("exp", 0)) < int(at.timestamp()):
        return None  # expired
    sub, role = payload.get("sub"), payload.get("role")
    if not isinstance(sub, str) or not isinstance(role, str):
        return None
    return Principal(user_id=sub, role=role)


def session_cookie_kwargs() -> dict[str, object]:
    """Session-cookie attributes: HttpOnly, Secure, SameSite=Strict (browser XSS/CSRF defense)."""
    return {"key": COOKIE_NAME, "httponly": True, "secure": True, "samesite": "strict", "path": "/"}


__all__ = [
    "ALGORITHM",
    "COOKIE_NAME",
    "DEFAULT_TTL_S",
    "Principal",
    "hash_password",
    "mint_token",
    "session_cookie_kwargs",
    "verify_password",
    "verify_token",
]
