"""Window->detector adapter: stream shaping + the end-to-end bridge (window -> detector -> alarm).

Pure/offline. Proves the previously-disconnected pieces connect: a §9.1 window drives a detector.
"""

from __future__ import annotations

from closcall.datasets.features import RawSample
from closcall.sensors.adapters import detector_streams, oper_state_stream, rate_stream
from closcall.sensors.common import run_stream
from closcall.sensors.rules.fsm import OperStateDetector
from closcall.sensors.timeseries.statistical import RobustEwmaZScore


def test_oper_state_stream_collapses_down_wins_and_orders() -> None:
    samples = [
        RawSample(10.0, "oper_state", 1.0),  # up
        RawSample(10.0, "oper_state", 0.0),  # down at same t -> down wins
        RawSample(5.0, "oper_state", 1.0),
        RawSample(0.0, "in_octets", 999.0),  # ignored
    ]
    stream = oper_state_stream(samples)
    assert [(s.t, s.value) for s in stream] == [(5.0, 1.0), (10.0, 0.0)]  # ordered, down at t=10


def test_rate_stream_per_step_and_reset_guard() -> None:
    samples = [
        RawSample(0.0, "in_octets", 100.0),
        RawSample(5.0, "in_octets", 600.0),  # +500 / 5s = 100/s
        RawSample(10.0, "in_octets", 100.0),  # counter reset (drop) -> guarded to 0
    ]
    stream = rate_stream(samples, "in_octets")
    assert [(s.t, s.value) for s in stream] == [(5.0, 100.0), (10.0, 0.0)]


def test_detector_streams_has_oper_plus_all_counter_rates() -> None:
    streams = detector_streams([RawSample(0.0, "oper_state", 1.0)])
    assert "oper_state" in streams
    assert "in_octets_rate" in streams and "out_discarded_packets_rate" in streams
    assert len(streams) == 7  # oper + 6 counters


def test_end_to_end_window_drives_fsm_alarm() -> None:
    # a window where oper-state goes down and persists -> the FSM must fire off the adapted stream
    window = [
        RawSample(0.0, "oper_state", 1.0),
        RawSample(5.0, "oper_state", 1.0),
        RawSample(10.0, "oper_state", 0.0),
        RawSample(15.0, "oper_state", 0.0),
        RawSample(20.0, "oper_state", 0.0),
    ]
    stream = detector_streams(window)["oper_state"]
    alarms = run_stream(OperStateDetector(persistence=2, cooldown_s=30.0), stream)
    assert len(alarms) == 1 and alarms[0].raised_at == 15.0


def test_end_to_end_window_drives_ewma_alarm_on_rate_spike() -> None:
    # error-packet counter rises with realistic jitter, then jumps sharply -> rate spikes -> EWMA/z
    # fires off the adapted stream (a perfectly flat baseline gives MAD=0 and is degenerate).
    cumulative = [0.0, 2.0, 3.0, 6.0, 7.0, 11.0]  # jittered deltas -> rates have nonzero variance
    base = [RawSample(float(i * 5), "in_error_packets", v) for i, v in enumerate(cumulative)]
    spike = [
        *base,
        RawSample(30.0, "in_error_packets", 1000.0),  # huge jump
        RawSample(35.0, "in_error_packets", 2000.0),  # sustained
        RawSample(40.0, "in_error_packets", 3000.0),
    ]
    stream = rate_stream(spike, "in_error_packets")
    alarms = run_stream(RobustEwmaZScore(z_threshold=4.0, warmup=3, persistence=2), stream)
    assert len(alarms) >= 1
