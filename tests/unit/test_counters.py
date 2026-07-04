"""Golden tests for counter transforms (Bible §9.2; acceptance C05)."""

from closcall.telemetry.counters import Quality, Sample, counter_deltas


def _s(t: float, v: int) -> Sample:
    return Sample(event_time=t, value=v)


def test_normal_series_rates() -> None:
    d = counter_deltas([_s(0, 100), _s(1, 200), _s(2, 350)], max_gap_s=5)
    assert [x.delta for x in d] == [100, 150]
    assert [x.quality for x in d] == [Quality.OK, Quality.OK]
    assert d[0].rate_per_s == 100.0 and d[1].rate_per_s == 150.0


def test_reset_flagged_no_rate() -> None:
    # counter goes backwards -> reset; delta is the new value, no rate fabricated.
    d = counter_deltas([_s(0, 900), _s(1, 50)], max_gap_s=5)
    assert d[0].quality == Quality.RESET
    assert d[0].delta == 50
    assert d[0].rate_per_s is None


def test_gap_never_forward_fills() -> None:
    # dt exceeds the watermark -> delta kept but flagged GAP with no rate (§9.2: no forward-fill).
    d = counter_deltas([_s(0, 100), _s(60, 700)], max_gap_s=5)
    assert d[0].quality == Quality.GAP
    assert d[0].delta == 600
    assert d[0].rate_per_s is None


def test_duplicate_and_out_of_order() -> None:
    d = counter_deltas([_s(5, 100), _s(5, 100), _s(4, 100)], max_gap_s=5)
    assert all(x.quality == Quality.DUPLICATE for x in d)
    assert all(x.rate_per_s is None for x in d)


def test_cold_start_single_sample_no_output() -> None:
    assert counter_deltas([_s(0, 100)], max_gap_s=5) == []
    assert counter_deltas([], max_gap_s=5) == []


def test_zero_variance_baseline() -> None:
    d = counter_deltas([_s(0, 500), _s(1, 500), _s(2, 500)], max_gap_s=5)
    assert [x.delta for x in d] == [0, 0]
    assert all(x.quality == Quality.OK and x.rate_per_s == 0.0 for x in d)


def test_reset_then_recovers() -> None:
    d = counter_deltas([_s(0, 900), _s(1, 100), _s(2, 300)], max_gap_s=5)
    assert d[0].quality == Quality.RESET
    assert d[1].quality == Quality.OK and d[1].delta == 200
