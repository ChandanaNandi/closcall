"""Shared streaming-sensor primitives (Bible §4.2, §11).

A detector is a *causal* stream transducer: samples arrive in nondecreasing-time order, and the
detector may emit at most one Alarm per sample — on the sample that raises it. Because nothing ever
reads ahead, the online path is identical to an offline replay of the same samples (the §10.3 golden
parity property is structural, not tested-in).

`Debouncer` centralizes the §10.1 alarm semantics — persistence (K consecutive crossings before a
raise), cooldown (minimum gap between raises), and clear-hysteresis (a non-crossing sample must be
seen before re-arming) — so FSM/EWMA/CUSUM detectors share identical raise timing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Sample:
    """One causal observation. `t` is epoch seconds; samples are fed in nondecreasing `t` order."""

    t: float
    value: float


@dataclass(frozen=True)
class Alarm:
    """A raised detection. `raised_at` is `t_detected` — the first persisted crossing (§10.3)."""

    raised_at: float
    detector: str
    detail: str


class Detector(Protocol):
    """Causal streaming detector: one sample in, at most one Alarm out (on the raising sample)."""

    def update(self, sample: Sample) -> Alarm | None: ...


def run_stream(det: Detector, samples: Iterable[Sample]) -> list[Alarm]:
    """Feed a whole causal stream; collect alarms. Never reads ahead (online == offline replay)."""
    out: list[Alarm] = []
    for s in samples:
        a = det.update(s)
        if a is not None:
            out.append(a)
    return out


@dataclass
class Debouncer:
    """§10.1 raise timing shared by all detectors: persistence + cooldown + clear-hysteresis."""

    persistence: int  # consecutive crossing samples required before a raise (>= 1)
    cooldown_s: float  # minimum seconds between two raised alarms
    _run: int = field(default=0, init=False)
    _armed: bool = field(default=True, init=False)  # must see a non-crossing before re-arming
    _last_raise: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.persistence < 1:
            raise ValueError("persistence must be >= 1")
        if self.cooldown_s < 0:
            raise ValueError("cooldown_s must be >= 0")

    def observe(self, t: float, crossing: bool) -> bool:
        """Feed one sample's crossing flag; return True on the sample that raises an alarm."""
        if not crossing:
            self._run = 0
            self._armed = True
            return False
        self._run += 1
        if self._run < self.persistence or not self._armed:
            return False
        if self._last_raise is not None and (t - self._last_raise) < self.cooldown_s:
            return False
        self._armed = False
        self._last_raise = t
        return True


__all__ = ["Alarm", "Debouncer", "Detector", "Sample", "run_stream"]
