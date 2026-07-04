"""Gate 8 resumable, checkpointed corpus runner (Bible §8.3, §10; Gate 8 work/exit).

Accumulates labeled incidents toward pre-registered per-stratum targets. RESUMABLE: it counts valid
(settled) incidents already in `evaluation.fault_injections` per stratum and collects only what is
missing, so it can be run in as many short chunks as you like (`make corpus BATCH=40`) until the
targets are met — no unattended overnight run required.

Per incident (checkpointed — committed immediately so interruption is safe):
  write ground truth BEFORE mutation -> inject (Gate-5) -> wait causal window -> verify OBSERVED
  onset (quarantine, never label, if absent §8.3) -> record label + hash the window artifact ->
  clear -> verify lab state clean between incidents (§8.3) -> commit.

Safe parallelism = 1 shard (measured, R13: one 2s4l lab fits the 16 GiB VM). Disk-guarded (R10).

Usage: BATCH=<n> TARGET=<total> uv run python scripts/corpus_run.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.chaos.faults import Fault  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    Artifact,
    EvalCampaign,
    EvalFaultInjection,
    EvalGroundTruthLabel,
)

CORPUS_MIN_FREE_GIB = 60
WINDOW_BLUNT_S = 25  # blunt faults (down/flap): short window
WINDOW_GRAY_S = 40  # congestion/impaired: longer window (still measurement floor, not convergence)
CAMPAIGN_KEY = "gate8-full-corpus"

# Pre-registered stratum matrix: fault_class x leaf. Split is location-inductive (leaf1/2 train,
# leaf3/4 test). Interface varies within a cell by incident index for within-stratum diversity.
CLASSES = (
    "admin_shutdown",
    "carrier_loss",
    "intermittent_link",
    "rate_limited_uplink",
    "impaired_link",
    "healthy_control",
)
LEAVES = ("leaf1", "leaf2", "leaf3", "leaf4")
UPLINKS = (("e1-1", "ethernet-1/1"), ("e1-2", "ethernet-1/2"))


def split_of(leaf: str) -> str:
    return "train" if leaf in ("leaf1", "leaf2") else "test"


def gray(fc: str) -> bool:
    return fc in ("rate_limited_uplink", "impaired_link")


def clean_between(node: str, netdev: str) -> bool:
    """Verify lab state clean between incidents (§8.3): interface up, no residual qdisc."""
    up = subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "root",
            f"clab-closcall-2s4l-{node}",
            "sr_cli",
            f"info from state interface {netdev.replace('e1-', 'ethernet-1/')} oper-state",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    qd = subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "root",
            f"clab-closcall-2s4l-{node}",
            "sh",
            "-c",
            f"tc qdisc show dev {netdev} | grep -cE 'netem|tbf' || true",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    return "up" in up and qd in ("0", "")


def oper_state(node: str, iface_srl: str) -> str:
    out = subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "root",
            f"clab-closcall-2s4l-{node}",
            "sr_cli",
            f"info from state interface {iface_srl} oper-state",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    return "down" if "down" in out else ("up" if "up" in out else "unknown")


async def counts_by_stratum(Session) -> dict[tuple[str, str], int]:  # type: ignore[no-untyped-def]
    async with Session() as s:
        rows = (
            await s.execute(
                select(EvalFaultInjection.fault_class, EvalFaultInjection.shard_key, func.count())
                .where(EvalFaultInjection.status == "settled")
                .group_by(EvalFaultInjection.fault_class, EvalFaultInjection.shard_key)
            )
        ).all()
    # key by (class, leaf) — shard_key stores the leaf here
    return {(fc, leaf): n for fc, leaf, n in rows}


async def campaign_id(Session) -> uuid.UUID:  # type: ignore[no-untyped-def]
    async with Session() as s:
        cid = (
            await s.execute(
                select(EvalCampaign.id).where(EvalCampaign.campaign_key == CAMPAIGN_KEY)
            )
        ).scalar_one_or_none()
        if cid is None:
            c = EvalCampaign(
                campaign_key=CAMPAIGN_KEY, code_revision="gate8", master_seed=1337, status="running"
            )
            s.add(c)
            await s.commit()
            cid = c.id
    return cid


async def collect_one(Session, cid, fc, leaf, netdev, iface, split, seed) -> str:  # type: ignore[no-untyped-def]
    fault = Fault(fault_class=fc, node=leaf, iface_netdev=netdev, iface_srl=iface)
    target = {"node": leaf, "interface": iface, "link": f"{leaf}:{iface}"}
    onset_time = datetime.now(UTC)
    async with Session() as s:
        inj = EvalFaultInjection(
            campaign_id=cid,
            fault_class=fc,
            shard_key=leaf,
            target_json=target,
            parameters_json={"split": split},
            traffic_seed=seed,
            fault_seed=seed,
            status="injecting",
            simulated=True,
        )
        s.add(inj)
        await s.commit()
        inj_id = inj.id

    fault.apply()
    time.sleep(WINDOW_GRAY_S if gray(fc) else WINDOW_BLUNT_S)
    onset_ok = fault.verify_onset() if fc != "healthy_control" else True
    feature = oper_state(leaf, iface)
    fault.clear()
    time.sleep(3)
    lab_clean = clean_between(leaf, netdev)

    status = "settled" if (onset_ok and lab_clean) else "quarantined"
    label = {
        "fault_class": fc,
        "target": target,
        "onset_at": onset_time.isoformat(),
        "split": split,
        "observed_feature": feature,
    }
    blob = json.dumps(label, sort_keys=True).encode()
    async with Session() as s:
        inj = await s.get(EvalFaultInjection, inj_id)
        assert inj is not None
        inj.status = status
        inj.device_observed_at = onset_time
        if status == "settled":
            s.add(
                EvalGroundTruthLabel(
                    fault_injection_id=inj_id,
                    label_json=label,
                    label_hash=hashlib.sha256(blob).hexdigest(),
                )
            )
            s.add(
                Artifact(
                    kind="label_window",
                    uri=f"mem://{inj_id}",
                    sha256=hashlib.sha256(blob).hexdigest(),
                    byte_size=len(blob),
                    media_type="application/json",
                )
            )
        await s.commit()
    return status


async def run() -> int:
    batch = int(os.environ.get("BATCH", "40"))
    target_total = int(os.environ.get("TARGET", "300"))
    cells = [(c, leaf) for c in CLASSES for leaf in LEAVES]
    per_cell = -(-target_total // len(cells))  # ceil

    free = shutil.disk_usage("/").free / (1024**3)
    if free < CORPUS_MIN_FREE_GIB:
        print(f"[HALT] R10 disk gate: {free:.0f} GiB < {CORPUS_MIN_FREE_GIB} — corpus blocked")
        return 1

    Session = make_sessionmaker()
    cid = await campaign_id(Session)
    counts = await counts_by_stratum(Session)
    total = sum(counts.values())
    print(
        f"corpus: {total}/{target_total} valid incidents; per-cell target {per_cell}; batch {batch}"
    )

    collected = quarantined = 0
    idx = total
    while collected < batch and total + collected < target_total:
        # pick the most under-filled cell (deterministic: first below per_cell)
        cell = next((c for c in cells if counts.get(c, 0) < per_cell), None)
        if cell is None:
            break
        fc, leaf = cell
        netdev, iface = UPLINKS[idx % len(UPLINKS)]
        if free < CORPUS_MIN_FREE_GIB:
            print("[HALT] disk floor reached mid-run; stopping safely")
            break
        status = await collect_one(Session, cid, fc, leaf, netdev, iface, split_of(leaf), idx + 1)
        if status == "settled":
            counts[cell] = counts.get(cell, 0) + 1
            collected += 1
        else:
            quarantined += 1
        idx += 1
        free = shutil.disk_usage("/").free / (1024**3)

    total_now = sum((await counts_by_stratum(Session)).values())
    filled = sum(1 for c in cells if counts.get(c, 0) >= per_cell)
    print(f"batch done: +{collected} settled, {quarantined} quarantined")
    print(f"corpus now: {total_now}/{target_total}; strata filled {filled}/{len(cells)}")
    (REPO / "evals" / "reports" / "gate8-corpus-progress.txt").write_text(
        f"corpus {total_now}/{target_total}; strata filled {filled}/{len(cells)}; "
        f"last batch +{collected} settled / {quarantined} quarantined\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
