"""§9.2 causal-feature builder: rate math, causality guard, missingness, leakage-free schema.

Pure/offline — synthetic RawSamples plus one Parquet round-trip in tmp_path. No DB or fabric.
"""

from __future__ import annotations

from datetime import UTC, datetime

from closcall.datasets.features import (
    FeatureMeta,
    RawSample,
    build_feature_row,
    causal_features,
    preprocessor_hash,
)
from closcall.datasets.schemas import CAUSAL_FEATURE_COLUMNS, FORBIDDEN_FEATURE_COLUMNS
from closcall.datasets.telemetry_window import capture_window, read_window_samples


def _counter(metric: str, t0: float, v0: float, t1: float, v1: float) -> list[RawSample]:
    return [RawSample(t0, metric, v0), RawSample(t1, metric, v1)]


def test_rates_and_util_normalization() -> None:
    # in_octets rises 6.25e9 bytes over 10s -> 8 * 625MB/s = 5 Gbps -> util 0.5 of the 10 Gbps link
    samples = (
        _counter("in_octets", 0, 0, 10, 6_250_000_000)
        + _counter("out_octets", 0, 0, 10, 0)
        + _counter("in_error_packets", 0, 0, 10, 100)  # 10/s
        + _counter("out_error_packets", 0, 0, 10, 0)
        + _counter("in_discarded_packets", 0, 0, 10, 20)  # 2/s
        + _counter("out_discarded_packets", 0, 0, 10, 0)
        + [RawSample(10, "oper_state", 1.0)]
    )
    f = causal_features(samples, as_of_at=10.0, w_seconds=10.0)
    assert abs(f["util_ratio"] - 0.5) < 1e-9
    assert abs(f["error_rate"] - 10.0) < 1e-9
    assert abs(f["discard_rate"] - 2.0) < 1e-9
    assert f["missingness_mask"] == 0  # all four channels present


def test_causality_future_samples_excluded() -> None:
    # a huge error spike AFTER as_of_at must not affect the features (never read the future)
    base = _counter("in_error_packets", 0, 0, 10, 0) + _counter("out_error_packets", 0, 0, 10, 0)
    leaked = [*base, RawSample(20, "in_error_packets", 1_000_000)]
    f_base = causal_features(base, as_of_at=10.0, w_seconds=10.0)
    f_leaked = causal_features(leaked, as_of_at=10.0, w_seconds=10.0)
    assert f_base == f_leaked


def test_missingness_mask_flags_absent_channels() -> None:
    # only oper-state present -> util(bit0)+error(bit1)+discard(bit2) missing = 0b0111 = 7
    f = causal_features([RawSample(10, "oper_state", 0.0)], as_of_at=10.0, w_seconds=10.0)
    assert f["missingness_mask"] == 0b0111


def test_build_row_is_schema_exact_and_leakage_free() -> None:
    meta = FeatureMeta(
        example_id="ex1",
        split="train",
        incident_runtime_id="inc1",
        node="leaf1",
        interface="ethernet-1/1",
        window_start=0.0,
        window_end=10.0,
        as_of_at=10.0,
    )
    samples = _counter("in_octets", 0, 0, 10, 1000) + _counter("out_octets", 0, 0, 10, 500)
    row = build_feature_row(meta, samples)
    assert set(row) == set(CAUSAL_FEATURE_COLUMNS)  # exact frozen column set
    assert not (set(row) & FORBIDDEN_FEATURE_COLUMNS)  # no leakage columns
    assert row["feature_schema_hash"] and row["preprocessor_hash"]
    assert preprocessor_hash(10.0) == row["preprocessor_hash"]  # deterministic


def test_parquet_roundtrip_into_features(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # write a real §9.1 window via the capture path (fake fetch), then read + featurize it
    def fake_fetch(metric, node, iface, start, end):  # type: ignore[no-untyped-def]
        from closcall.datasets.telemetry_window import OPER_METRIC

        if metric == OPER_METRIC:
            return [{"labels": {"oper_state": "up"}, "values": [[start, "1"]]}]
        return [{"labels": {}, "values": [[start, "0"], [end, "1000"]]}]

    t0 = datetime(2026, 7, 4, 6, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 7, 4, 6, 0, 10, tzinfo=UTC)
    res = capture_window(
        node="leaf1",
        iface_srl="ethernet-1/1",
        window_start=t0,
        window_end=t1,
        campaign_key="c",
        topology_hash="h",
        incident_id="i1",
        out_root=tmp_path,
        fetch=fake_fetch,
    )
    samples = read_window_samples(res.path)
    assert samples  # non-empty
    f = causal_features(samples, as_of_at=t1.timestamp(), w_seconds=10.0)
    assert f["missingness_mask"] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
    assert f["util_ratio"] >= 0.0
