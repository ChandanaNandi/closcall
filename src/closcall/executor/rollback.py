"""§13.3 rollback state machine (Bible §13.3; Gate 11 exit: rollback-failed states remain visible).

Rollback is a SEPARATE state machine from execution. It runs the captured rollback actions for the
COMPLETED forward steps, in reverse, and ONLY while rollback preconditions still hold. Any unsafe
precondition, failed read-back, or raised actuator call stops immediately and returns
`halted_operator_required` with the reason — the ambiguous/failed state stays visible; it is never
silently swallowed. The actuator is injected so the logic is unit-tested without a device.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from closcall.executor.plan import Action

ROLLED_BACK = "rolled_back"
HALTED = "halted_operator_required"
NOT_NEEDED = "not_needed"


class Actuator(Protocol):
    def apply(self, action: Action) -> None: ...
    def verify(self, action: Action) -> bool: ...  # read-back confirms the reverse mutation


@dataclass(frozen=True)
class RollbackOutcome:
    status: str  # ROLLED_BACK | HALTED | NOT_NEEDED
    steps_reverted: int
    reason: str | None = None


def rollback(
    completed_steps: int,
    rollback_actions: list[Action],
    actuator: Actuator,
    *,
    preconditions_hold: Callable[[], bool],
) -> RollbackOutcome:
    """Reverse the first `completed_steps` rollback actions while preconditions hold; else halt."""
    if completed_steps <= 0:
        return RollbackOutcome(NOT_NEEDED, 0, "no completed steps to reverse")

    to_revert = list(reversed(rollback_actions[:completed_steps]))  # completed steps, reverse order
    reverted = 0
    for action in to_revert:
        if not preconditions_hold():  # re-checked before EVERY step (§13.3)
            return RollbackOutcome(HALTED, reverted, "rollback preconditions no longer hold")
        try:
            actuator.apply(action)
        except Exception as exc:  # a raised actuator call is unsafe -> stop, operator required
            return RollbackOutcome(HALTED, reverted, f"rollback step raised: {exc}")
        if not actuator.verify(action):  # read-back failed -> ambiguous, stop and stay visible
            return RollbackOutcome(HALTED, reverted, f"rollback step failed read-back: {action}")
        reverted += 1
    return RollbackOutcome(ROLLED_BACK, reverted)


__all__ = [
    "HALTED",
    "NOT_NEEDED",
    "ROLLED_BACK",
    "Actuator",
    "RollbackOutcome",
    "rollback",
]
