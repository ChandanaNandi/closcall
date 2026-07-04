"""HITL API with RBAC, CSRF, and IDOR protection (Bible §13; Contracts §API).

`create_app` wires an app around an injected user store + repository + signing secret, so it is
fully testable offline with Starlette's TestClient (no DB, no server). Security posture:

- AUTHN: session is the §auth JWT in an HttpOnly/Secure/SameSite=Strict cookie; missing/invalid ->
  401.
- RBAC: role-gated dependencies; wrong role -> 403.
- CSRF: double-submit — login also sets a non-HttpOnly CSRF cookie; every state-changing request
  must echo it in the X-CSRF-Token header (constant-time compared). Missing/mismatch -> 403.
- IDOR: resource access is authorization-checked (principal must be authorized for the incident),
  not merely authentication-checked; unauthorized -> 404 (existence is not leaked).
"""

from __future__ import annotations

import secrets as _secrets
from datetime import UTC, datetime
from typing import Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from closcall.api.auth import (
    COOKIE_NAME,
    Principal,
    mint_token,
    session_cookie_kwargs,
    verify_password,
    verify_token,
)

CSRF_COOKIE = "closcall_csrf"


class User(BaseModel):
    user_id: str
    role: str
    password_hash: str


class Incident(BaseModel):
    id: str
    authorized_users: list[str]  # IDOR authorization set


class UserStore(Protocol):
    def get(self, username: str) -> User | None: ...


class Repo(Protocol):
    def get_incident(self, incident_id: str) -> Incident | None: ...


class LoginBody(BaseModel):
    username: str
    password: str


def create_app(*, secret: str, users: UserStore, repo: Repo) -> FastAPI:
    app = FastAPI(title="ClosCall HITL")

    def principal(request: Request) -> Principal:
        token = request.cookies.get(COOKIE_NAME)
        p = verify_token(token, secret=secret) if token else None
        if p is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        return p

    def require(*roles: str):  # type: ignore[no-untyped-def]
        def dep(p: Principal = Depends(principal)) -> Principal:
            if p.role not in roles:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
            return p

        return dep

    require_reader = require("viewer", "operator", "approver")
    require_operator = require("operator")

    def csrf(request: Request, x_csrf_token: str | None = Header(default=None)) -> None:
        cookie = request.cookies.get(CSRF_COOKIE)
        if not cookie or not x_csrf_token or not _secrets.compare_digest(cookie, x_csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")

    def _authorized_incident(incident_id: str, p: Principal) -> Incident:
        inc = repo.get_incident(incident_id)
        if inc is None or p.user_id not in inc.authorized_users:  # IDOR: hide existence
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return inc

    @app.post("/login")
    def login(body: LoginBody, response: Response) -> dict[str, str]:
        user = users.get(body.username)
        if user is None or not verify_password(user.password_hash, body.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
        token = mint_token(user.user_id, user.role, secret=secret, now=datetime.now(UTC))
        response.set_cookie(value=token, **session_cookie_kwargs())  # type: ignore[arg-type]
        csrf_token = _secrets.token_urlsafe(32)
        response.set_cookie(  # non-HttpOnly so the client can echo it (double-submit)
            CSRF_COOKIE, csrf_token, secure=True, samesite="strict", path="/"
        )
        return {"user_id": user.user_id, "role": user.role, "csrf_token": csrf_token}

    @app.post("/logout")
    def logout(response: Response, p: Principal = Depends(principal)) -> dict[str, str]:
        response.delete_cookie(COOKIE_NAME, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
        return {"status": "logged_out"}

    @app.get("/me")
    def me(p: Principal = Depends(principal)) -> dict[str, str]:
        return {"user_id": p.user_id, "role": p.role}

    @app.get("/incidents/{incident_id}")
    def get_incident(
        incident_id: str,
        p: Principal = Depends(require_reader),
    ) -> dict[str, str]:
        inc = _authorized_incident(incident_id, p)
        return {"id": inc.id}

    @app.post("/incidents/{incident_id}/ack")
    def ack(
        incident_id: str,
        p: Principal = Depends(require_operator),
        _csrf: None = Depends(csrf),
    ) -> dict[str, str]:
        inc = _authorized_incident(incident_id, p)
        return {"acked": inc.id}

    return app


__all__ = ["CSRF_COOKIE", "Incident", "LoginBody", "Repo", "User", "UserStore", "create_app"]
