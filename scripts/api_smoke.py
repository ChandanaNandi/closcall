"""Clean-clone HTTP smoke for the Gate 14 UI (make api-smoke).

Seeds a synthetic incident + drafted plan, then drives login → incident list → case file → approve
over an offline HTTPS TestClient against the REAL DB, with a FAKE device (no live lab needed).
Asserts: the H07 banner renders on the case file, the approve action drives the gated executor
(device flipped, execution recorded), and unauthenticated access is refused. Non-zero on failure.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.api.adapters import DbUIRepo, DbUserStore  # noqa: E402
from closcall.api.app import create_app  # noqa: E402
from closcall.api.auth import hash_password  # noqa: E402
from closcall.api.ui import H07_NOTICE  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    ApprovalDecision,
    AppUser,
    AuditEvent,
    Execution,
    ExecutionJob,
    Incident,
    IncidentSignal,
    RecoveryCheck,
    RemediationVersion,
)
from closcall.workflow.slice_diagnose import build_link_down_plan, plan_digest  # noqa: E402

SECRET = "smoke-secret"
KEY = f"smoke-link-down-{uuid.uuid4().hex[:8]}"


class FakeDevice:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_oper_state(self, node: str, interface: str) -> str:
        return "up"  # after re-enable, reads up -> executor 'succeeded'

    def set_admin_state(self, node: str, interface: str, value: str) -> None:
        self.calls.append((node, interface, value))


async def seed() -> str:
    from datetime import UTC, datetime

    Session = make_sessionmaker()
    async with Session() as s:
        await s.execute(
            pg_insert(AppUser)
            .values(user_id="approver1", role="approver", password_hash=hash_password("pw"))
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={"role": "approver", "password_hash": hash_password("pw")},
            )
        )
        inc = Incident(incident_key=KEY, status="open", severity="high")
        s.add(inc)
        await s.flush()
        s.add(
            IncidentSignal(
                incident_id=inc.id,
                source="rules",
                source_event_id=f"leaf1:ethernet-1/1:oper-down:{KEY}",  # unique per smoke run
                observed_at=datetime.now(UTC),
                payload_json={"oper_state": "down"},
            )
        )
        plan, _ = build_link_down_plan("leaf1", "ethernet-1/1", "2s4l-" + "0" * 8)
        plan["smoke_run"] = KEY  # unique digest per run (avoids uq_remv_digest with prior runs)
        digest = plan_digest(plan)
        s.add(
            RemediationVersion(
                incident_id=inc.id,
                plan_version=1,
                plan_json=plan,
                plan_digest=digest,
                topology_hash="2s4l-" + "0" * 8,
                risk_class="low",
            )
        )
        await s.commit()
        return str(inc.id)


async def cleanup(inc_id: str) -> None:
    Session = make_sessionmaker()
    async with Session() as s:
        iid = uuid.UUID(inc_id)
        rvs = (
            (
                await s.execute(
                    select(RemediationVersion.id).where(RemediationVersion.incident_id == iid)
                )
            )
            .scalars()
            .all()
        )
        jobs = (
            (
                await s.execute(
                    select(ExecutionJob.id).where(
                        ExecutionJob.remediation_version_id.in_(rvs or [uuid.uuid4()])
                    )
                )
            )
            .scalars()
            .all()
        )
        await s.execute(
            delete(RecoveryCheck).where(
                RecoveryCheck.execution_id.in_(
                    (
                        await s.execute(
                            select(Execution.id).where(
                                Execution.execution_job_id.in_(jobs or [uuid.uuid4()])
                            )
                        )
                    )
                    .scalars()
                    .all()
                    or [uuid.uuid4()]
                )
            )
        )
        await s.execute(
            delete(Execution).where(Execution.execution_job_id.in_(jobs or [uuid.uuid4()]))
        )
        await s.execute(
            delete(ExecutionJob).where(
                ExecutionJob.remediation_version_id.in_(rvs or [uuid.uuid4()])
            )
        )
        await s.execute(
            delete(ApprovalDecision).where(
                ApprovalDecision.remediation_version_id.in_(rvs or [uuid.uuid4()])
            )
        )
        await s.execute(delete(RemediationVersion).where(RemediationVersion.incident_id == iid))
        await s.execute(delete(IncidentSignal).where(IncidentSignal.incident_id == iid))
        await s.execute(delete(AuditEvent).where(AuditEvent.entity_id == inc_id))
        await s.execute(delete(Incident).where(Incident.id == iid))
        await s.commit()


def main() -> int:
    inc_id = asyncio.run(seed())
    ok = True

    def check(cond: bool, name: str) -> None:
        nonlocal ok
        ok = ok and cond
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    try:
        device = FakeDevice()
        app = create_app(secret=SECRET, users=DbUserStore(), repo=_Null(), ui_repo=DbUIRepo(device))
        c = TestClient(app, base_url="https://testserver")

        check(c.get("/ui/incidents").status_code == 401, "unauthenticated list -> 401")

        r = c.post("/login", json={"username": "approver1", "password": "pw"})
        check(r.status_code == 200, "approver login 200")
        csrf = r.json()["csrf_token"]

        lst = c.get("/ui/incidents")
        check(lst.status_code == 200 and KEY in lst.text, "incident list shows the incident")

        cf = c.get(f"/ui/incidents/{inc_id}")
        check(cf.status_code == 200, "case file 200")
        check(H07_NOTICE[:40] in cf.text, "H07 banner present on case file")
        check("Approve" in cf.text, "approve button present")

        ap = c.post(f"/ui/incidents/{inc_id}/approve", headers={"X-CSRF-Token": csrf})
        check(ap.status_code == 200, "approve 200")
        check(
            ("leaf1", "ethernet-1/1", "enable") in device.calls,
            "executor flipped the device (enable)",
        )
        check(H07_NOTICE[:40] in ap.text, "H07 banner still present after approve")

        got = asyncio.run(_exec_recorded(inc_id))
        check(got, "execution recorded in DB (audit chain)")
    finally:
        asyncio.run(cleanup(inc_id))

    print("api-smoke:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


class _Null:
    def get_incident(self, incident_id: str):  # type: ignore[no-untyped-def]
        return None


async def _exec_recorded(inc_id: str) -> bool:
    Session = make_sessionmaker()
    async with Session() as s:
        rvs = (
            (
                await s.execute(
                    select(RemediationVersion.id).where(
                        RemediationVersion.incident_id == uuid.UUID(inc_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rvs:
            return False
        jobs = (
            (
                await s.execute(
                    select(ExecutionJob.id).where(ExecutionJob.remediation_version_id.in_(rvs))
                )
            )
            .scalars()
            .all()
        )
        execs = (
            (
                await s.execute(
                    select(Execution).where(Execution.execution_job_id.in_(jobs or [uuid.uuid4()]))
                )
            )
            .scalars()
            .all()
        )
        return len(execs) >= 1


if __name__ == "__main__":
    sys.exit(main())
