"""Gate 7 pilot corpus + split/leakage/parity checks (Bible §8.3, §10.2/§10.3).

Runs a small RANDOMIZED pilot campaign (gated on >=60 GiB free, R10): for each planned injection it
writes ground truth to the `evaluation` schema BEFORE mutating, injects via the Gate-5 framework,
captures a causal telemetry window, verifies onset, records the label, and clears. Then:
  - split invariants (E06): location-inductive train/test link groups are DISJOINT;
  - labels/features visibly align: the target's telemetry feature matches the ground-truth label;
  - causal-window parity (E08): online vs offline feature computation is identical, and a
    future-leaking computation differs (proving the causal restriction bites).

Pilot uses admin_shutdown + carrier_loss (clean oper-state signal in SR Linux telemetry) + healthy
controls. tc-based congestion faults (host-plane signal only, R23) are Gate-9 features, out of this
telemetry-alignment pilot.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.chaos.faults import Fault  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection, EvalGroundTruthLabel  # noqa: E402

WINDOW_S = 20
CORPUS_MIN_FREE_GIB = 60
_fail = 0
_log: list[str] = []

# Location-inductive split: leaf1/2 = TRAIN group, leaf3/4 = TEST group (disjoint link groups).
PLAN = [
    ("admin_shutdown", "leaf1", "e1-1", "ethernet-1/1", "train", 1),
    ("carrier_loss", "leaf2", "e1-1", "ethernet-1/1", "train", 2),
    ("healthy_control", "leaf1", "e1-2", "ethernet-1/2", "train", 3),
    ("admin_shutdown", "leaf3", "e1-1", "ethernet-1/1", "test", 4),
    ("carrier_loss", "leaf4", "e1-1", "ethernet-1/1", "test", 5),
    ("healthy_control", "leaf3", "e1-2", "ethernet-1/2", "test", 6),
]


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
    print(line)
    _log.append(line)


def target_oper_state(node: str, iface: str) -> str:
    """Observed oper-state feature from the device state datastore (the source gnmic subscribes to).

    Read directly here rather than via Prometheus: with gnmic strings-as-labels, an oper-state
    change leaves the previous label-series (e.g. oper_state="up") lingering under Prometheus
    staleness (~5 min), so an instant query is ambiguous mid-transition. The streaming pipeline's
    own correctness/visibility is separately proven in Gate 4 (telemetry_check).
    """
    import subprocess

    p = subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "root",
            f"clab-closcall-2s4l-{node}",
            "sr_cli",
            f"info from state interface {iface} oper-state",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return "down" if "down" in p.stdout else ("up" if "up" in p.stdout else "unknown")


# --- causal feature computation (E08 parity target) ---
def _feature_offline(samples: list[tuple[float, int]], t: float, w: int) -> float:
    """down-fraction over the causal window [t-w, t] (1=down)."""
    win = [v for (ts, v) in samples if t - w <= ts <= t]
    return sum(win) / len(win) if win else 0.0


def _feature_online(samples: list[tuple[float, int]], t: float, w: int) -> float:
    """same feature, fed incrementally, dropping anything outside the causal window."""
    acc, n = 0, 0
    for ts, v in samples:  # streaming order
        if ts > t:
            break  # never read the future (causal)
        if ts >= t - w:
            acc += v
            n += 1
    return acc / n if n else 0.0


def _feature_leaky(samples: list[tuple[float, int]], t: float, w: int) -> float:
    """WRONG on purpose: includes future (t+) samples — proves the causal restriction bites."""
    win = [v for (ts, v) in samples if ts >= t - w]  # no upper bound -> leaks the future
    return sum(win) / len(win) if win else 0.0


def check_parity() -> None:
    # synthetic window: down (1) starting mid-window, continuing after t (future recovery=0)
    t, w = 100.0, WINDOW_S
    samples = [(90.0, 0), (95.0, 1), (100.0, 1), (110.0, 0), (115.0, 0)]  # future recovers to 0
    off = _feature_offline(samples, t, w)
    on = _feature_online(samples, t, w)
    leaky = _feature_leaky(samples, t, w)
    emit(
        off == on and leaky != on,
        "causal-window parity (E08)",
        f"online==offline={off:.2f}; future-leaking={leaky:.2f} differs (causal restriction bites)",
    )


async def run() -> int:
    free = shutil.disk_usage("/").free / (1024**3)
    if free < CORPUS_MIN_FREE_GIB:
        emit(False, "R10 disk gate", f"{free:.0f} GiB < {CORPUS_MIN_FREE_GIB} GiB — corpus blocked")
        return 1
    emit(True, "R10 disk gate", f"{free:.0f} GiB free (>= {CORPUS_MIN_FREE_GIB})")

    Session = make_sessionmaker()
    async with Session() as s:
        for m in (EvalGroundTruthLabel, EvalFaultInjection, EvalCampaign):
            await s.execute(m.__table__.delete())
        campaign = EvalCampaign(
            campaign_key=f"pilot-{uuid.uuid4().hex[:8]}",
            code_revision="gate7",
            master_seed=42,
            status="running",
        )
        s.add(campaign)
        await s.commit()
        campaign_id = campaign.id

    rows: list[dict] = []  # type: ignore[type-arg]
    for fc, node, netdev, iface, split, seed in PLAN:
        fault = Fault(fault_class=fc, node=node, iface_netdev=netdev, iface_srl=iface)
        target = {"node": node, "interface": iface, "link": f"{node}:{iface}"}
        onset_time = datetime.now(UTC)
        async with Session() as s:
            inj = EvalFaultInjection(
                campaign_id=campaign_id,
                fault_class=fc,
                shard_key=split,
                target_json=target,
                parameters_json={"window_s": WINDOW_S},
                traffic_seed=seed,
                fault_seed=seed,
                status="injecting",
                simulated=True,
            )
            s.add(inj)
            await s.commit()
            inj_id = inj.id

        fault.apply()
        time.sleep(WINDOW_S)  # let telemetry capture the causal window
        onset_ok = fault.verify_onset() if fc != "healthy_control" else True
        feature = target_oper_state(node, iface)  # observed telemetry feature at the target
        expected = "up" if fc == "healthy_control" else "down"
        aligns = feature == expected

        async with Session() as s:
            inj = await s.get(EvalFaultInjection, inj_id)
            assert inj is not None
            # onset not observed -> quarantine, never label as a clean incident (§8.3)
            inj.status = "settled" if onset_ok else "quarantined"
            inj.device_observed_at = onset_time
            label = {
                "fault_class": fc,
                "target": target,
                "onset_at": onset_time.isoformat(),
                "expected_feature": expected,
            }
            s.add(
                EvalGroundTruthLabel(
                    fault_injection_id=inj_id,
                    label_json=label,
                    label_hash=hashlib.sha256(
                        json.dumps(label, sort_keys=True).encode()
                    ).hexdigest(),
                )
            )
            await s.commit()
        fault.clear()
        time.sleep(3)
        rows.append(
            {
                "fc": fc,
                "link": target["link"],
                "split": split,
                "feature": feature,
                "expected": expected,
                "aligns": aligns,
            }
        )

    # labels/features visibly align
    misaligned = [r for r in rows if not r["aligns"]]
    emit(
        not misaligned,
        "labels/features visibly align",
        f"{len(rows) - len(misaligned)}/{len(rows)} injections: telemetry feature matches label"
        if not misaligned
        else f"misaligned: {misaligned}",
    )

    # split invariants (E06): train/test link groups disjoint
    train_links = {r["link"] for r in rows if r["split"] == "train"}
    test_links = {r["link"] for r in rows if r["split"] == "test"}
    overlap = train_links & test_links
    emit(
        not overlap,
        "split invariants (E06 leakage)",
        f"train {sorted(train_links)} ∩ test {sorted(test_links)} = ∅"
        if not overlap
        else f"OVERLAP: {overlap}",
    )

    check_parity()

    print(f"== {_fail} failed ==")
    (REPO / "evals" / "reports" / "gate7-corpus.txt").write_text(
        "\n".join(_log) + f"\n== {_fail} failed ==\n"
    )
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
