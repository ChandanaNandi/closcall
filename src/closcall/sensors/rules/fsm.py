"""Operational-state finite-state detector (Bible §11.1, §4.2 classical).

Consumes `oper_state` samples (1.0 = up, 0.0 = down, exactly as persisted in the §9.1 raw-telemetry
`oper_state` rows) and raises when the link's operational state holds `down` past the debounce. This
is the strongest, lowest-latency signal for blunt link failures (admin_shutdown / carrier_loss);
gradual/gray faults that keep oper-state up are covered by the §11.2 statistical detectors.

The FSM is implicit in `Debouncer`: NOMINAL -> (down persists) -> ALARM -> (up seen) -> re-armed.
Thresholds (`persistence`, `cooldown_s`) are validation-tuned then frozen (§10.2); the defaults here
are placeholders, not the frozen values.
"""

from __future__ import annotations

from closcall.sensors.common import Alarm, Debouncer, Sample


class OperStateDetector:
    """Raise when oper-state `down` (value below `down_below`) persists past debounce (§11.1)."""

    def __init__(
        self, *, down_below: float = 0.5, persistence: int = 2, cooldown_s: float = 30.0
    ) -> None:
        self._down_below = down_below
        self._deb = Debouncer(persistence=persistence, cooldown_s=cooldown_s)

    def update(self, sample: Sample) -> Alarm | None:
        crossing = sample.value < self._down_below  # oper-state observed down
        if self._deb.observe(sample.t, crossing):
            return Alarm(sample.t, "oper_state_fsm", "oper-state down persisted")
        return None


__all__ = ["OperStateDetector"]
