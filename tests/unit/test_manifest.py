"""§9.4 dataset manifest builder: field completeness, determinism, drift-sensitivity.

Pure/offline — synthetic inputs plus one read-only file hash in tmp_path.
"""

from __future__ import annotations

import pytest

from closcall.datasets.manifest import build_manifest, sha256_file


def _kwargs() -> dict:  # type: ignore[type-arg]
    return dict(
        dataset_kind="gate9-corpus",
        source_run_ids=["campaign-v2"],
        split_protocol="location-inductive",
        split_manifest_hash="s" * 64,
        topology_hash="t" * 64,
        config_hash="c" * 64,
        feature_schema_hash="f" * 64,
        graph_schema_hash="g" * 64,
        code_revision="abc123",
        dependency_lock_hash="d" * 64,
        image_digests={"srlinux": "sha256:deadbeef"},
        master_seed=1337,
        seeds={"traffic": 1, "fault": 1},
        exclusions=["inc-quarantined-1"],
        creation_command="make corpus",
        content_hashes={"data/x.parquet": "h" * 64},
    )


def test_manifest_has_all_required_provenance_fields() -> None:
    m = build_manifest(**_kwargs())
    for field_name in (
        "content_hashes",
        "source_run_ids",
        "split_protocol",
        "topology_hash",
        "config_hash",
        "code_revision",
        "dependency_lock_hash",
        "image_digests",
        "master_seed",
        "seeds",
        "exclusions",
        "creation_command",
    ):
        assert getattr(m, field_name)
    assert len(m.manifest_hash) == 64


def test_manifest_hash_is_deterministic() -> None:
    assert build_manifest(**_kwargs()).manifest_hash == build_manifest(**_kwargs()).manifest_hash


def test_any_field_change_changes_the_hash() -> None:
    base = build_manifest(**_kwargs()).manifest_hash
    drifted = build_manifest(**{**_kwargs(), "master_seed": 42}).manifest_hash
    assert base != drifted


def test_missing_required_field_raises() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        build_manifest(**{**_kwargs(), "topology_hash": ""})


def test_empty_source_run_ids_raises() -> None:
    with pytest.raises(ValueError, match="source run id"):
        build_manifest(**{**_kwargs(), "source_run_ids": []})


def test_sha256_file_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    import hashlib

    assert sha256_file(p) == hashlib.sha256(b"hello").hexdigest()
