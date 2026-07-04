"""§9.4 dataset manifest (Contracts §9.4, Bible §2.10 provenance).

A dataset manifest pins everything needed to reproduce and audit a dataset: content hashes, source
run ids, split protocol + manifest hash, topology/config hashes, code/dependency/image revisions,
seeds, exclusions, and the creation command. `build_manifest` is a pure assembler — it takes the
already-computed hashes/ids and emits a `DatasetManifest` plus a `manifest_hash` over all fields, so
any drift in any input changes the manifest hash (§16 versioning). Reading real hashes from disk
(the uv.lock, artifact files) is the caller's job; `sha256_file` is a read-only convenience.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REQUIRED_NONEMPTY = (
    "dataset_kind",
    "split_protocol",
    "split_manifest_hash",
    "topology_hash",
    "config_hash",
    "feature_schema_hash",
    "code_revision",
    "dependency_lock_hash",
    "creation_command",
)


@dataclass(frozen=True)
class DatasetManifest:
    dataset_kind: str
    source_run_ids: list[str]
    split_protocol: str
    split_manifest_hash: str
    topology_hash: str
    config_hash: str  # hash of lab/fabric.yaml
    feature_schema_hash: str
    graph_schema_hash: str
    code_revision: str
    dependency_lock_hash: str  # hash of uv.lock
    image_digests: dict[str, str]
    master_seed: int
    seeds: dict[str, int]
    exclusions: list[str]  # quarantined/excluded incident ids or reasons
    creation_command: str
    content_hashes: dict[str, str]  # artifact uri -> sha256
    manifest_hash: str = field(default="")


def sha256_file(path: str | Path) -> str:
    """Read-only content hash of a file (for content_hashes / dependency_lock_hash)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(
    *,
    dataset_kind: str,
    source_run_ids: list[str],
    split_protocol: str,
    split_manifest_hash: str,
    topology_hash: str,
    config_hash: str,
    feature_schema_hash: str,
    graph_schema_hash: str,
    code_revision: str,
    dependency_lock_hash: str,
    image_digests: dict[str, str],
    master_seed: int,
    seeds: dict[str, int],
    exclusions: list[str],
    creation_command: str,
    content_hashes: dict[str, str],
) -> DatasetManifest:
    """Assemble a §9.4 manifest and hash all fields (raises on a missing required field)."""
    m = DatasetManifest(
        dataset_kind=dataset_kind,
        source_run_ids=source_run_ids,
        split_protocol=split_protocol,
        split_manifest_hash=split_manifest_hash,
        topology_hash=topology_hash,
        config_hash=config_hash,
        feature_schema_hash=feature_schema_hash,
        graph_schema_hash=graph_schema_hash,
        code_revision=code_revision,
        dependency_lock_hash=dependency_lock_hash,
        image_digests=image_digests,
        master_seed=master_seed,
        seeds=seeds,
        exclusions=exclusions,
        creation_command=creation_command,
        content_hashes=content_hashes,
    )
    body = asdict(m)
    del body["manifest_hash"]
    missing = [k for k in REQUIRED_NONEMPTY if not body.get(k)]
    if missing:
        raise ValueError(f"§9.4 manifest missing required fields: {missing}")
    if not source_run_ids:
        raise ValueError("§9.4 manifest requires at least one source run id")
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=list).encode()).hexdigest()
    # frozen dataclass -> rebuild with the computed hash
    return DatasetManifest(**{**body, "manifest_hash": digest})


__all__ = ["DatasetManifest", "build_manifest", "sha256_file"]
