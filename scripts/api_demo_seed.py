"""Seed a fresh, un-approved demo incident for `make demo-ui` (idempotent).

Creates one open incident with a signal and a drafted (not yet approved) remediation plan, so the UI
shows a real case file with an actionable Approve button + the H07 banner. Stable keys, so re-runs do
not duplicate. Also seeds the login users. Run via `make demo-ui`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.api.auth import hash_password  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    AppUser,
    Incident,
    IncidentSignal,
    RemediationVersion,
)
from closcall.workflow.slice_diagnose import build_link_down_plan, plan_digest  # noqa: E402

USERS = [("viewer1", "viewer"), ("operator1", "operator"), ("approver1", "approver")]
KEY = "demo-ui:link-down:leaf1:ethernet-1/1"


async def run() -> int:
    Session = make_sessionmaker()
    async with Session() as s:
        for uid, role in USERS:
            await s.execute(
                pg_insert(AppUser)
                .values(user_id=uid, role=role, password_hash=hash_password("closcall-demo"))
                .on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={"role": role, "password_hash": hash_password("closcall-demo")},
                )
            )
        inc = (
            await s.execute(select(Incident).where(Incident.incident_key == KEY))
        ).scalar_one_or_none()
        if inc is None:
            inc = Incident(incident_key=KEY, status="open", severity="high")
            s.add(inc)
            await s.flush()
            s.add(
                IncidentSignal(
                    incident_id=inc.id,
                    source="rules",
                    source_event_id=f"{KEY}:oper-down",
                    observed_at=datetime.now(UTC),
                    payload_json={"oper_state": "down"},
                )
            )
            plan, _ = build_link_down_plan("leaf1", "ethernet-1/1", "2s4l-" + "0" * 8)
            plan["demo_ui"] = "1"  # stable, distinct digest from the slice's plan
            s.add(
                RemediationVersion(
                    incident_id=inc.id,
                    plan_version=1,
                    plan_json=plan,
                    plan_digest=plan_digest(plan),
                    topology_hash="2s4l-" + "0" * 8,
                    risk_class="low",
                )
            )
        await s.commit()
        print(f"demo incident ready: {KEY} ({inc.id}) — un-approved, drafted plan attached")
        print("  login: approver1 / closcall-demo (also viewer1, operator1)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
