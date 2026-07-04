"""Adapt §9.1 raw-telemetry windows into detector Sample streams (Bible §11 wiring, §10.3 causal).

The §11 detectors consume a causal scalar stream (`sensors.common.Sample`); the corpus persists §9.1
windows as `datasets.features.RawSample` rows. This module is the bridge:

- `oper_state_stream` collapses the oper-state rows to one 0/1 value per timestamp (down wins under
  staleness overlap) — the input to the operational-state FSM (§11.1);
- `rate_stream` turns a cumulative counter into a per-step per-second rate (counter-reset guarded) —
  the input to the EWMA/CUSUM detectors (§11.2) for gray faults;
- `detector_streams` yields the oper stream plus one rate stream per counter metric.

Strictly causal: every derived point uses only the current and immediately preceding sample, and
order is preserved, so replaying a stream is identical to streaming it live (§10.3).
"""

from __future__ import annotations

from itertools import pairwise

from closcall.datasets.features import RawSample
from closcall.sensors.common import Sample

COUNTER_METRICS = (
    "in_octets",
    "out_octets",
    "in_error_packets",
    "out_error_packets",
    "in_discarded_packets",
    "out_discarded_packets",
)


def oper_state_stream(samples: list[RawSample]) -> list[Sample]:
    """Collapse oper-state rows to one value per timestamp (min == down wins), time-ordered."""
    by_t: dict[float, float] = {}
    for s in samples:
        if s.metric == "oper_state":
            by_t[s.t] = min(by_t.get(s.t, 1.0), s.value)
    return [Sample(t, v) for t, v in sorted(by_t.items())]


def rate_stream(samples: list[RawSample], metric: str) -> list[Sample]:
    """Per-step per-second rate of a cumulative counter (reset-guarded), stamped at the later t."""
    pts = sorted((s for s in samples if s.metric == metric), key=lambda s: s.t)
    out: list[Sample] = []
    for prev, cur in pairwise(pts):
        dt = cur.t - prev.t
        if dt <= 0:
            continue
        dv = cur.value - prev.value
        if dv < 0:  # counter reset within the window -> no observed increase
            dv = 0.0
        out.append(Sample(cur.t, dv / dt))
    return out


def detector_streams(samples: list[RawSample]) -> dict[str, list[Sample]]:
    """All detector-ready streams from one §9.1 window: oper-state + per-counter rates."""
    streams = {"oper_state": oper_state_stream(samples)}
    for m in COUNTER_METRICS:
        streams[f"{m}_rate"] = rate_stream(samples, m)
    return streams


__all__ = ["COUNTER_METRICS", "detector_streams", "oper_state_stream", "rate_stream"]
