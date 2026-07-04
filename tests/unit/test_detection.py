"""Detection ensemble: blunt fault detected, healthy stays clean, latency reported. Pure/offline."""

from __future__ import annotations

from closcall.datasets.features import RawSample
from closcall.sensors.detection import DetectorConfig, all_alarms, detect_incident


def _oper_down_window() -> list[RawSample]:
    # oper up then persistently down (a blunt link failure), flat counters
    rows: list[RawSample] = []
    for i, oper in enumerate([1.0, 1.0, 0.0, 0.0, 0.0]):
        t = float(i * 5)
        rows.append(RawSample(t, "oper_state", oper))
        rows.append(RawSample(t, "in_octets", float(i * 100)))  # flat-ish, no anomaly
        rows.append(RawSample(t, "out_octets", float(i * 100)))
    return rows


def _healthy_window() -> list[RawSample]:
    rows: list[RawSample] = []
    for i in range(6):
        t = float(i * 5)
        rows.append(RawSample(t, "oper_state", 1.0))  # stays up
        rows.append(RawSample(t, "in_octets", float(i * 100)))  # steady low traffic
        rows.append(RawSample(t, "out_octets", float(i * 100)))
    return rows


def test_blunt_fault_is_detected_with_latency() -> None:
    w = _oper_down_window()
    res = detect_incident(w, DetectorConfig(), onset_t=0.0, is_healthy=False)
    assert res.detected
    assert res.t_detected == 15.0  # 2nd persisted down sample
    assert res.latency_s == 15.0


def test_healthy_window_produces_no_alarm() -> None:
    w = _healthy_window()
    res = detect_incident(w, DetectorConfig(), onset_t=0.0, is_healthy=True)
    assert not res.detected
    assert res.false_positives == 0  # steady healthy signal -> no false positive


def test_all_alarms_time_ordered() -> None:
    alarms = all_alarms(_oper_down_window(), DetectorConfig())
    assert alarms == sorted(alarms, key=lambda a: a.raised_at)
    assert any(a.detector == "oper_state_fsm" for a in alarms)
