"""Gate 6 deterministic vertical slice (NO LLM/neural).

Drives the full chain against the live fabric + Postgres:
  inject admin_shutdown -> rules detect -> idempotent correlator opens ONE incident ->
  evidence + typed claim -> diagnosis -> prebuilt immutable plan (digest) -> approval + durable
  job (same txn) -> isolated executor (prechecks/set/read-back/recovery) -> audit chain.

Asserts the exit criteria: no LLM; duplicate signals/requests do not duplicate incident/execution;
injector cleanup is NOT the remediation (the executor's re-enable restores service — the injector's
clear() is never called). Writes evidence to evals/reports/gate6-slice.txt.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    ApprovalDecision,
    AuditEvent,
    Execution,
    ExecutionJob,
    Incident,
    IncidentEvent,
    IncidentSignal,
    RecoveryCheck,
    RemediationVersion,
)
from closcall.executor.executor import execute_job  # noqa: E402
from closcall.incidents.correlator import correlate_signal  # noqa: E402
from closcall.workflow.slice_diagnose import (  # noqa: E402
    build_link_down_plan,
    evaluate_oper_state_claim,
)

NODE, IFACE_SRL, IFACE_NETDEV = "leaf1", "ethernet-1/1", "e1-1"
CLABN = f"clab-closcall-2s4l-{NODE}"
_log: list[str] = []
_fail = 0


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
    print(line)
    _log.append(line)


class FabricDevice:
    """Executor's device access (holds the gNMI-Set capability). Read-only helpers for detection."""

    def get_oper_state(self, node: str, interface: str) -> str:
        p = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "root",
                f"clab-closcall-2s4l-{node}",
                "sr_cli",
                f"info from state interface {interface} oper-state",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "down" if "down" in p.stdout else ("up" if "up" in p.stdout else "unknown")

    def set_admin_state(self, node: str, interface: str, value: str) -> None:
        srl_val = "enable" if value == "enable" else "disable"
        # discard first: the SR Linux shared candidate persists across sessions, so a prior tool
        # (e.g. lab-check's B05 policy probe) can leave it dirty and make `commit now` fail.
        script = (
            "enter candidate\ndiscard stay\n"
            f"set / interface {interface} admin-state {srl_val}\ncommit now\n"
        )
        subprocess.run(
            ["docker", "exec", "-i", "-u", "root", f"clab-closcall-2s4l-{node}", "sr_cli"],
            input=script,
            capture_output=True,
            text=True,
            timeout=30,
        )


