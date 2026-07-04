"""Gate 9 §11.1-11.3 detectors: debounce semantics, FSM/EWMA/CUSUM triggers, and event matching.

Pure/offline — no DB, fabric, or Prometheus. Detectors are causal stream transducers, so feeding a
list equals feeding sample-by-sample (online == offline replay), asserted explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence

from closcall.sensors.common import Alarm, Debouncer, Sample, run_stream
from closcall.sensors.evaluator import Event, evaluate
from closcall.sensors.rules.fsm import OperStateDetector
from closcall.sensors.timeseries.statistical import Cusum, RobustEwmaZScore


def _samples(values: Sequence[float], start: float = 0.0, dt: float = 5.0) -> list[Sample]:
    return [Sample(t=start + i * dt, value=v) for i, v in enumerate(values)]


# --- Debouncer (§10.1) ---
def test_debouncer_persistence_requires_consecutive_crossings() -> None:
    d = Debouncer(persistence=3, cooldown_s=0.0)
    assert not d.observe(0.0, True)
    assert not d.observe(1.0, True)
    assert d.observe(2.0, True)  # 3rd consecutive -> raise


def test_debouncer_run_resets_on_non_crossing() -> None:
    d = Debouncer(persistence=2, cooldown_s=0.0)
    assert not d.observe(0.0, True)
    assert not d.observe(1.0, False)  # reset
    assert not d.observe(2.0, True)
    assert d.observe(3.0, True)


def test_debouncer_hysteresis_and_cooldown() -> None:
    d = Debouncer(persistence=1, cooldown_s=100.0)
    assert d.observe(0.0, True)  # first raise
    assert not d.observe(5.0, True)  # still crossing, not re-armed (hysteresis)
    d.observe(10.0, False)  # clears -> re-armed
    assert not d.observe(20.0, True)  # re-armed but within cooldown (20-0 < 100)
    d.observe(25.0, False)
    assert d.observe(150.0, True)  # cooldown elapsed -> raise again


def test_debouncer_rejects_bad_config() -> None:
    for bad in (dict(persistence=0, cooldown_s=1.0), dict(persistence=1, cooldown_s=-1.0)):
        raised = False
        try:
            Debouncer(**bad)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised


# --- Operational-state FSM (§11.1) ---
def test_fsm_raises_on_persisted_down_not_on_blip() -> None:
    det = OperStateDetector(persistence=2, cooldown_s=30.0)
    # single down blip then recovery -> no alarm
    assert run_stream(det, _samples([1, 1, 0, 1, 1])) == []
    det2 = OperStateDetector(persistence=2, cooldown_s=30.0)
    alarms = run_stream(det2, _samples([1, 1, 0, 0, 0]))
    assert len(alarms) == 1
    assert alarms[0].detector == "oper_state_fsm"
    assert alarms[0].raised_at == 15.0  # 2nd consecutive down (index 3, t=15)


# --- Robust EWMA/z-score (§11.2) ---
def test_ewma_z_silent_on_stationary_signal() -> None:
    det = RobustEwmaZScore(z_threshold=4.0, warmup=4, persistence=2)
    vals = [100, 101, 99, 100, 101, 99, 100, 101, 99, 100]
    assert run_stream(det, _samples(vals)) == []


def test_ewma_z_fires_on_sustained_level_shift() -> None:
    det = RobustEwmaZScore(z_threshold=4.0, warmup=4, persistence=2)
    vals = [100, 101, 99, 100, 101, 99, 200, 200, 200, 200]  # jump at index 6
    alarms = run_stream(det, _samples(vals))
    assert len(alarms) >= 1
    assert alarms[0].detector == "robust_ewma_z"
    assert alarms[0].raised_at >= 30.0  # not before the shift


# --- CUSUM (§11.2) ---
def test_cusum_detects_mean_shift_not_flat() -> None:
    flat = Cusum(slack_k=0.5, threshold_h=5.0, warmup=3, persistence=1)
    assert run_stream(flat, _samples([0.0] * 12)) == []
    shift = Cusum(slack_k=0.5, threshold_h=5.0, warmup=3, persistence=1)
    vals = [0.0, 0.0, 0.0, 0.0] + [3.0] * 8  # sustained +3 sigma shift
    alarms = run_stream(shift, _samples(vals))
    assert len(alarms) >= 1
    assert alarms[0].detector == "cusum"


# --- Causality / online==offline replay ---
def test_stream_replay_is_deterministic_and_causal() -> None:
    vals = [100, 101, 99, 100, 200, 200, 200, 200]
    a = run_stream(RobustEwmaZScore(persistence=2), _samples(vals))
    # feed an identical fresh detector sample-by-sample -> identical alarms
    det = RobustEwmaZScore(persistence=2)
    b = [det.update(s) for s in _samples(vals)]
    b_alarms = [x for x in b if x is not None]
    assert a == b_alarms


# --- Event evaluator (§11.3 / §10.1) ---
def test_evaluate_detection_latency_and_horizon() -> None:
    alarms = [Alarm(raised_at=112.0, detector="d", detail="")]
    r = evaluate(alarms, Event(onset_t=100.0), horizon_s=30.0)
    assert r.detected and r.t_detected == 112.0 and r.latency_s == 12.0
    assert r.false_positives == 0


def test_evaluate_pre_onset_alarm_is_false_positive_and_missed() -> None:
    alarms = [Alarm(raised_at=90.0, detector="d", detail="")]  # before onset
    r = evaluate(alarms, Event(onset_t=100.0), horizon_s=30.0)
    assert not r.detected and r.t_detected is None and r.false_positives == 1


def test_evaluate_multiple_in_horizon_collapse_to_one() -> None:
    alarms = [Alarm(105.0, "d", ""), Alarm(110.0, "d", ""), Alarm(140.0, "d", "")]
    r = evaluate(alarms, Event(onset_t=100.0), horizon_s=30.0)
    assert r.detected and r.t_detected == 105.0  # first in-horizon
    assert r.false_positives == 1  # the 140.0 alarm is past the horizon


def test_evaluate_healthy_incident_counts_all_alarms_as_fp() -> None:
    alarms = [Alarm(10.0, "d", ""), Alarm(20.0, "d", "")]
    r = evaluate(alarms, None, horizon_s=30.0)
    assert not r.detected and r.false_positives == 2
