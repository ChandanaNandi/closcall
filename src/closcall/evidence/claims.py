"""§12.2 typed claims + deterministic verifier (Bible §12.2; Gate 10 exit criterion 1).

A claim is a typed proposition about immutable evidence. The verifier executes the claim's predicate
against an immutable `Snapshot`, returning `supported`, `contradicted`, or `insufficient` — no model
in the loop, so narrative prose can only be generated after a claim verifies. This is what makes
"unsupported/contradictory claims cannot be committed" true in code.

The verifier is adversarially strict: evidence must match the claim's subject, metric/event, and
unit and fall inside the claim's causal interval, or the claim is `insufficient` (never spuriously
supported). Cherry-picking is defeated by predicate semantics — a `sustained` claim requires EVERY
in-window sample to satisfy, so one supporting sample cannot carry it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


class Predicate(StrEnum):
    SUSTAINED = "sustained"  # operator holds for EVERY in-window matched sample
    ANY = "any"  # operator holds for at least one matched sample (e.g. a peak/event)


@dataclass(frozen=True)
class Evidence:
    """One immutable typed observation in a snapshot."""

    evidence_id: str
    subject: str  # e.g. "leaf1:ethernet-1/1"
    metric_or_event: str  # e.g. "oper_state", "in_error_rate", "bgp_session_state"
    value: float | str
    unit: str  # e.g. "state", "packets_per_s", "bytes"
    at: float  # event_time (epoch seconds)


@dataclass(frozen=True)
class Snapshot:
    """Immutable evidence bundle captured at `as_of` (no mutation after collect, §12.1)."""

    as_of: float
    records: tuple[Evidence, ...]

    def by_id(self, evidence_id: str) -> Evidence | None:
        return next((r for r in self.records if r.evidence_id == evidence_id), None)


@dataclass(frozen=True)
class Claim:
    """A typed atomic claim (§12.2). `polarity=False` asserts the negation of the predicate."""

    claim_id: str
    predicate_type: Predicate
    subject: str
    metric_or_event: str
    operator: str  # ">", ">=", "<", "<=", "=="
    comparison: float | str
    unit: str
    interval: tuple[float, float]  # causal window [lo, hi]
    polarity: bool
    evidence_ids: tuple[str, ...]


_NUMERIC_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def _satisfies(operator: str, value: float | str, comparison: float | str) -> bool | None:
    """Evaluate one sample; None if the comparison is ill-typed (e.g. unit/type mismatch)."""
    if operator == "==":
        return value == comparison
    if isinstance(value, int | float) and isinstance(comparison, int | float):
        return bool(_NUMERIC_OPS[operator](value, comparison))
    return None  # ordering operator on non-numeric -> ill-typed, cannot support


def verify(claim: Claim, snapshot: Snapshot) -> Verdict:
    """Deterministically verify a claim against an immutable snapshot (§12.2)."""
    if claim.operator not in _NUMERIC_OPS:
        return Verdict.INSUFFICIENT
    lo, hi = claim.interval
    # only referenced evidence that matches subject + metric/event + UNIT and lies in the interval
    matched = [
        r
        for eid in claim.evidence_ids
        if (r := snapshot.by_id(eid)) is not None
        and r.subject == claim.subject
        and r.metric_or_event == claim.metric_or_event
        and r.unit == claim.unit
        and lo <= r.at <= hi
    ]
    if not matched:
        return Verdict.INSUFFICIENT

    results = [_satisfies(claim.operator, r.value, claim.comparison) for r in matched]
    if any(res is None for res in results):
        return Verdict.INSUFFICIENT  # ill-typed comparison (unit/type mismatch) never "supports"

    holds = all(results) if claim.predicate_type is Predicate.SUSTAINED else any(results)
    truth = holds if claim.polarity else not holds
    return Verdict.SUPPORTED if truth else Verdict.CONTRADICTED


def committable(verdict: Verdict) -> bool:
    """Only supported claims may be committed (§12.1 commit); everything else abstains."""
    return verdict is Verdict.SUPPORTED


__all__ = [
    "Claim",
    "Evidence",
    "Predicate",
    "Snapshot",
    "Verdict",
    "committable",
    "verify",
]
