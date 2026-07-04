"""§13.3 rollback state machine + audit-write guard. Pure/offline."""

from __future__ import annotations

import pytest

from closcall.executor.audit_guard import AuditUnavailable, guarded_mutation
from closcall.executor.plan import Action
from closcall.executor.rollback import HALTED, NOT_NEEDED, ROLLED_BACK, rollback


def _acts(n: int) -> list[Action]:
    return [
        Action("set_admin_state", "leaf1", f"ethernet-1/{i}", "disable") for i in range(1, n + 1)
    ]


class Ok:
    def __init__(self) -> None:
        self.applied: list[str] = []

    def apply(self, action: Action) -> None:
        self.applied.append(action.interface)

    def verify(self, action: Action) -> bool:
        return True


class VerifyFailsOn:
    def __init__(self, fail_iface: str) -> None:
        self.fail_iface, self.applied = fail_iface, []  # type: ignore[var-annotated]

    def apply(self, action: Action) -> None:
        self.applied.append(action.interface)

    def verify(self, action: Action) -> bool:
        return action.interface != self.fail_iface


class Raises:
    def apply(self, action: Action) -> None:
        raise RuntimeError("device unreachable")

    def verify(self, action: Action) -> bool:
        return True


# --- rollback ---
def test_rollback_reverses_completed_steps_in_order() -> None:
    acts = _acts(3)
    dev = Ok()
    out = rollback(3, acts, dev, preconditions_hold=lambda: True)
    assert out.status == ROLLED_BACK and out.steps_reverted == 3
    assert dev.applied == ["ethernet-1/3", "ethernet-1/2", "ethernet-1/1"]  # reverse order


def test_rollback_only_reverses_completed_prefix() -> None:
    dev = Ok()
    out = rollback(1, _acts(3), dev, preconditions_hold=lambda: True)  # only 1 forward step done
    assert out.steps_reverted == 1 and dev.applied == ["ethernet-1/1"]


def test_rollback_halts_when_preconditions_fail() -> None:
    out = rollback(2, _acts(2), Ok(), preconditions_hold=lambda: False)
    assert out.status == HALTED and out.steps_reverted == 0 and out.reason


def test_rollback_halts_and_stays_visible_on_failed_readback() -> None:
    out = rollback(2, _acts(2), VerifyFailsOn("ethernet-1/2"), preconditions_hold=lambda: True)
    # reverse order reverts /2 first, which fails read-back -> halt immediately, operator required
    assert out.status == HALTED and out.steps_reverted == 0 and "read-back" in (out.reason or "")


def test_rollback_halts_on_raising_actuator() -> None:
    out = rollback(1, _acts(1), Raises(), preconditions_hold=lambda: True)
    assert out.status == HALTED and "raised" in (out.reason or "")


def test_rollback_not_needed_when_nothing_completed() -> None:
    assert rollback(0, _acts(2), Ok(), preconditions_hold=lambda: True).status == NOT_NEEDED


# --- audit guard ---
def test_mutation_runs_only_after_successful_audit() -> None:
    order: list[str] = []
    result = guarded_mutation(
        lambda: order.append("audit"), lambda: order.append("mutate") or "done"
    )
    assert order == ["audit", "mutate"] and result == "done"


def test_audit_failure_blocks_mutation() -> None:
    mutated = []

    def failing_audit() -> None:
        raise OSError("db down")

    with pytest.raises(AuditUnavailable):
        guarded_mutation(failing_audit, lambda: mutated.append(1))
    assert mutated == []  # mutation NEVER ran (§10: audit unavailable -> no state change)
