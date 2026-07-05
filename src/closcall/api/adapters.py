"""DB-backed adapters wiring the Gate 14 UI to the real core.* tables (Gate 11's noted loose end).

`DbUserStore` serves login from `core.app_users`; `DbUIRepo` reads incidents/signals/remediation/
audit and drives the EXISTING gated executor for approvals. No new execution path:
`approve_and_execute` records an approval bound to the stored plan digest, then calls `execute_job`,
whose precheck re-checks the same binding. IDOR is role-scoped (single-tenant lab, no owner column).
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from closcall.api.app import User
from closcall.api.approval import guard_execution
from closcall.api.ui_repo import (
    AuditEntry,
    CaseFile,
    DraftedPlan,
    IncidentSummary,
)
from closcall.db.engine import make_sessionmaker
from closcall.db.models import (
    ApprovalDecision,
    AuditEvent,
    Execution,
    ExecutionJob,
    Incident,
    IncidentSignal,
    RemediationVersion,
)
from closcall.executor.executor import Device, execute_job
from closcall.executor.fabric_device import FabricDevice
from closcall.workflow.slice_diagnose import plan_digest

READER_ROLES = ("viewer", "operator", "approver")


class DbUserStore:
    """UserStore over core.app_users. get() is sync (login endpoint is sync) via a fresh loop."""

    def get(self, username: str) -> User | None:
        async def _q() -> User | None:
            Session = make_sessionmaker()
            async with Session() as s:
                from closcall.db.models import AppUser

                u = (
                    await s.execute(select(AppUser).where(AppUser.user_id == username))
                ).scalar_one_or_none()
                if u is None:
                    return None
                return User(user_id=u.user_id, role=u.role, password_hash=u.password_hash)

        return asyncio.run(_q())


def _localized_link(plan_json: dict) -> str:  # type: ignore[type-arg]
    return f"{plan_json.get('node', '?')}:{plan_json.get('interface', '?')}"


class DbUIRepo:
    """DB-backed UIRepo. `device` is the injected mutation capability (FabricDevice in prod)."""

    def __init__(self, device: Device | None = None) -> None:
        self.device: Device = device or FabricDevice()

    # --- IDOR: single-tenant lab -> any reader role may view (role gate happens at the route) ---
    def is_authorized(self, incident_id: str, user_id: str) -> bool:
        return True  # role-scoped in the lab; no per-user incident ownership column exists

    async def list_incidents(self, user_id: str) -> list[IncidentSummary]:
        Session = make_sessionmaker()
        async with Session() as s:
            rows = (
                (await s.execute(select(Incident).order_by(Incident.opened_at.desc())))
                .scalars()
                .all()
            )
            out: list[IncidentSummary] = []
            for inc in rows:
                rv = (
                    (
                        await s.execute(
                            select(RemediationVersion)
                            .where(RemediationVersion.incident_id == inc.id)
                            .order_by(RemediationVersion.plan_version.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
                link = _localized_link(rv.plan_json) if rv else None
                out.append(
                    IncidentSummary(
                        id=str(inc.id),
                        incident_key=inc.incident_key,
                        status=inc.status,
                        severity=inc.severity,
                        opened_at=inc.opened_at.isoformat() if inc.opened_at else "",
                        localized_link=link,
                    )
                )
            return out

    async def get_case_file(self, incident_id: str) -> CaseFile | None:
        Session = make_sessionmaker()
        async with Session() as s:
            inc = (
                await s.execute(select(Incident).where(Incident.id == uuid.UUID(incident_id)))
            ).scalar_one_or_none()
            if inc is None:
                return None
            sigs = (
                (
                    await s.execute(
                        select(IncidentSignal).where(IncidentSignal.incident_id == inc.id)
                    )
                )
                .scalars()
                .all()
            )
            rv = (
                (
                    await s.execute(
                        select(RemediationVersion)
                        .where(RemediationVersion.incident_id == inc.id)
                        .order_by(RemediationVersion.plan_version.desc())
                    )
                )
                .scalars()
                .first()
            )
            plan = None
            if rv is not None:
                appr = (
                    (
                        await s.execute(
                            select(ApprovalDecision).where(
                                ApprovalDecision.remediation_version_id == rv.id,
                                ApprovalDecision.plan_digest == rv.plan_digest,
                                ApprovalDecision.decision == "approve",
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                job = (
                    (
                        await s.execute(
                            select(ExecutionJob).where(ExecutionJob.remediation_version_id == rv.id)
                        )
                    )
                    .scalars()
                    .first()
                )
                exec_status = None
                if job is not None:
                    ex = (
                        (
                            await s.execute(
                                select(Execution).where(Execution.execution_job_id == job.id)
                            )
                        )
                        .scalars()
                        .first()
                    )
                    exec_status = ex.status if ex else job.status
                plan = DraftedPlan(
                    remediation_version_id=str(rv.id),
                    plan_version=rv.plan_version,
                    plan_json=rv.plan_json,
                    plan_digest=rv.plan_digest,
                    risk_class=rv.risk_class,
                    localized_link=_localized_link(rv.plan_json),
                    approved=appr is not None,
                    executed_status=exec_status,
                )
            audit = (
                (
                    await s.execute(
                        select(AuditEvent)
                        .where(AuditEvent.entity_id == str(inc.id))
                        .order_by(AuditEvent.id.desc())
                    )
                )
                .scalars()
                .all()
            )
            # also fold in execution audit for this incident's remediation, if any
            summary = IncidentSummary(
                id=str(inc.id),
                incident_key=inc.incident_key,
                status=inc.status,
                severity=inc.severity,
                opened_at=inc.opened_at.isoformat() if inc.opened_at else "",
                localized_link=plan.localized_link if plan else None,
            )
            claim = "supported" if (plan and plan.localized_link) else "insufficient"
            return CaseFile(
                incident=summary,
                signals=[{"source": x.source, "observed_at": str(x.observed_at)} for x in sigs],
                claim=claim,
                evidence={"signals": len(sigs)},
                plan=plan,
                audit=[
                    AuditEntry(
                        occurred_at="",
                        actor_type=a.actor_type,
                        action=a.action,
                        entity_type=a.entity_type,
                        summary=str(a.after_json)[:120],
                    )
                    for a in audit
                ],
            )

    async def approve_and_execute(self, incident_id: str, user_id: str) -> str:
        Session = make_sessionmaker()
        async with Session() as s:
            inc_id = uuid.UUID(incident_id)
            rv = (
                (
                    await s.execute(
                        select(RemediationVersion)
                        .where(RemediationVersion.incident_id == inc_id)
                        .order_by(RemediationVersion.plan_version.desc())
                    )
                )
                .scalars()
                .first()
            )
            if rv is None:
                raise ValueError("no drafted plan to approve")
            digest = rv.plan_digest  # bind to the STORED digest, never a client-supplied value
            await s.execute(
                pg_insert(ApprovalDecision)
                .values(
                    id=uuid.uuid4(),
                    remediation_version_id=rv.id,
                    plan_digest=digest,
                    user_id=user_id,
                    decision="approve",
                )
                .on_conflict_do_nothing(index_elements=["remediation_version_id", "user_id"])
            )
            await s.execute(
                pg_insert(ExecutionJob)
                .values(
                    id=uuid.uuid4(),
                    remediation_version_id=rv.id,
                    idempotency_key=f"job:{digest}",
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            await s.commit()
            appr = (
                (
                    await s.execute(
                        select(ApprovalDecision)
                        .where(
                            ApprovalDecision.remediation_version_id == rv.id,
                            ApprovalDecision.decision == "approve",
                        )
                        .order_by(ApprovalDecision.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            job = (
                (
                    await s.execute(
                        select(ExecutionJob).where(ExecutionJob.remediation_version_id == rv.id)
                    )
                )
                .scalars()
                .first()
            )
        # UI-layer guard (defense in depth); the executor precheck re-checks the SAME binding.
        guard_execution(
            decision=appr.decision if appr else None,
            approval_digest=appr.plan_digest if appr else None,
            plan_digest=digest,
        )
        if job is None:  # unreachable (just inserted), but keep the executor call total
            raise ValueError("no execution job to run")
        async with Session() as s2:
            status = await execute_job(s2, job.id, self.device)
            await s2.commit()
        return status

    async def reject(self, incident_id: str, user_id: str) -> None:
        Session = make_sessionmaker()
        async with Session() as s:
            rv = (
                (
                    await s.execute(
                        select(RemediationVersion)
                        .where(RemediationVersion.incident_id == uuid.UUID(incident_id))
                        .order_by(RemediationVersion.plan_version.desc())
                    )
                )
                .scalars()
                .first()
            )
            if rv is None:
                return
            await s.execute(
                pg_insert(ApprovalDecision)
                .values(
                    id=uuid.uuid4(),
                    remediation_version_id=rv.id,
                    plan_digest=rv.plan_digest,
                    user_id=user_id,
                    decision="reject",
                )
                .on_conflict_do_nothing(index_elements=["remediation_version_id", "user_id"])
            )
            await s.commit()

    async def edit_plan(self, incident_id: str, user_id: str) -> str:
        """New immutable plan version: bump an embedded revision so the digest changes -> any prior
        approval no longer binds (H03). The action stays the same safe allowlisted re-enable."""
        Session = make_sessionmaker()
        async with Session() as s:
            rv = (
                (
                    await s.execute(
                        select(RemediationVersion)
                        .where(RemediationVersion.incident_id == uuid.UUID(incident_id))
                        .order_by(RemediationVersion.plan_version.desc())
                    )
                )
                .scalars()
                .first()
            )
            if rv is None:
                raise ValueError("no plan to edit")
            new_json = dict(rv.plan_json)
            new_json["plan_revision"] = int(new_json.get("plan_revision", 0)) + 1
            new_digest = plan_digest(new_json)
            s.add(
                RemediationVersion(
                    incident_id=rv.incident_id,
                    plan_version=rv.plan_version + 1,
                    plan_json=new_json,
                    plan_digest=new_digest,
                    topology_hash=rv.topology_hash,
                    risk_class=rv.risk_class,
                )
            )
            await s.commit()
            return new_digest


__all__ = ["READER_ROLES", "DbUIRepo", "DbUserStore"]
