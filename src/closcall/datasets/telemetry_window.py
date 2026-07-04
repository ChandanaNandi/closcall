"""§9.1 raw-telemetry Parquet capture (Contracts §9.1, C03).

Closes the dataset-contract gap surfaced at Gate 9: the causal-feature/model pipeline (§11) needs
the per-incident telemetry window [t-W, t], but Prometheus retains only 2 h, so the window must be
captured and persisted at collection time. This module range-queries Prometheus for the target
link's counters + operational state over the causal window and writes a §9.1-conformant Parquet
whose columns/order are pinned by the frozen schema (`RAW_TELEMETRY_COLUMNS`).

Faithful, not synthetic: every value is an observed Prometheus sample (generative synthetic
telemetry is canon-rejected, R-log). Fidelity note (C04): all containers share the Docker-VM clock,
so `event_time`/`received_at`/`ingested_at` are near-identical here — `received_at`/`ingested_at`
record the capture read time (documented single-VM limit).
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from closcall.datasets.features import RawSample
from closcall.datasets.schemas import RAW_TELEMETRY_COLUMNS, SCHEMA_VERSION

PROM = "http://127.0.0.1:9090"
STEP_S = 5  # matches Prometheus scrape_interval (5s)
# Two scrape jobs (gnmic, gnmic-self) target the same exporter, so every series is duplicated; pin
# one job to capture each series exactly once (dedup, not a telemetry-config change).
JOB = "gnmic"

_PREFIX = "closcall_if_counters_srl_nokia_interfaces_interface_statistics_"
# prom metric name -> (short metric, direction, unit, is_counter)
COUNTERS: dict[str, tuple[str, str, str, bool]] = {
    f"{_PREFIX}in_octets": ("in_octets", "in", "bytes", True),
    f"{_PREFIX}out_octets": ("out_octets", "out", "bytes", True),
    f"{_PREFIX}in_error_packets": ("in_error_packets", "in", "packets", True),
    f"{_PREFIX}out_error_packets": ("out_error_packets", "out", "packets", True),
    f"{_PREFIX}in_discarded_packets": ("in_discarded_packets", "in", "packets", True),
    f"{_PREFIX}out_discarded_packets": ("out_discarded_packets", "out", "packets", True),
}
OPER_METRIC = "closcall_if_state_srl_nokia_interfaces_interface_oper_state"

# fetch(metric, node, iface, start, end) -> list of {"labels": {...}, "values": [[ts, "val"], ...]}
Fetch = Callable[[str, str, str, float, float], list[dict]]  # type: ignore[type-arg]


@dataclass(frozen=True)
class CaptureResult:
    path: Path
    sha256: str
    byte_size: int
    n_rows: int


def _http_fetch(metric: str, node: str, iface: str, start: float, end: float) -> list[dict]:  # type: ignore[type-arg]
    query = f'{metric}{{source="{node}",interface_name="{iface}",job="{JOB}"}}'
    qs = urllib.parse.urlencode(
        {"query": query, "start": f"{start:.3f}", "end": f"{end:.3f}", "step": f"{STEP_S}s"}
    )
    url = f"{PROM}/api/v1/query_range?{qs}"
    with urllib.request.urlopen(url, timeout=15) as r:
        payload = json.loads(r.read())
    return [{"labels": s["metric"], "values": s["values"]} for s in payload["data"]["result"]]


def capture_window(
    node: str,
    iface_srl: str,
    window_start: datetime,
    window_end: datetime,
    campaign_key: str,
    topology_hash: str,
    incident_id: str,
    out_root: Path,
    fetch: Fetch = _http_fetch,
) -> CaptureResult:
    """Range-query the target telemetry over [window_start, window_end]; persist §9.1 Parquet."""
    read_at = datetime.now(UTC)
    start, end = window_start.timestamp(), window_end.timestamp()
    cols: dict[str, list] = {c: [] for c in RAW_TELEMETRY_COLUMNS}  # type: ignore[type-arg]
    seq = 0

    def add(
        event_time: datetime,
        direction: str,
        metric: str,
        value: float,
        unit: str,
        is_counter: bool,
        flags: str,
    ) -> None:
        nonlocal seq
        cols["event_time"].append(event_time)
        cols["received_at"].append(read_at)
        cols["ingested_at"].append(read_at)
        cols["topology_hash"].append(topology_hash)
        cols["node"].append(node)
        cols["interface"].append(iface_srl)
        cols["direction"].append(direction)
        cols["metric"].append(metric)
        cols["value"].append(value)
        cols["unit"].append(unit)
        cols["is_counter"].append(is_counter)
        cols["quality_flags"].append(flags)
        cols["source_sequence"].append(seq)
        cols["schema_version"].append(SCHEMA_VERSION)
        seq += 1

    for prom_name, (short, direction, unit, is_counter) in COUNTERS.items():
        for series in fetch(prom_name, node, iface_srl, start, end):
            for ts, val in series["values"]:
                add(
                    datetime.fromtimestamp(float(ts), UTC),
                    direction,
                    short,
                    float(val),
                    unit,
                    is_counter,
                    "",
                )

    for series in fetch(OPER_METRIC, node, iface_srl, start, end):
        state = series["labels"].get("oper_state", "unknown")
        numeric = 1.0 if state == "up" else 0.0
        for ts, _val in series["values"]:
            add(
                datetime.fromtimestamp(float(ts), UTC),
                "na",
                "oper_state",
                numeric,
                "state",
                False,
                f"oper={state}",
            )

    schema = pa.schema(
        [
            ("event_time", pa.timestamp("us", tz="UTC")),
            ("received_at", pa.timestamp("us", tz="UTC")),
            ("ingested_at", pa.timestamp("us", tz="UTC")),
            ("topology_hash", pa.string()),
            ("node", pa.string()),
            ("interface", pa.string()),
            ("direction", pa.string()),
            ("metric", pa.string()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("is_counter", pa.bool_()),
            ("quality_flags", pa.string()),
            ("source_sequence", pa.int64()),
            ("schema_version", pa.int64()),
        ]
    )
    table = pa.table({c: cols[c] for c in RAW_TELEMETRY_COLUMNS}, schema=schema)

    # Partition by bounded campaign/topology/date (never incident id alone, §9.1); incident in file.
    part = (
        out_root
        / "raw_telemetry"
        / f"campaign={campaign_key}"
        / f"topo={topology_hash}"
        / f"date={read_at.date().isoformat()}"
    )
    part.mkdir(parents=True, exist_ok=True)
    path = part / f"incident-{incident_id}.parquet"
    pq.write_table(table, path)  # type: ignore[no-untyped-call]

    raw = path.read_bytes()
    return CaptureResult(
        path=path, sha256=hashlib.sha256(raw).hexdigest(), byte_size=len(raw), n_rows=table.num_rows
    )


def read_window_samples(path: Path) -> list[RawSample]:
    """Load a §9.1 raw-telemetry Parquet into RawSamples for the §9.2 feature stage (read-only)."""
    table = pq.ParquetFile(path).read()  # type: ignore[no-untyped-call]
    rows = table.to_pylist()
    return [
        RawSample(t=r["event_time"].timestamp(), metric=r["metric"], value=float(r["value"]))
        for r in rows
    ]


__all__ = ["COUNTERS", "OPER_METRIC", "CaptureResult", "capture_window", "read_window_samples"]
