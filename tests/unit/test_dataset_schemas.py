"""Schema-freeze tests (Contracts §9; Bible §10.3 leakage guard)."""

from closcall.datasets.schemas import (
    CAUSAL_FEATURE_COLUMNS,
    FORBIDDEN_FEATURE_COLUMNS,
    RAW_TELEMETRY_COLUMNS,
    schema_hash,
)

# Pinned frozen hash. A deliberate schema change bumps SCHEMA_VERSION and this value (§16);
# an accidental change breaks this test — that is the point of "frozen".
FROZEN_HASH = "35f6e540b9928d525c4d3d9266e3a5d0a5c0f4c25a6e448ae1811d0d6caaad7a"


def test_schema_is_frozen_at_pinned_hash() -> None:
    assert schema_hash() == FROZEN_HASH, "schema drifted; bump SCHEMA_VERSION + FROZEN_HASH via ADR"


def test_raw_has_four_timestamp_lineage() -> None:
    for col in ("event_time", "received_at", "ingested_at"):
        assert col in RAW_TELEMETRY_COLUMNS


def test_causal_features_have_missingness_and_age() -> None:
    assert "sample_age_s" in CAUSAL_FEATURE_COLUMNS
    assert "missingness_mask" in CAUSAL_FEATURE_COLUMNS


def test_no_leakage_columns_in_features() -> None:
    leaked = FORBIDDEN_FEATURE_COLUMNS & set(CAUSAL_FEATURE_COLUMNS)
    assert not leaked, f"leakage columns present in feature schema: {leaked}"


def test_ground_truth_not_in_features() -> None:
    assert "ground_truth" not in CAUSAL_FEATURE_COLUMNS
    assert "label" not in CAUSAL_FEATURE_COLUMNS
