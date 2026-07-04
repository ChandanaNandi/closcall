"""§13.1/§13.2 immutable plan digest + prechecks fail closed. Pure/offline."""

from __future__ import annotations

from dataclasses import replace

from closcall.executor.plan import Action, Plan
from closcall.executor.prechecks import (
    PrecheckContext,
    executable,
    failures,
    run_prechecks,
)


def _plan() -> Plan:
    return Plan(
        incident_id="inc-1",
        plan_version=3,
        actions=(Action("set_admin_state", "leaf1", "ethernet-1/1", "enable"),),
        topology_hash="topo-abc",
        preconditions=("interface_admin_down",),
        postconditions=("interface_oper_up",),
        recovery_predicate="oper_state==up",
        rollback=(Action("set_admin_state", "leaf1", "ethernet-1/1", "disable"),),
        risk_class="low",
        provenance={"incident": "inc-1"},
    )


def _ctx(plan: Plan) -> PrecheckContext:
    return PrecheckContext(
        approved_digest=plan.digest(),
        approved_version=plan.plan_version,
        current_topology_hash=plan.topology_hash,
        telemetry_fresh=True,
        allowed_actions=frozenset({"set_admin_state"}),
        allowed_values=frozenset({"enable"}),
        competing_execution=False,
        alternate_path_healthy=True,
        capacity_headroom_ok=True,
        would_remove_final_path=False,
        audit_writable=True,
        db_writable=True,
    )


def test_all_prechecks_pass_is_executable() -> None:
    plan = _plan()
    assert executable(run_prechecks(plan, _ctx(plan)))


def test_edited_plan_fails_closed_on_approval() -> None:
    # an edited plan has a new digest; the approval was bound to the OLD digest -> fail closed
    plan = _plan()
    ctx = _ctx(plan)  # approval bound to the original digest
    edited = replace(plan, actions=(Action("set_admin_state", "leaf1", "ethernet-1/2", "enable"),))
    results = run_prechecks(edited, ctx)
    assert not executable(results)
    assert "approval_valid_for_digest_and_version" in failures(results)


def test_digest_changes_with_any_edit_and_is_deterministic() -> None:
    plan = _plan()
    assert plan.digest() == _plan().digest()  # deterministic
    assert replace(plan, risk_class="high").digest() != plan.digest()
    assert replace(plan, plan_version=4).digest() != plan.digest()


def test_topology_drift_fails_closed() -> None:
    plan = _plan()
    ctx = replace(_ctx(plan), current_topology_hash="topo-DRIFTED")
    assert not executable(run_prechecks(plan, ctx))
    assert "no_topology_drift" in failures(run_prechecks(plan, ctx))


def test_management_interface_target_fails_closed() -> None:
    plan = _plan()
    mgmt = replace(plan, actions=(Action("set_admin_state", "leaf1", "mgmt0", "enable"),))
    # rebind approval to the edited plan so ONLY the mgmt check fails
    ctx = replace(_ctx(plan), approved_digest=mgmt.digest())
    results = run_prechecks(mgmt, ctx)
    assert not executable(results)
    assert "target_not_management_interface" in failures(results)


def test_each_context_flag_fails_closed() -> None:
    plan = _plan()
    flips = {
        "telemetry_fresh": False,
        "competing_execution": True,
        "alternate_path_healthy": False,
        "capacity_headroom_ok": False,
        "would_remove_final_path": True,
        "audit_writable": False,
        "db_writable": False,
    }
    for field, bad in flips.items():
        ctx = replace(_ctx(plan), **{field: bad})
        assert not executable(run_prechecks(plan, ctx)), f"{field} should fail closed"


def test_missing_rollback_or_recovery_fails_closed() -> None:
    plan = _plan()
    no_rollback = replace(plan, rollback=())
    ctx = replace(_ctx(plan), approved_digest=no_rollback.digest())
    assert "rollback_defined" in failures(run_prechecks(no_rollback, ctx))
    no_recovery = replace(plan, recovery_predicate="")
    ctx2 = replace(_ctx(plan), approved_digest=no_recovery.digest())
    assert "recovery_predicate_defined" in failures(run_prechecks(no_recovery, ctx2))


def test_non_allowlisted_action_fails_closed() -> None:
    plan = _plan()
    danger = replace(plan, actions=(Action("delete_config", "leaf1", "ethernet-1/1", "enable"),))
    ctx = replace(_ctx(plan), approved_digest=danger.digest())
    assert "actions_and_params_allowlisted" in failures(run_prechecks(danger, ctx))
