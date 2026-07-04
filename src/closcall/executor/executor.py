"""Isolated executor (Bible §13.2/§13.3, §2.6/§2.7).

The executor is the ONLY component that holds device-mutation capability. It accepts a durable,
approved job, runs safety prechecks, captures pre-state, performs the smallest guarded mutation,
reads state back, evaluates a recovery predicate, and records everything. Ambiguous read-back is
`outcome_unknown`, never success (§13.3). The device is injected (a `Device` protocol) so the
credential boundary is explicit and the logic is unit-testable.

Allowlist (slice scope): the only permitted action is re-enabling admin-state on a NON-management
fabric interface — the safe reversal of an admin_shutdown fault.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from closcall.db.models import (
    ApprovalDecision,
    AuditEvent,
    Execution,
    ExecutionJob,
    RecoveryCheck,
    RemediationVersion,
)
from closcall.executor.audit_guard import AuditUnavailable

ALLOWED_ACTIONS = {"set_admin_state"}
ALLOWED_VALUES = {"enable"}


class Device(Protocol):
    def get_oper_state(self, node: str, interface: str) -> str: ...
    def set_admin_state(self, node: str, interface: str, value: str) -> None: ...


class PrecheckError(Exception):
    pass


async def _precheck(session: AsyncSession, rv: RemediationVersion) -> dict:  # type: ignore[type-arg]
    # valid approval for the exact digest/version (§13.2)
    appr = (
        await session.execute(
            select(ApprovalDecision).where(
                ApprovalDecision.remediation_version_id == rv.id,
                ApprovalDecision.plan_digest == rv.plan_digest,
                ApprovalDecision.decision == "approve",
            )
        )
    ).scalar_one_or_none()
    if appr is None:
        raise PrecheckError("no valid approval for this plan digest")
    plan = rv.plan_json
    if plan.get("action") not in ALLOWED_ACTIONS or plan.get("value") not in ALLOWED_VALUES:
        raise PrecheckError(
            f"action/value not allowlisted: {plan.get('action')}/{plan.get('value')}"
        )
    if str(plan.get("interface", "")).startswith("mgmt"):
        raise PrecheckError("target is a management interface")
    return plan


async def execute_job(session: AsyncSession, job_id: uuid.UUID, device: Device) -> str:
    """Run one approved job through prechecks/set/read-back/recovery. Returns execution status."""
    job = (
        await session.execute(select(ExecutionJob).where(ExecutionJob.id == job_id))
    ).scalar_one()
    rv = (
        await session.execute(
            select(RemediationVersion).where(RemediationVersion.id == job.remediation_version_id)
        )
    ).scalar_one()

    # competing-execution guard: one execution per job (also a DB unique constraint)
    if (
        await session.execute(select(Execution).where(Execution.execution_job_id == job.id))
    ).scalar_one_or_none() is not None:
        return "duplicate_ignored"

    plan = await _precheck(session, rv)
    node, iface, value = plan["node"], plan["interface"], plan["value"]

    before = device.get_oper_state(node, iface)  # pre-state capture (§13.2)
    job.status = "running"

    # audit-write-first (§10/§13.3): persist mutation intent durably BEFORE touching the device;
    # if the audit write fails, the state change never happens.
    session.add(
        AuditEvent(
            actor_type="executor",
            actor_id="executor",
            action="execution.apply.intent",
            entity_type="execution_job",
            entity_id=str(job.id),
            before_json={"oper_state": before},
            after_json={"intended_value": value},
        )
    )
    try:
        await session.flush()
    except Exception as exc:  # audit/db unavailable -> block the mutation
        raise AuditUnavailable("audit write failed; execution blocked") from exc

    device.set_admin_state(node, iface, value)  # smallest guarded mutation
    after = device.get_oper_state(node, iface)  # read-back (§13.3)

    if after == "up":
        status, failure = "succeeded", None
    elif after in ("", "unknown"):
        status, failure = "outcome_unknown", "ambiguous_readback"  # never success (§13.3)
    else:
        status, failure = "failed", "readback_not_up"

    execution = Execution(
        execution_job_id=job.id,
        status=status,
        observed_config_before={"oper_state": before},
        observed_config_after={"oper_state": after},
        failure_class=failure,
    )
    session.add(execution)
    await session.flush()

    recovery_passed = status == "succeeded" and after == "up"
    session.add(
        RecoveryCheck(
            execution_id=execution.id,
            check_type="oper_state_up",
            result="passed" if recovery_passed else "failed",
            observed_json={"before": before, "after": after},
        )
    )
    job.status = "completed" if status == "succeeded" else "reconciling"
    session.add(
        AuditEvent(
            actor_type="executor",
            actor_id="executor",
            action="execution.apply",
            entity_type="execution_job",
            entity_id=str(job.id),
            before_json={"oper_state": before},
            after_json={"oper_state": after, "status": status},
        )
    )
    return status


__all__ = ["ALLOWED_ACTIONS", "Device", "PrecheckError", "execute_job"]
