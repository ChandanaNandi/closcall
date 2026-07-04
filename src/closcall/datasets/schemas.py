"""Frozen data-contract schemas (Bible §6 events, Contracts §9.1/9.2 Parquet).

These are the versioned, content-hashed schemas the corpus and feature pipelines must conform to.
"Frozen" means the column set + order is pinned by a schema hash; any change is caught by the
schema-freeze test (a deliberate change bumps `SCHEMA_VERSION` and the pinned hash, creating a new
benchmark version per §16). No data is required to define or freeze these — only the contract.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = 1

# Raw telemetry Parquet columns (Contracts §9.1). Four timestamps preserved: event/received/ingested
# plus the query snapshot time recorded per-read elsewhere.
RAW_TELEMETRY_COLUMNS: tuple[str, ...] = (
    "event_time",
    "received_at",
    "ingested_at",
    "topology_hash",
    "node",
    "interface",
    "direction",
    "metric",
    "value",
    "unit",
    "is_counter",
    "quality_flags",
    "source_sequence",
    "schema_version",
)

# Causal feature Parquet columns (Contracts §9.2). Ground truth is NOT here — it is joined only at
# scoring time from evaluator-only artifacts (§9.2). Explicit missingness/age columns per §9.2.
CAUSAL_FEATURE_COLUMNS: tuple[str, ...] = (
    "example_id",
    "split",
    "incident_runtime_id",
    "window_start",
    "window_end",
    "as_of_at",
    "node",
    "interface",
    "util_ratio",
    "error_rate",
    "discard_rate",  # feature columns (extend by ADR + version bump)
    "sample_age_s",
    "missingness_mask",  # explicit age/missingness (§9.2)
    "feature_schema_hash",
    "preprocessor_hash",
)

# Event envelope (Bible §6).
EVENT_ENVELOPE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "event_type",
    "event_time",
    "observed_at",
    "source",
    "trace_id",
    "payload",
)

# Columns that MUST NEVER appear in the causal feature schema (leakage guard, §10.3).
FORBIDDEN_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {
        "t_clear",
        "t_settled",
        "incident_duration",
        "ground_truth",
        "label",
        "scenario_key",
        "fault_class",
        "split_answer",
    }
)


def schema_hash() -> str:
    """Content hash pinning the frozen column sets + version. Any drift changes this."""
    payload = {
        "version": SCHEMA_VERSION,
        "raw_telemetry": RAW_TELEMETRY_COLUMNS,
        "causal_feature": CAUSAL_FEATURE_COLUMNS,
        "event_envelope": EVENT_ENVELOPE_FIELDS,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=list).encode()).hexdigest()


__all__ = [
    "CAUSAL_FEATURE_COLUMNS",
    "EVENT_ENVELOPE_FIELDS",
    "FORBIDDEN_FEATURE_COLUMNS",
    "RAW_TELEMETRY_COLUMNS",
    "SCHEMA_VERSION",
    "schema_hash",
]
