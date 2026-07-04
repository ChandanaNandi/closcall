"""§9.1 raw-telemetry capture: schema conformance + faithful value mapping (no live Prometheus)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pyarrow.parquet as pq

from closcall.datasets.schemas import RAW_TELEMETRY_COLUMNS
from closcall.datasets.telemetry_window import COUNTERS, OPER_METRIC, capture_window


def _fake_fetch(metric, node, iface, start, end):  # type: ignore[no-untyped-def]
    # two counter samples per metric; oper flips up->down across the window
    if metric == OPER_METRIC:
        return [
            {"labels": {"oper_state": "up"}, "values": [[start, "1"]]},
            {"labels": {"oper_state": "down"}, "values": [[end, "1"]]},
        ]
    return [{"labels": {}, "values": [[start, "10"], [end, "20"]]}]


def test_capture_window_conforms_and_maps(tmp_path):  # type: ignore[no-untyped-def]
    t0 = datetime(2026, 7, 4, 6, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 7, 4, 6, 0, 25, tzinfo=UTC)
    res = capture_window(
        node="leaf1",
        iface_srl="ethernet-1/1",
        window_start=t0,
        window_end=t1,
        campaign_key="test-campaign",
        topology_hash="deadbeef",
        incident_id="abc123",
        out_root=tmp_path,
        fetch=_fake_fetch,
    )

    # 6 counters x 2 samples + oper (up + down) = 14 rows
    assert res.n_rows == len(COUNTERS) * 2 + 2
    assert res.path.exists()
    assert res.sha256 == hashlib.sha256(res.path.read_bytes()).hexdigest()
    assert res.byte_size == len(res.path.read_bytes())

    # the file's own schema is the frozen contract (dir names add Hive partition keys on read)
    assert tuple(pq.ParquetFile(res.path).schema_arrow.names) == RAW_TELEMETRY_COLUMNS

    rows = pq.ParquetFile(res.path).read().to_pylist()
    opers = {r["quality_flags"]: r["value"] for r in rows if r["metric"] == "oper_state"}
    assert opers == {"oper=up": 1.0, "oper=down": 0.0}  # down mapped to 0.0 (link down)
    counters = [r for r in rows if r["is_counter"]]
    assert {r["value"] for r in counters} == {10.0, 20.0}
    assert all(r["topology_hash"] == "deadbeef" for r in rows)

    # partition layout: campaign/topo/date dirs, incident in filename (§9.1)
    assert res.path.name == "incident-abc123.parquet"
    assert "campaign=test-campaign" in str(res.path)
    assert "topo=deadbeef" in str(res.path)
