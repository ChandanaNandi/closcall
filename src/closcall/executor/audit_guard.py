"""Audit-write guard (Bible §13.3, §10 'audit unavailable: no state mutation'; Gate 11 work item).

The append-only audit must be durable BEFORE any state change. `guarded_mutation` persists the
audit record first; if that write fails it raises `AuditUnavailable` and the mutation is NEVER
attempted — so a state change can never outrun its audit trail. Both callables are injected, so the
guard is unit-tested without a database or a device.
"""

from __future__ import annotations

from collections.abc import Callable


class AuditUnavailable(RuntimeError):
    """The audit write failed; the guarded state mutation must not proceed."""


def guarded_mutation[T](audit_write: Callable[[], None], mutate: Callable[[], T]) -> T:
    """Write the audit record first; only run `mutate` if the audit write succeeded."""
    try:
        audit_write()
    except Exception as exc:  # audit unavailable -> block the mutation (§10)
        raise AuditUnavailable("audit write failed; state mutation blocked") from exc
    return mutate()


__all__ = ["AuditUnavailable", "guarded_mutation"]
