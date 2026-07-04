"""Tests for syslog normalization (Bible §9.1)."""

from closcall.telemetry.syslog import normalize


def test_rfc3164_parsed() -> None:
    raw = "<28>Jul  3 19:41:05 leaf1 sr_device_mgr: Interface ethernet-1/1 is down"
    e = normalize(raw, received_at=1000.0)
    assert e.node == "leaf1"
    assert e.facility == 3  # 28 // 8
    assert e.severity == "warning"  # 28 % 8 == 4
    assert e.tag == "sr_device_mgr"
    assert e.event_time == "Jul  3 19:41:05"
    assert e.received_at == 1000.0
    assert e.raw == raw  # raw always preserved


def test_severity_mapping() -> None:
    # <11> -> facility 1, severity index 3 == error
    assert normalize("<11>Jul  3 19:41:05 spine1 bgp_mgr: peer down", 1.0).severity == "error"


def test_unparseable_keeps_raw() -> None:
    e = normalize("garbage not-a-syslog line", received_at=5.0)
    assert e.raw == "garbage not-a-syslog line"
    assert e.node is None and e.severity is None
    assert e.received_at == 5.0


def test_tag_with_pid() -> None:
    e = normalize("<30>Jul  3 19:41:05 leaf2 app[1234]: started", 1.0)
    assert e.tag == "app"
