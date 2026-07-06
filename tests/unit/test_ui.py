"""Gate 14 UI acceptance — AUTHN/RBAC/CSRF/IDOR on the new routes, the H07 banner, and the
CRITICAL no-side-door property: the approve action cannot execute a plan without a valid approval
bound to the EXACT immutable digest. Offline TestClient + fakes (no DB, no server, no lab).
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from closcall.api.app import Incident, User, create_app
from closcall.api.approval import SideDoorRejected, guard_execution
from closcall.api.ui import H07_NOTICE
from closcall.api.ui_repo import CaseFile, DraftedPlan, IncidentSummary
from closcall.executor.binding import approval_authorizes_plan

SECRET = "test-secret"
INC = "11111111-1111-1111-1111-111111111111"
REAL = "digest-REAL"


class Users:
    _pw: ClassVar[dict[str, str]] = {"viewer1": "viewer", "approver1": "approver"}

    def __init__(self) -> None:
        from closcall.api.auth import hash_password

        self._h = {u: hash_password("pw") for u in self._pw}

    def get(self, username: str) -> User | None:
        role = self._pw.get(username)
        return User(user_id=username, role=role, password_hash=self._h[username]) if role else None


class Repo:  # legacy JSON route; unused by the UI
    def get_incident(self, incident_id: str) -> Incident | None:
        return None


class FakeDevice:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_oper_state(self, n: str, i: str) -> str:
        return "up"

    def set_admin_state(self, n: str, i: str, v: str) -> None:
        self.calls.append((n, i, v))


class FakeUIRepo:
    """Faithful stand-in: approve_and_execute runs the REAL binding guard before touching the
    device, as the DB adapter does — the side-door test exercises the real gate, not a mock."""

    def __init__(
        self,
        *,
        plan_digest: str = REAL,
        approval_digest: str = REAL,
        decision: str = "approve",
        authorized: bool = True,
    ) -> None:
        self.plan_digest = plan_digest
        self.approval_digest = approval_digest
        self.decision = decision
        self.authorized = authorized
        self.device = FakeDevice()
        self.executed = False

    def is_authorized(self, incident_id: str, user_id: str) -> bool:
        return self.authorized

    def _plan(self) -> DraftedPlan:
        return DraftedPlan(
            remediation_version_id="rv1",
            plan_version=1,
            plan_json={
                "action": "set_admin_state",
                "node": "leaf1",
                "interface": "ethernet-1/1",
                "value": "enable",
            },
            plan_digest=self.plan_digest,
            risk_class="low",
            localized_link="leaf1:ethernet-1/1",
            approved=False,
            executed_status=None,
        )

    def _summary(self) -> IncidentSummary:
        return IncidentSummary(
            id=INC,
            incident_key="link-down",
            status="open",
            severity="high",
            opened_at="2026-07-05T00:00:00",
            localized_link="leaf1:ethernet-1/1",
        )

    async def list_incidents(self, user_id: str) -> list[IncidentSummary]:
        return [self._summary()]

    async def get_case_file(self, incident_id: str) -> CaseFile | None:
        return CaseFile(incident=self._summary(), claim="supported", plan=self._plan())

    async def approve_and_execute(self, incident_id: str, user_id: str) -> str:
        # THE gate: refuse unless the approval binds the exact plan digest (real shared predicate).
        guard_execution(
            decision=self.decision,
            approval_digest=self.approval_digest,
            plan_digest=self.plan_digest,
        )
        self.device.set_admin_state("leaf1", "ethernet-1/1", "enable")  # only reached if authorized
        self.executed = True
        return "succeeded"

    async def reject(self, incident_id: str, user_id: str) -> None:
        return None

    async def edit_plan(self, incident_id: str, user_id: str) -> str:
        self.plan_digest = self.plan_digest + "-v2"  # new digest -> prior approval no longer binds
        return self.plan_digest


def _client(repo: FakeUIRepo) -> TestClient:
    app = create_app(secret=SECRET, users=Users(), repo=Repo(), ui_repo=repo)
    return TestClient(app, base_url="https://testserver")


def _login(c: TestClient, user: str) -> str:
    r = c.post("/login", json={"username": user, "password": "pw"})
    assert r.status_code == 200
    return r.json()["csrf_token"]


# ---------------------------------------------------------------- authn / rbac / csrf / idor
def test_unauthenticated_list_401() -> None:
    assert _client(FakeUIRepo()).get("/ui/incidents").status_code == 401


def test_viewer_cannot_approve_403() -> None:
    c = _client(FakeUIRepo())
    csrf = _login(c, "viewer1")
    r = c.post(f"/ui/incidents/{INC}/approve", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


def test_csrf_required_on_approve() -> None:
    c = _client(FakeUIRepo())
    _login(c, "approver1")
    assert c.post(f"/ui/incidents/{INC}/approve").status_code == 403  # no CSRF header


def test_idor_unauthorized_case_file_404() -> None:
    c = _client(FakeUIRepo(authorized=False))
    _login(c, "approver1")
    assert c.get(f"/ui/incidents/{INC}").status_code == 404  # existence hidden


# ---------------------------------------------------------------- H07 banner (honest labeling)
def test_h07_banner_on_case_file() -> None:
    c = _client(FakeUIRepo())
    _login(c, "approver1")
    body = c.get(f"/ui/incidents/{INC}").text
    assert H07_NOTICE[:60] in body and "Approve" in body  # banner sits with the approve button


def test_h07_banner_persists_in_approve_fragment() -> None:
    c = _client(FakeUIRepo())
    csrf = _login(c, "approver1")
    frag = c.post(f"/ui/incidents/{INC}/approve", headers={"X-CSRF-Token": csrf})
    assert frag.status_code == 200 and H07_NOTICE[:60] in frag.text


def test_approve_fragment_refreshes_whole_casefile() -> None:
    """The action swap must include the plan JSON and the audit section — no stale siblings."""
    c = _client(FakeUIRepo())
    csrf = _login(c, "approver1")
    frag = c.post(f"/ui/incidents/{INC}/approve", headers={"X-CSRF-Token": csrf})
    assert 'id="casefile"' in frag.text  # full partial, not just the decision panel
    assert "Drafted plan" in frag.text and "Audit trail" in frag.text


# ---------------------------------------------------------------- dashboard (front door)
def test_dashboard_renders_numbers_from_immutable_artifacts() -> None:
    """/ui/ parses the committed study artifacts — spot-check known frozen values render."""
    c = _client(FakeUIRepo())
    _login(c, "viewer1")  # reader role suffices
    body = c.get("/ui/").text
    assert "chance" in body and "Localizing the faulted link" in body
    assert "0.91" in body  # gray-fault MLP AUROC (temporal features), from the frozen table
    assert "312" in body  # corpus incidents, parsed from the ablation artifact
    assert "dd8def51" in body  # immutable run id prefix from the manifest


def test_dashboard_requires_auth() -> None:
    assert _client(FakeUIRepo()).get("/ui/").status_code == 401


def test_browser_navigation_unauthed_redirects_to_login() -> None:
    """A browser (Accept: text/html) with no/expired session is sent to the login page, not JSON."""
    c = _client(FakeUIRepo())
    r = c.get("/ui/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ui/login"
    # non-HTML clients keep the 401 JSON contract
    assert c.get("/ui/", headers={"Accept": "application/json"}).status_code == 401


# ---------------------------------------------------------------- happy path drives the executor
def test_approve_drives_executor() -> None:
    repo = FakeUIRepo()
    c = _client(repo)
    csrf = _login(c, "approver1")
    r = c.post(f"/ui/incidents/{INC}/approve", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert repo.executed and ("leaf1", "ethernet-1/1", "enable") in repo.device.calls


# ---------------------------------------------------------------- THE no-side-door proofs
def test_binding_predicate_rejects_mismatch() -> None:
    assert approval_authorizes_plan(decision="approve", approval_digest="X", plan_digest="X")
    assert not approval_authorizes_plan(decision="approve", approval_digest="X", plan_digest="Y")
    assert not approval_authorizes_plan(decision="reject", approval_digest="X", plan_digest="X")


def test_side_door_tampered_digest_refused_and_no_mutation() -> None:
    """Try to open the side door: an approval whose digest does NOT match the plan. Must refuse
    with 403 and must NEVER touch the device."""
    repo = FakeUIRepo(plan_digest="digest-REAL", approval_digest="digest-TAMPERED")
    c = _client(repo)
    csrf = _login(c, "approver1")
    r = c.post(f"/ui/incidents/{INC}/approve", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403
    assert repo.device.calls == []  # <-- the property: no mutation without a valid digest binding
    assert repo.executed is False


def test_side_door_no_approval_refused() -> None:
    """No approve decision (a reject) cannot execute — refused, device untouched."""
    repo = FakeUIRepo(decision="reject")
    c = _client(repo)
    csrf = _login(c, "approver1")
    r = c.post(f"/ui/incidents/{INC}/approve", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403
    assert repo.device.calls == []


def test_edit_bumps_digest_and_invalidates_prior_approval() -> None:
    """Edit bumps the digest; a prior approval bound to the old digest no longer binds (H03)."""
    repo = FakeUIRepo(plan_digest="digest-REAL", approval_digest="digest-REAL")
    c = _client(repo)
    csrf = _login(c, "approver1")
    c.post(f"/ui/incidents/{INC}/edit", headers={"X-CSRF-Token": csrf})
    assert repo.plan_digest == "digest-REAL-v2"  # new immutable version
    with pytest.raises(SideDoorRejected):  # the old approval digest no longer binds the new plan
        guard_execution(
            decision="approve", approval_digest="digest-REAL", plan_digest=repo.plan_digest
        )