def inject_admin_shutdown() -> None:
    # discard first (see set_admin_state): a dirty shared candidate from a prior tool would
    # otherwise make this commit fail and the fault would silently never activate.
    subprocess.run(
        ["docker", "exec", "-i", "-u", "root", CLABN, "sr_cli"],
        input=(
            "enter candidate\ndiscard stay\n"
            f"set / interface {IFACE_SRL} admin-state disable\ncommit now\n"
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )


async def run() -> int:
    dev = FabricDevice()
    Session = make_sessionmaker()

    # clean slate for a repeatable slice
    async with Session() as s:
        await s.execute(AuditEvent.__table__.delete())
        for m in (
            RecoveryCheck,
            Execution,
            ExecutionJob,
            ApprovalDecision,
            RemediationVersion,
            IncidentSignal,
            IncidentEvent,  # FK-references incidents; must be cleared before Incident (idempotency)
        ):
            await s.execute(m.__table__.delete())
        await s.execute(Incident.__table__.delete())
        await s.commit()

    # 1. inject the fault (admin_shutdown); it stays ACTIVE — injector clear() is never called.
    # Re-assert + verify rather than trust one commit: on a freshly-converged node the first commit
    # can be accepted but not reflect in oper-state, so re-issue the disable every few seconds until
    # oper-state drops (up to ~25s). Still FAILS honestly if the fault never becomes active.
    down = "up"
    for i in range(25):
        if i % 5 == 0:
            inject_admin_shutdown()
        await asyncio.sleep(1)
        down = dev.get_oper_state(NODE, IFACE_SRL)
        if down == "down":
            break
    emit(down == "down", "fault active (admin_shutdown)", f"{NODE} {IFACE_SRL} oper-state={down}")

    # 2+3. rules detect -> idempotent correlator. Fire the SAME signal 100x -> ONE incident.
    incident_key = f"link-down:{NODE}:{IFACE_SRL}"
    sig_id = f"{NODE}:{IFACE_SRL}:oper-down"
    async with Session() as s:
        for _ in range(100):
            await correlate_signal(
                s,
                incident_key=incident_key,
                source="rules",
                source_event_id=sig_id,
                observed_at=datetime.now(UTC),
                payload={"oper_state": "down"},
            )
        await s.commit()
    async with Session() as s:
        n_inc = (await s.execute(select(func.count()).select_from(Incident))).scalar_one()
        n_sig = (await s.execute(select(func.count()).select_from(IncidentSignal))).scalar_one()
        incident_id = (await s.execute(select(Incident.id))).scalar_one()
    emit(
        n_inc == 1 and n_sig == 1,
        "idempotent correlator",
        f"100 duplicate signals -> {n_inc} incident, {n_sig} signal",
    )

    # 4. evidence + typed claim (deterministic, no LLM) -> diagnosis
    evidence = {"oper_state": dev.get_oper_state(NODE, IFACE_SRL)}
    claim = evaluate_oper_state_claim(evidence, expected="down")
    emit(claim == "supported", "typed claim (no LLM)", f"oper-state==down -> {claim}")

    # 5. prebuilt immutable plan + digest
    topo_hash = "2s4l-" + "0" * 8
    plan, digest = build_link_down_plan(NODE, IFACE_SRL, topo_hash)
    async with Session() as s:
        rv = RemediationVersion(
            incident_id=incident_id,
            plan_version=1,
            plan_json=plan,
            plan_digest=digest,
            topology_hash=topo_hash,
            risk_class="low",
        )
        s.add(rv)
        await s.commit()
        rv_id = rv.id
    emit(len(digest) == 64, "immutable plan digest", f"sha256={digest[:16]}")

    # 6. approval + durable job in the SAME txn; fire the request twice -> ONE job (idempotency).
    async def approve_and_enqueue() -> None:
        async with Session() as s:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            await s.execute(
                pg_insert(ApprovalDecision)
                .values(
                    id=uuid.uuid4(),
                    remediation_version_id=rv_id,
                    plan_digest=digest,
                    user_id="approver1",
                    decision="approve",
                )
                .on_conflict_do_nothing(index_elements=["remediation_version_id", "user_id"])
            )
            await s.execute(
                pg_insert(ExecutionJob)
                .values(
                    id=uuid.uuid4(),
                    remediation_version_id=rv_id,
                    idempotency_key=f"job:{digest}",
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            await s.commit()

    await approve_and_enqueue()
    await approve_and_enqueue()  # duplicate request
    async with Session() as s:
        n_job = (await s.execute(select(func.count()).select_from(ExecutionJob))).scalar_one()
        job_id = (await s.execute(select(ExecutionJob.id))).scalar_one()
    emit(n_job == 1, "duplicate request -> one job", f"2 approve+enqueue requests -> {n_job} job")

    # 7. isolated executor applies the approved job (prechecks/set/read-back/recovery)
    async with Session() as s:
        status = await execute_job(s, job_id, dev)
        await s.commit()
    after = dev.get_oper_state(NODE, IFACE_SRL)
    emit(
        status == "succeeded" and after == "up",
        "isolated executor recovery",
        f"execution={status}, {IFACE_SRL} oper-state={after}",
    )

    # 8. injector cleanup is NOT the remediation: the injector clear() was never called; recovery is
    #    attributable to the executor's set_admin_state(enable). Prove via audit + recovery rows.
    async with Session() as s:
        rec = (
            await s.execute(select(RecoveryCheck).where(RecoveryCheck.result == "passed"))
        ).first()
        audit_actions = (await s.execute(select(AuditEvent.action))).scalars().all()
    emit(
        rec is not None and "execution.apply" in audit_actions,
        "recovery via executor, not injector cleanup",
        f"recovery passed + audit chain: {sorted(set(audit_actions))}",
    )

    print(f"== {_fail} failed ==")
    (REPO / "evals" / "reports" / "gate6-slice.txt").write_text(
        "\n".join(_log) + f"\n== {_fail} failed ==\n"
    )
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
