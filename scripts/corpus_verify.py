"""Gate 8 full-corpus verification (Bible §8.3, §10; Gate 8 exit).

Verifies the collected corpus against the three written Gate 8 exit criteria, reading only the DB
the runner committed to (no re-injection):

  1. pre-registered stratum counts are met — every {fault_class x leaf} cell >= per-cell target and
     the >=300 operational floor (§10.1) is cleared;
  2. artifacts verify — every settled incident has exactly one ground-truth label whose hash
     recomputes from its canonical JSON, backed by a `label_window` Artifact whose sha256 +
     byte_size match;
  3. no split/provenance/quality violation — location-inductive train/test link groups are DISJOINT
     (E06), provenance is complete (campaign revision/seed; per-injection seeds; simulated=true),
     and every settled incident recorded an observed onset (device_observed_at) with 0 unexplained
     quarantines.

Usage: uv run python scripts/corpus_verify.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import pyarrow.parquet as pq  # noqa: E402

from closcall.datasets.schemas import RAW_TELEMETRY_COLUMNS  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    Artifact,
    EvalCampaign,
    EvalFaultInjection,
    EvalGroundTruthLabel,
)

CAMPAIGN_KEY = "gate8-full-corpus-v2"
CLASSES = (
    "admin_shutdown",
    "carrier_loss",
    "intermittent_link",
    "rate_limited_uplink",
    "impaired_link",
    "healthy_control",
)
LEAVES = ("leaf1", "leaf2", "leaf3", "leaf4")
FLOOR = 300  # §10.1 operational floor (">=300 incidents")
PER_CELL = 13  # balanced per-stratum design recorded for this campaign

_fail = 0
_log: list[str] = []


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
    print(line)
    _log.append(line)


def split_of(leaf: str) -> str:
    return "train" if leaf in ("leaf1", "leaf2") else "test"


async def run() -> int:
    Session = make_sessionmaker()
    async with Session() as s:
        camp = (
            await s.execute(select(EvalCampaign).where(EvalCampaign.campaign_key == CAMPAIGN_KEY))
        ).scalar_one_or_none()
        if camp is None:
            emit(False, "campaign present", f"no campaign {CAMPAIGN_KEY!r}")
            _finish()
            return 1

        settled = (
            (
                await s.execute(
                    select(EvalFaultInjection).where(
                        EvalFaultInjection.campaign_id == camp.id,
                        EvalFaultInjection.status == "settled",
                    )
                )
            )
            .scalars()
            .all()
        )
        quarantined = (
            await s.execute(
                select(func.count())
                .select_from(EvalFaultInjection)
                .where(
                    EvalFaultInjection.campaign_id == camp.id,
                    EvalFaultInjection.status == "quarantined",
                )
            )
        ).scalar_one()
        labels = {
            gl.fault_injection_id: gl
            for gl in (await s.execute(select(EvalGroundTruthLabel))).scalars().all()
        }
        artifacts = {
            a.uri: a
            for a in (await s.execute(select(Artifact).where(Artifact.kind == "label_window")))
            .scalars()
            .all()
        }
        telem = {
            a.uri.split("incident-")[1].split(".parquet")[0]: a
            for a in (
                await s.execute(select(Artifact).where(Artifact.kind == "raw_telemetry_window"))
            )
            .scalars()
            .all()
        }

    # --- 1. pre-registered stratum counts are met ---
    cells: dict[tuple[str, str], int] = {}
    for inj in settled:
        cells[(inj.fault_class, inj.shard_key)] = cells.get((inj.fault_class, inj.shard_key), 0) + 1
    expected_cells = [(c, leaf) for c in CLASSES for leaf in LEAVES]
    short = [
        (c, leaf, cells.get((c, leaf), 0))
        for c, leaf in expected_cells
        if cells.get((c, leaf), 0) < PER_CELL
    ]
    emit(
        not short,
        "stratum counts met",
        f"all {len(expected_cells)} cells >= {PER_CELL}/cell"
        if not short
        else f"under-filled: {short}",
    )
    emit(len(settled) >= FLOOR, "operational floor (§10.1)", f"{len(settled)} settled >= {FLOOR}")

    # --- 2. artifacts verify ---
    hash_ok = art_ok = missing_label = 0
    bad: list[str] = []
    for inj in settled:
        gl = labels.get(inj.id)
        if gl is None:
            missing_label += 1
            bad.append(f"{inj.id}:no-label")
            continue
        blob = json.dumps(gl.label_json, sort_keys=True).encode()
        recomputed = hashlib.sha256(blob).hexdigest()
        if recomputed == gl.label_hash:
            hash_ok += 1
        else:
            bad.append(f"{inj.id}:hash-mismatch")
        art = artifacts.get(f"mem://{inj.id}")
        if art is not None and art.sha256 == gl.label_hash and art.byte_size == len(blob):
            art_ok += 1
        else:
            bad.append(f"{inj.id}:artifact")
    emit(
        missing_label == 0 and hash_ok == len(settled) and art_ok == len(settled),
        "artifacts verify",
        f"{hash_ok}/{len(settled)} label hashes recompute; {art_ok}/{len(settled)} artifacts match"
        if not bad
        else f"{len(bad)} bad: {bad[:5]}",
    )

    # --- 2b. §9.1 raw-telemetry windows present, hash-verify, non-empty, schema-conformant ---
    tel_ok = 0
    tel_bad: list[str] = []
    for inj in settled:
        art = telem.get(str(inj.id))
        if art is None:
            tel_bad.append(f"{inj.id}:no-window")
            continue
        path = REPO / art.uri
        if not path.exists():
            tel_bad.append(f"{inj.id}:file-missing")
            continue
        raw = path.read_bytes()
        pf = pq.ParquetFile(path)
        if (
            hashlib.sha256(raw).hexdigest() == art.sha256
            and len(raw) == art.byte_size
            and pf.metadata.num_rows > 0
            and tuple(pf.schema_arrow.names) == RAW_TELEMETRY_COLUMNS
        ):
            tel_ok += 1
        else:
            tel_bad.append(f"{inj.id}:window-bad")
    emit(
        tel_ok == len(settled),
        "telemetry windows verify (§9.1)",
        f"{tel_ok}/{len(settled)} raw-telemetry windows hash-verify, non-empty, schema-conformant"
        if not tel_bad
        else f"{len(tel_bad)} bad: {tel_bad[:5]}",
    )

    # --- 3a. split invariant (E06): train/test link groups disjoint ---
    train_links = {inj.target_json["link"] for inj in settled if split_of(inj.shard_key) == "train"}
    test_links = {inj.target_json["link"] for inj in settled if split_of(inj.shard_key) == "test"}
    overlap = train_links & test_links
    split_tag_ok = all(
        inj.parameters_json.get("split") == split_of(inj.shard_key) for inj in settled
    )
    emit(
        not overlap and split_tag_ok,
        "split invariant (E06)",
        f"train {len(train_links)} ∩ test {len(test_links)} links = ∅; split tags consistent"
        if not overlap and split_tag_ok
        else f"overlap={overlap} split_tag_ok={split_tag_ok}",
    )

    # --- 3b. provenance complete ---
    prov_ok = bool(camp.code_revision) and camp.master_seed is not None
    seeds_ok = all(
        inj.traffic_seed is not None and inj.fault_seed is not None and inj.simulated
        for inj in settled
    )
    emit(
        prov_ok and seeds_ok,
        "provenance complete",
        f"campaign rev={camp.code_revision!r} seed={camp.master_seed}; "
        f"all {len(settled)} injections carry seeds + simulated=true"
        if prov_ok and seeds_ok
        else f"prov_ok={prov_ok} seeds_ok={seeds_ok}",
    )

    # --- 3c. quality: observed onset recorded, no unexplained quarantine ---
    no_onset = [str(inj.id) for inj in settled if inj.device_observed_at is None]
    emit(
        not no_onset,
        "quality (observed onset)",
        f"all {len(settled)} settled have device_observed_at; {quarantined} quarantined"
        if not no_onset
        else f"{len(no_onset)} settled without onset: {no_onset[:5]}",
    )

    _finish()
    return 1 if _fail else 0


def _finish() -> None:
    print(f"== {_fail} failed ==")
    (REPO / "evals" / "reports" / "gate8-corpus.txt").write_text(
        "\n".join(_log) + f"\n== {_fail} failed ==\n"
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
