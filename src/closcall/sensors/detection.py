"""Detection ensemble over one incident window (Bible §11.1-11.3, §10.3, §10.4).

Runs the classical detectors on the adapted streams of a §9.1 window and reduces them to a single
per-incident outcome via the causal event evaluator: the operational-state FSM on the oper stream
(§11.1) plus robust-EWMA/z and CUSUM on each counter-rate stream (§11.2). An incident is DETECTED if
any detector raises within the detection horizon after onset; healthy incidents count any alarm as
a false positive. Thresholds live in `DetectorConfig` and are validation-tuned then frozen (§10.2)
— the defaults are placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass

from closcall.datasets.features import RawSample
from closcall.sensors.adapters import detector_streams
from closcall.sensors.common import Alarm, run_stream
from closcall.sensors.evaluator import Event, MatchResult, evaluate
from closcall.sensors.rules.fsm import OperStateDetector
from closcall.sensors.timeseries.statistical import Cusum, RobustEwmaZScore


@dataclass(frozen=True)
class DetectorConfig:
    fsm_persistence: int = 2
    fsm_cooldown_s: float = 30.0
    ewma_z: float = 4.0
    ewma_persistence: int = 2
    ewma_warmup: int = 4
    cusum_k: float = 0.5
    cusum_h: float = 5.0
    cusum_persistence: int = 1
    horizon_s: float = 60.0


def all_alarms(samples: list[RawSample], cfg: DetectorConfig) -> list[Alarm]:
    """Run the full detector ensemble over the window's adapted streams; alarms time-ordered."""
    streams = detector_streams(samples)
    alarms: list[Alarm] = run_stream(
        OperStateDetector(persistence=cfg.fsm_persistence, cooldown_s=cfg.fsm_cooldown_s),
        streams["oper_state"],
    )
    for channel, stream in streams.items():
        if channel == "oper_state":
            continue
        alarms += run_stream(
            RobustEwmaZScore(
                z_threshold=cfg.ewma_z,
                persistence=cfg.ewma_persistence,
                warmup=cfg.ewma_warmup,
                cooldown_s=cfg.fsm_cooldown_s,
            ),
            stream,
        )
        alarms += run_stream(
            Cusum(
                slack_k=cfg.cusum_k,
                threshold_h=cfg.cusum_h,
                persistence=cfg.cusum_persistence,
                cooldown_s=cfg.fsm_cooldown_s,
            ),
            stream,
        )
    return sorted(alarms, key=lambda a: a.raised_at)


def detect_incident(
    samples: list[RawSample], cfg: DetectorConfig, *, onset_t: float, is_healthy: bool
) -> MatchResult:
    """Reduce the ensemble's alarms to one per-incident detection outcome (§11.3/§10.1)."""
    event = None if is_healthy else Event(onset_t=onset_t)
    return evaluate(all_alarms(samples, cfg), event, horizon_s=cfg.horizon_s)


__all__ = ["DetectorConfig", "all_alarms", "detect_incident"]
