"""HITL API security acceptance — AUTHN, RBAC, CSRF, IDOR (Gate 11 exit). Offline TestClient."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from closcall.api.app import Incident, User, create_app
from closcall.api.auth import COOKIE_NAME, hash_password, mint_token

SECRET = "unit-test-signing-secret-at-least-32-bytes"


class Users:
    def __init__(self) -> None:
        self._u = {
            "alice": User(
                user_id="alice", role="operator", password_hash=hash_password("pw-alice")
            ),
            "vic": User(user_id="vic", role="viewer", password_hash=hash_password("pw-vic")),
        }

    def get(self, username: str) -> User | None:
        return self._u.get(username)


class Repo:
    def __init__(self) -> None:
        self._i = {
            "inc-1": Incident(id="inc-1", authorized_users=["alice", "vic"]),
            "inc-2": Incident(id="inc-2", authorized_users=["bob"]),  # neither alice nor vic
        }

    def get_incident(self, incident_id: str) -> Incident | None:
        return self._i.get(incident_id)


@pytest.fixture
def client() -> TestClient:
    app = create_app(secret=SECRET, users=Users(), repo=Repo())
    return TestClient(app, base_url="https://testserver")  # https so Secure cookies flow


def _login(client: TestClient, username: str, password: str) -> str:
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["csrf_token"]


def test_login_success_sets_session_and_csrf(client: TestClient) -> None:
    r = client.post("/login", json={"username": "alice", "password": "pw-alice"})
    assert r.status_code == 200 and r.json()["role"] == "operator"
    assert COOKIE_NAME in r.cookies and "closcall_csrf" in r.cookies


def test_login_bad_password_401(client: TestClient) -> None:
    r = client.post("/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/me").status_code == 401
    _login(client, "alice", "pw-alice")
    assert client.get("/me").json()["user_id"] == "alice"


def test_expired_session_rejected(client: TestClient) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    stale = mint_token("alice", "operator", secret=SECRET, now=past, ttl_s=900)
    client.cookies.set(COOKIE_NAME, stale)
    assert client.get("/me").status_code == 401


def test_rbac_viewer_cannot_ack(client: TestClient) -> None:
    csrf = _login(client, "vic", "pw-vic")  # viewer, not operator
    r = client.post("/incidents/inc-1/ack", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403  # RBAC: insufficient role


def test_csrf_required_on_state_change(client: TestClient) -> None:
    _login(client, "alice", "pw-alice")  # operator, authorized for inc-1
    assert client.post("/incidents/inc-1/ack").status_code == 403  # no CSRF header


def test_csrf_valid_allows_state_change(client: TestClient) -> None:
    csrf = _login(client, "alice", "pw-alice")
    r = client.post("/incidents/inc-1/ack", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["acked"] == "inc-1"


def test_csrf_mismatch_rejected(client: TestClient) -> None:
    _login(client, "alice", "pw-alice")
    r = client.post("/incidents/inc-1/ack", headers={"X-CSRF-Token": "forged-token"})
    assert r.status_code == 403


def test_idor_unauthorized_incident_hidden(client: TestClient) -> None:
    _login(client, "alice", "pw-alice")  # authorized for inc-1, NOT inc-2
    assert client.get("/incidents/inc-1").status_code == 200
    assert client.get("/incidents/inc-2").status_code == 404  # existence not leaked
