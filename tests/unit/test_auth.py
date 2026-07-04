"""Auth core — Argon2id hashing, JWT mint/verify, expiry, tamper resistance, cookie flags."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from closcall.api.auth import (
    Principal,
    hash_password,
    mint_token,
    session_cookie_kwargs,
    verify_password,
    verify_token,
)

SECRET = "test-secret-key-at-least-32-bytes-long!"  # >=32 bytes (RFC 7518 §3.2)
T0 = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)


def test_argon2id_hash_roundtrip_and_wrong_password() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")  # Argon2id, not a weaker variant
    assert verify_password(h, "correct horse battery staple")
    assert not verify_password(h, "wrong password")
    assert not verify_password("not-even-a-hash", "x")


def test_token_roundtrip() -> None:
    token = mint_token("alice", "operator", secret=SECRET, now=T0)
    assert verify_token(token, secret=SECRET, now=T0) == Principal("alice", "operator")


def test_expired_token_rejected() -> None:
    token = mint_token("alice", "operator", secret=SECRET, now=T0, ttl_s=900)
    later = T0 + timedelta(seconds=901)
    assert verify_token(token, secret=SECRET, now=later) is None


def test_wrong_secret_rejected() -> None:
    token = mint_token("alice", "operator", secret=SECRET, now=T0)
    attacker = "a-different-but-also-32plus-byte-secret!"  # wrong key, still >=32 bytes
    assert verify_token(token, secret=attacker, now=T0) is None


def test_tampered_token_rejected() -> None:
    token = mint_token("alice", "operator", secret=SECRET, now=T0)
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    assert verify_token(tampered, secret=SECRET, now=T0) is None


def test_garbage_token_rejected() -> None:
    assert verify_token("not.a.jwt", secret=SECRET, now=T0) is None
    assert verify_token("", secret=SECRET, now=T0) is None


def test_session_cookie_is_httponly_secure_samesite_strict() -> None:
    kw = session_cookie_kwargs()
    assert kw["httponly"] is True
    assert kw["secure"] is True
    assert kw["samesite"] == "strict"
