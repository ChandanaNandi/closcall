"""Counter transform handling (Bible §9.2).

Interface counters are monotonic gauges that reset (device/counter restart), wrap (fixed-width
overflow), arrive out of order, and have gaps (missed samples / reconnect). This module turns a raw
counter series into per-interval deltas + rates, and never forward-fills across an unbounded gap
(§9.2). Each output sample carries a quality flag so downstream detection can weight or drop it.

Pure functions — the golden parity tests (C05) pin their behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# SR Linux statistics counters are 64-bit unsigned.
COUNTER_MAX = 2**64


class Quality(str, Enum):
    OK = "ok"
    RESET = "reset"  # counter went backwards -> device/counter reset (delta from 0)
    GAP = "gap"  # sample interval exceeds the allowed watermark -> not rate-able
    DUPLICATE = "duplicate"  # same or earlier event time as the previous accepted sample


@dataclass(frozen=True)
class Sample:
    event_time: float  # seconds (device event time)
    value: int


@dataclass(frozen=True)
class Delta:
    start_time: float
    end_time: float
    delta: int
    rate_per_s: float | None  # None when not rate-able (gap/duplicate)
    quality: Quality


def counter_deltas(samples: list[Sample], max_gap_s: float) -> list[Delta]:
    """Convert an ordered-by-arrival counter series into quality-flagged deltas.

    - reset (value < previous): treat the new value as the delta (counter restarted at 0), flag
      RESET; no rate is emitted because the true elapsed count is unknown.
    - wrap is indistinguishable from reset without a max-hint; when the drop is within one counter
      width and a counter_max is given, we could unwrap, but a reset is the safe assumption for a
      software NOS, so we flag RESET and skip the rate rather than fabricate one.
    - gap (dt > max_gap_s): emit the delta but flag GAP and NO rate (never forward-fill, §9.2).
    - duplicate / out-of-order (dt <= 0): flag DUPLICATE, no rate.
    """
    out: list[Delta] = []
    prev: Sample | None = None
    for s in samples:
        if prev is None:
            prev = s
            continue
        dt = s.event_time - prev.event_time
        if dt <= 0:
            out.append(Delta(prev.event_time, s.event_time, 0, None, Quality.DUPLICATE))
            # keep the later value only if it is not strictly older
            if s.event_time == prev.event_time:
                prev = s
            continue
        if s.value < prev.value:
            out.append(Delta(prev.event_time, s.event_time, s.value, None, Quality.RESET))
            prev = s
            continue
        delta = s.value - prev.value
        if dt > max_gap_s:
            out.append(Delta(prev.event_time, s.event_time, delta, None, Quality.GAP))
        else:
            out.append(Delta(prev.event_time, s.event_time, delta, delta / dt, Quality.OK))
        prev = s
    return out


__all__ = ["COUNTER_MAX", "Delta", "Quality", "Sample", "counter_deltas"]
