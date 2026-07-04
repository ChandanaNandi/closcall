"""§13.2 mandatory prechecks (Bible §13.2; Gate 11 exit: stale/edited/drifted plans fail closed).

Every check must pass before the executor may mutate anything. Pure: all environment facts arrive
in a `PrecheckContext`, so each check is unit-tested in isolation and the whole suite fails CLOSED —
any failing check makes the plan non-executable. The approval is bound to the plan's exact digest
and version, so an edited plan (new digest) or a stale/superseded version fails the first check.
"""

from __future__ import annotations

from dataclasses import dataclass

from closcall.executor.plan import Plan


@dataclass(frozen=True)
class PrecheckContext:
    approved_digest: str | None  # digest an approval exists for (None if unapproved)
    approved_version: int | None
    current_topology_hash: str  # live topology/config revision (drift check)
    telemetry_fresh: bool  # fresh AND complete telemetry
    allowed_actions: frozenset[str]
    allowed_values: frozenset[str]
    competing_execution: bool  # another execution in flight on the target
    alternate_path_healthy: bool
    capacity_headroom_ok: bool  # remaining capacity above configured headroom
    would_remove_final_path: bool  # change would remove the final usable path
    audit_writable: bool
    db_writable: bool


@dataclass(frozen=True)
class PrecheckResult:
    name: str
    ok: bool
    detail: str = ""


def run_prechecks(plan: Plan, ctx: PrecheckContext) -> list[PrecheckResult]:
    """Run every §13.2 check against the plan + context; order is stable for auditing."""
    r: list[PrecheckResult] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        r.append(PrecheckResult(name, ok, detail if not ok else ""))

    digest = plan.digest()
    # 1. valid approval for the EXACT digest and plan version
    check(
        "approval_valid_for_digest_and_version",
        ctx.approved_digest == digest and ctx.approved_version == plan.plan_version,
        "no approval for this exact plan digest/version (edited or unapproved)",
    )
    # 2. no topology / config drift
    check(
        "no_topology_drift",
        ctx.current_topology_hash == plan.topology_hash,
        "topology/config drifted since the plan was built",
    )
    # 3. fresh, complete telemetry
    check("telemetry_fresh_and_complete", ctx.telemetry_fresh, "telemetry stale or incomplete")
    # 4. target/action/parameters on allowlists
    allow_ok = bool(plan.actions) and all(
        a.action in ctx.allowed_actions and a.value in ctx.allowed_values for a in plan.actions
    )
    check("actions_and_params_allowlisted", allow_ok, "an action/parameter is not allow-listed")
    # 5. target is not a management interface
    check(
        "target_not_management_interface",
        all(not a.interface.startswith("mgmt") for a in plan.actions),
        "a target is a management interface",
    )
    # 6. no competing execution on the target
    check(
        "no_competing_execution", not ctx.competing_execution, "a competing execution is in flight"
    )
    # 7. alternate path healthy
    check("alternate_path_healthy", ctx.alternate_path_healthy, "no healthy alternate path")
    # 8. remaining capacity above headroom
    check("capacity_above_headroom", ctx.capacity_headroom_ok, "capacity below configured headroom")
    # 9. change cannot remove the final usable path
    check(
        "keeps_final_usable_path",
        not ctx.would_remove_final_path,
        "change would remove the final usable path",
    )
    # 10. audit and database writable
    check("audit_writable", ctx.audit_writable, "audit store not writable")
    check("database_writable", ctx.db_writable, "database not writable")
    # 11. recovery and rollback predicates defined
    check("recovery_predicate_defined", bool(plan.recovery_predicate), "no recovery predicate")
    check("rollback_defined", len(plan.rollback) > 0, "no captured rollback procedure")
    return r


def executable(results: list[PrecheckResult]) -> bool:
    """Fail closed: the plan is executable only if EVERY precheck passed."""
    return bool(results) and all(res.ok for res in results)


def failures(results: list[PrecheckResult]) -> list[str]:
    return [res.name for res in results if not res.ok]


__all__ = ["PrecheckContext", "PrecheckResult", "executable", "failures", "run_prechecks"]
