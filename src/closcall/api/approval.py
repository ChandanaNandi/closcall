"""UI-side approval guard (Gate 14) — the no-side-door property, enforced in code.

The browser approve action must NEVER become a way to mutate a device without a valid approval bound
to the exact immutable plan digest. This guard is the UI-layer check; the isolated executor's
precheck enforces the SAME predicate server-side (both call the shared `executor.binding` gate), so
the property holds in depth. The critical test (test_ui) tries to open the side door — a tampered or
mismatched digest, or no approval — and asserts this refuses and no execution runs.
"""

from __future__ import annotations

from closcall.executor.binding import approval_authorizes_plan


class SideDoorRejected(Exception):
    """Raised when execution runs without a valid approval bound to the exact plan digest."""


def guard_execution(*, decision: str | None, approval_digest: str | None, plan_digest: str) -> None:
    """Refuse unless an approve decision binds EXACTLY this plan digest. Raises SideDoorRejected."""
    if (
        decision is None
        or approval_digest is None
        or not approval_authorizes_plan(
            decision=decision, approval_digest=approval_digest, plan_digest=plan_digest
        )
    ):
        raise SideDoorRejected("execution refused: no approval bound to this exact plan digest")


__all__ = ["SideDoorRejected", "guard_execution"]
