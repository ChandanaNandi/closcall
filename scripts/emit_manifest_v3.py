"""Emit the v3 under-load dataset manifest (Gate 12.5/13 release anchor; §9.4, §2.10).

Standalone twin of `emit_manifest.py`. That script emits the IMMUTABLE v2 anchor
(`gate9-dataset.json`) and is never touched — its byte-for-byte stability is what anchors v2's
provenance. This script emits a SEPARATE artifact, `gate12_5-dataset-v3.json`, binding the v3 corpus
(`gate8-full-corpus-v3`, under traffic load, fabric-wide capture) and the v3 study outputs.
Two clean lineages, no shared mutable generator (Bible §16: a new benchmark version is a new
artifact; old results remain immutable).

Binds: source run id, split protocol + hash, topology/config/feature/graph schema hashes, code
revision, dependency-lock hash, image digests, seeds, exclusions (quarantines), a content-hash
roll-up of the §9.1 windows + the v3 study reports, and the creation command. Read-mostly (one
idempotent split-manifest upsert). Run: CLOSCALL_DB_PASSWORD=... uv run scripts/emit_manifest_v3.py
"""

from __future__ import annotations

import asyncio
import glob
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.datasets.graph import build_topology_graph, graph_schema_hash  # noqa: E402
from closcall.datasets.manifest import build_manifest, sha256_file  # noqa: E402
from closcall.datasets.schemas import schema_hash  # noqa: E402
from closcall.datasets.splits import IncidentRef, assemble_location_inductive  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    Artifact,
    EvalCampaign,
    EvalFaultInjection,
    EvalSplitManifest,
)
from closcall.domain.fabric import allocate, load_fabric  # noqa: E402

CAMPAIGN_KEY = "gate8-full-corpus-v3"
MANIFEST_NAME = "gate12_5-dataset-v3.json"
# v3 study artifacts the manifest content-binds (the numbers the release reports).
BOUND_REPORTS = (
    "gate12_5-detection-v3.txt",  # detection under load (classical ensemble)
    "localization-v3.txt",  # localization ablation summary (rule vs MLP vs GNN)
    "gate12_5-ablation.txt",  # full feature-ablation headline (v1 vs v2 temporal)
    "gate12_5-localization-v1.txt",
    "gate12_5-localization-v2.txt",
    "gate12_5-localization-cv.txt",  # leave-one-leaf-out CV supplement
)
CREATION_COMMAND = (
    "make corpus (v3, under load, fabric-wide) -> make evaluate-sensors-v3 "
    "-> make evaluate-localization -> uv run python scripts/emit_manifest_v3.py"
)
CONTAINERS = {
    "srlinux": "clab-closcall-2s4l-leaf1",
    "prometheus": "closcall-prometheus",
    "postgres": "closcall-postgres",
    "gnmic": "closcall-gnmic",
}


def git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()


