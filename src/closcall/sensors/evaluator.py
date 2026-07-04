"""Causal event evaluator (Bible §11.3, §10.1, §10.3).

Matches a detector's raised alarms against a known injected event and derives the per-incident
outcome: whether it was detected, `t_detected` (first persisted crossing after observed onset),
detection latency, misses, and false positives. This is the pure matching *mechanism*; the
tolerances/thresholds it consumes are validation-tuned then frozen (§10.2) — never fit on TEST.

Conventions (§10.3):
- `t_detected` is the earliest alarm within the detection horizon [onset, onset + horizon_s].
- Alarms strictly before onset are pre-onset false positives.
- Alarms after the horizon are late/spurious false positives (the event's detection already resolved
  or was missed).
- A healthy/hard-negative incident carries no event: every alarm is a false positive.
- Multiple alarms inside the horizon collapse to the single detection (one independent incident).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from closcall.sensors.common import Alarm


@dataclass(frozen=True)
class Event:
    """A ground-truth injected fault onset (evaluator-only; joined at scoring, never a feature)."""

    onset_t: float


@dataclass(frozen=True)
class MatchResult:
    detected: bool
    t_detected: float | None
    latency_s: float | None
    false_positives: int


def evaluate(alarms: Iterable[Alarm], event: Event | None, *, horizon_s: float) -> MatchResult:
    """Match alarms to `event` (or None for a healthy incident) within a detection horizon."""
    if horizon_s <= 0:
        raise ValueError("horizon_s must be > 0")
    ordered = sorted(alarms, key=lambda a: a.raised_at)

    if event is None:  # healthy / hard-negative: any alarm is a false positive
        return MatchResult(
            detected=False, t_detected=None, latency_s=None, false_positives=len(ordered)
        )

    lo, hi = event.onset_t, event.onset_t + horizon_s
    t_detected: float | None = None
    false_positives = 0
    for a in ordered:
        if lo <= a.raised_at <= hi:
            if t_detected is None:
                t_detected = a.raised_at  # first in-horizon alarm is the detection
            # subsequent in-horizon alarms collapse into the same event (not counted)
        else:
            false_positives += 1  # pre-onset or post-horizon
    detected = t_detected is not None
    latency = (t_detected - event.onset_t) if t_detected is not None else None
    return MatchResult(
        detected=detected,
        t_detected=t_detected,
        latency_s=latency,
        false_positives=false_positives,
    )


__all__ = ["Event", "MatchResult", "evaluate"]
