"""Gate 12.5 corpus runner v3 — collect UNDER LOAD with FABRIC-WIDE capture (Bible §8.1, §8.3, §9).

Fixes the two deferrals that gutted the science: (1) traffic runs during every incident window (so
congestion/gray faults leave device-counter signatures), and (2) telemetry is captured for every
candidate-link endpoint, not just the target (so localization has real multi-link features for the
GNN). New campaign `gate8-full-corpus-v3`; v2 retained. Resumable + disk-guarded like v2.

Per incident: write ground truth -> start background traffic -> inject -> wait causal window ->
capture the target-link window (label) + all fabric-link endpoints (fabric-wide) -> clear -> stop
traffic -> verify lab clean -> commit.
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
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.chaos.faults import Fault  # noqa: E402
from closcall.datasets.graph import build_topology_graph  # noqa: E402
from closcall.datasets.telemetry_window import CaptureResult, capture_window  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import (  # noqa: E402
    Artifact,
    EvalCampaign,
    EvalFaultInjection,
    EvalGroundTruthLabel,
)
from closcall.domain.fabric import allocate, load_fabric  # noqa: E402
from closcall.traffic.generator import TrafficProfile  # noqa: E402
from closcall.traffic.lab import start_background_traffic, stop_traffic  # noqa: E402

CORPUS_MIN_FREE_GIB = int(os.environ.get("MIN_FREE_GIB", "55"))  # R10 floor; env-overridable
WINDOW_BLUNT_S = 25
WINDOW_GRAY_S = 40
CAMPAIGN_KEY = "gate8-full-corpus-v3"
DATA_ROOT = REPO / "data"
TRAFFIC = TrafficProfile(
    name="collective_base",
    pattern="all_to_all",
    streams_per_flow=4,
    target_bitrate_bps=30_000_000,
    duration_s=60,
    seed=1337,
)

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


def topology_hash() -> str:
    return hashlib.sha256((REPO / "lab" / "fabric.yaml").read_bytes()).hexdigest()[:16]


def fabric_link_endpoints() -> list[tuple[str, str, str]]:
    """(device, iface_srl, interface_id) for every fabric-link endpoint — the GNN capture set."""
    graph = build_topology_graph(allocate(load_fabric("lab/fabric.yaml")))
    eps: dict[str, tuple[str, str, str]] = {}
    for link in graph.candidate_links:
        if link.kind != "fabric":
            continue
        for iid in link.endpoints:
            dev, ifc = iid.split(":", 1)
            eps[iid] = (dev, ifc, iid)
    return sorted(eps.values())


def _sr(node: str, args: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-u", "root", f"clab-closcall-2s4l-{node}", "sr_cli", *args.split()],
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


def oper_state(node: str, iface_srl: str) -> str:
    out = _sr(node, f"info from state interface {iface_srl} oper-state")
    return "down" if "down" in out else ("up" if "up" in out else "unknown")


def clean_between(node: str, netdev: str) -> bool:
    up = _sr(node, f"info from state interface {netdev.replace('e1-', 'ethernet-1/')} oper-state")
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


async def counts_by_stratum(Session, cid):  # type: ignore[no-untyped-def]
    async with Session() as s:
        rows = (
            await s.execute(
                select(EvalFaultInjection.fault_class, EvalFaultInjection.shard_key, func.count())
                .where(
                    EvalFaultInjection.status == "settled", EvalFaultInjection.campaign_id == cid
                )
                .group_by(EvalFaultInjection.fault_class, EvalFaultInjection.shard_key)
            )
        ).all()
    return {(fc, leaf): n for fc, leaf, n in rows}


async def campaign_id(Session):  # type: ignore[no-untyped-def]
    async with Session() as s:
        cid = (
            await s.execute(
                select(EvalCampaign.id).where(EvalCampaign.campaign_key == CAMPAIGN_KEY)
            )
        ).scalar_one_or_none()
        if cid is None:
            c = EvalCampaign(
                campaign_key=CAMPAIGN_KEY,
                code_revision="gate12.5",
                master_seed=1337,
                status="running",
            )
            s.add(c)
            await s.commit()
            cid = c.id
    return cid


async def collect_one(Session, cid, topo, endpoints, fc, leaf, netdev, iface, split, seed):  # type: ignore[no-untyped-def]
    fault = Fault(fault_class=fc, node=leaf, iface_netdev=netdev, iface_srl=iface)
    target = {"node": leaf, "interface": iface, "link": f"{leaf}:{iface}"}
    window_s = WINDOW_GRAY_S if gray(fc) else WINDOW_BLUNT_S
    onset_time = datetime.now(UTC)
    async with Session() as s:
        inj = EvalFaultInjection(
            campaign_id=cid,
            fault_class=fc,
            shard_key=leaf,
            target_json=target,
            parameters_json={"split": split, "under_load": True},
            traffic_seed=seed,
            fault_seed=seed,
            status="injecting",
            simulated=True,
        )
        s.add(inj)
        await s.commit()
        inj_id = inj.id

    start_background_traffic(TRAFFIC, duration_s=window_s + 20)  # load for the whole window
    time.sleep(3)  # let flows ramp before the fault
    fault.apply()
    time.sleep(window_s)
    onset_ok = fault.verify_onset() if fc != "healthy_control" else True
    feature = oper_state(leaf, iface)
    window_end = datetime.now(UTC)

    # fabric-wide capture: target link (for the label) + every fabric-link endpoint (for the GNN)
    captured: dict[str, CaptureResult] = {}
    for dev, ifc, iid in endpoints:
        cap = capture_window(
            node=dev,
            iface_srl=ifc,
            window_start=onset_time,
            window_end=window_end,
            campaign_key=CAMPAIGN_KEY,
            topology_hash=topo,
            incident_id=f"{inj_id}--{iid.replace(':', '-').replace('/', '_')}",
            out_root=DATA_ROOT,
        )
        captured[iid] = cap

    fault.clear()
    stop_traffic()
    time.sleep(3)
    lab_clean = clean_between(leaf, netdev)
    status = "settled" if (onset_ok and lab_clean) else "quarantined"
    label = {
        "fault_class": fc,
        "target": target,
        "onset_at": onset_time.isoformat(),
        "window_start": onset_time.isoformat(),
        "window_end": window_end.isoformat(),
        "split": split,
        "observed_feature": feature,
        "under_load": True,
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
            for cap in captured.values():
                s.add(
                    Artifact(
                        kind="raw_telemetry_window",
                        uri=str(cap.path.relative_to(REPO)),
                        sha256=cap.sha256,
                        byte_size=cap.byte_size,
                        media_type="application/vnd.apache.parquet",
                    )
                )
        await s.commit()
    if status != "settled":
        for cap in captured.values():
            cap.path.unlink(missing_ok=True)
    return status


async def run() -> int:
    batch = int(os.environ.get("BATCH", "6"))
    target_total = int(os.environ.get("TARGET", "312"))
    cells = [(c, leaf) for c in CLASSES for leaf in LEAVES]
    per_cell = -(-target_total // len(cells))
    free = shutil.disk_usage("/").free / (1024**3)
    if free < CORPUS_MIN_FREE_GIB:
        print(f"[HALT] R10 disk gate: {free:.0f} GiB < {CORPUS_MIN_FREE_GIB}")
        return 1

    Session = make_sessionmaker()
    cid = await campaign_id(Session)
    topo = topology_hash()
    endpoints = fabric_link_endpoints()
    counts = await counts_by_stratum(Session, cid)
    total = sum(counts.values())
    print(
        f"corpus v3 (under load): {total}/{target_total}; per-cell {per_cell}; batch {batch}; "
        f"fabric endpoints/incident {len(endpoints)}"
    )

    collected = quarantined = 0
    idx = total
    while collected < batch and total + collected < target_total:
        cell = next((c for c in cells if counts.get(c, 0) < per_cell), None)
        if cell is None:
            break
        fc, leaf = cell
        netdev, iface = UPLINKS[idx % len(UPLINKS)]
        if shutil.disk_usage("/").free / (1024**3) < CORPUS_MIN_FREE_GIB:
            print("[HALT] disk floor reached mid-run")
            break
        status = await collect_one(
            Session, cid, topo, endpoints, fc, leaf, netdev, iface, split_of(leaf), idx + 1
        )
        if status == "settled":
            counts[cell] = counts.get(cell, 0) + 1
            collected += 1
        else:
            quarantined += 1
        idx += 1

    total_now = sum((await counts_by_stratum(Session, cid)).values())
    filled = sum(1 for c in cells if counts.get(c, 0) >= per_cell)
    print(f"batch done: +{collected} settled, {quarantined} quarantined")
    print(f"corpus v3 now: {total_now}/{target_total}; strata filled {filled}/{len(cells)}")
    return 0


if __name__ == "__main__":
    stop_traffic()  # ensure no leftover traffic before starting
    sys.exit(asyncio.run(run()))