def image_digests() -> dict[str, str]:
    """Resolve pinned image digests (docker inspect works on exited containers too)."""
    out: dict[str, str] = {}
    for name, container in CONTAINERS.items():
        img = subprocess.run(
            ["docker", "inspect", "--format", "{{.Image}}", container],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if img:
            out[name] = img
    return out


def windows_rollup() -> str:
    """Deterministic roll-up hash over the sorted §9.1 window file hashes (content binding)."""
    files = sorted(
        glob.glob(f"{REPO}/data/raw_telemetry/campaign={CAMPAIGN_KEY}/**/*.parquet", recursive=True)
    )
    h = hashlib.sha256()
    for f in files:
        h.update(sha256_file(f).encode())
    return f"{h.hexdigest()}({len(files)} windows)"


async def gather() -> dict:  # type: ignore[type-arg]
    topo = allocate(load_fabric("lab/fabric.yaml"))
    graph = build_topology_graph(topo)
    Session = make_sessionmaker()
    async with Session() as s:
        camp = (
            await s.execute(select(EvalCampaign).where(EvalCampaign.campaign_key == CAMPAIGN_KEY))
        ).scalar_one()
        settled = (
            await s.execute(
                select(
                    EvalFaultInjection.id,
                    EvalFaultInjection.shard_key,
                    EvalFaultInjection.target_json,
                    EvalFaultInjection.traffic_seed,
                ).where(
                    EvalFaultInjection.campaign_id == camp.id,
                    EvalFaultInjection.status == "settled",
                )
            )
        ).all()
        quarantined = (
            (
                await s.execute(
                    select(EvalFaultInjection.id).where(
                        EvalFaultInjection.campaign_id == camp.id,
                        EvalFaultInjection.status == "quarantined",
                    )
                )
            )
            .scalars()
            .all()
        )
        window_arts = (
            await s.execute(select(Artifact.sha256).where(Artifact.kind == "raw_telemetry_window"))
        ).all()

    refs = [
        IncidentRef(
            incident_id=str(i),
            link_key=t["link"],
            leaf=leaf,
            seed_family=seed,
            campaign_batch=CAMPAIGN_KEY,
            onset_t=0.0,
        )
        for i, leaf, t, seed in settled
    ]
    split = assemble_location_inductive(refs)

    reports = {
        name: sha256_file(REPO / "evals" / "reports" / name)
        for name in BOUND_REPORTS
        if (REPO / "evals" / "reports" / name).exists()
    }
    return {
        "master_seed": camp.master_seed,
        "topology_hash": graph.topology_hash,
        "graph_schema_hash": graph_schema_hash(),
        "split_manifest_hash": split.manifest_hash,
        "split_protocol": split.protocol,
        "split_version": split.version,
        "exclusions": [str(q) for q in quarantined],
        "content_hashes": {"corpus_windows_rollup": windows_rollup(), **reports},
        "n_settled": len(settled),
        "n_window_artifacts": len(window_arts),
    }


async def run() -> int:
    g = await gather()
    manifest = build_manifest(
        dataset_kind="gate12_5-corpus-v3",
        source_run_ids=[CAMPAIGN_KEY],
        split_protocol=g["split_protocol"],
        split_manifest_hash=g["split_manifest_hash"],
        topology_hash=g["topology_hash"],
        config_hash=sha256_file(REPO / "lab" / "fabric.yaml"),
        feature_schema_hash=schema_hash(),
        graph_schema_hash=g["graph_schema_hash"],
        code_revision=git_revision(),
        dependency_lock_hash=sha256_file(REPO / "uv.lock"),
        image_digests=image_digests(),
        master_seed=g["master_seed"],
        seeds={"master": g["master_seed"]},
        exclusions=g["exclusions"],
        creation_command=CREATION_COMMAND,
        content_hashes=g["content_hashes"],
    )

    # persist the split-manifest header to the DB (idempotent on protocol+version)
    Session = make_sessionmaker()
    async with Session() as s:
        existing = (
            await s.execute(
                select(EvalSplitManifest).where(
                    EvalSplitManifest.protocol_name == g["split_protocol"],
                    EvalSplitManifest.version == g["split_version"],
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            s.add(
                EvalSplitManifest(
                    protocol_name=g["split_protocol"],
                    version=g["split_version"],
                    manifest_hash=g["split_manifest_hash"],
                )
            )
            await s.commit()

    out = REPO / "artifacts" / "manifests" / MANIFEST_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n")
    print(f"emitted v3 manifest: {out.relative_to(REPO)}")
    print(
        f"  dataset={manifest.dataset_kind} settled={g['n_settled']} "
        f"windows={g['n_window_artifacts']} exclusions={len(manifest.exclusions)}"
    )
    print(f"  manifest_hash={manifest.manifest_hash}")
    print(f"  split={manifest.split_protocol} v{g['split_version']} persisted to split_manifests")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
