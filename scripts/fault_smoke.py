"""Gate 5 fault-framework smoke campaign (Bible §8.3).

For each fault class: write the write-ahead ledger `planned` record (with exact cleanup payload)
BEFORE applying, apply, verify OBSERVED onset, then clear and record. After the campaign, run the
reconciler (nothing should be outstanding) and assert NO dirty state (no residual qdiscs, down
interfaces, or containers stopped). Also asserts the honest-taxonomy no-overclaim rule.

Requires the fabric (make lab-up) + telemetry (make telemetry-up) running.
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.chaos.faults import FAULT_TAXONOMY, Fault  # noqa: E402
from closcall.chaos.ledger import Ledger, Phase, now_record  # noqa: E402

LEDGER = REPO / "artifacts" / "chaos-ledger.jsonl"
# (fault_class, node, netdev, srl-iface). Fabric link leaf1<->spine1 for most; telemetry_gap global.
CAMPAIGN = [
    ("healthy_control", "leaf1", "e1-1", "ethernet-1/1"),
    ("admin_shutdown", "leaf1", "e1-1", "ethernet-1/1"),
    ("carrier_loss", "leaf2", "e1-1", "ethernet-1/1"),
    ("intermittent_link", "leaf3", "e1-1", "ethernet-1/1"),
    ("rate_limited_uplink", "leaf1", "e1-3", "ethernet-1/3"),
    ("impaired_link", "leaf4", "e1-1", "ethernet-1/1"),
    ("telemetry_gap", "-", "-", "-"),
]
_fail = 0


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def no_overclaim() -> None:
    bad = [
        fc
        for fc, (_, meaning) in FAULT_TAXONOMY.items()
        if "pfc" in meaning.lower() or "ecn" in meaning.lower() or "optic" in meaning.lower()
    ]
    emit(
        not bad,
        "honest taxonomy (no fidelity overclaim)",
        "no fault labels claim PFC/ECN/optics" if not bad else f"overclaiming: {bad}",
    )


def run_campaign() -> None:
    led = Ledger(LEDGER)
    for fc, node, netdev, srl in CAMPAIGN:
        iid = f"{fc}-{uuid.uuid4().hex[:8]}"
        fault = Fault(fault_class=fc, node=node, iface_netdev=netdev, iface_srl=srl)
        target = {"node": node, "interface": srl}
        cleanup = fault.cleanup_payload()
        # write-ahead: planned + cleanup payload BEFORE any mutation (§8.3)
        led.append(now_record(iid, fc, Phase.PLANNED, target, cleanup))
        try:
            led.append(now_record(iid, fc, Phase.INJECTING, target, cleanup))
            fault.apply()
            time.sleep(3)
            onset = fault.verify_onset()
            led.append(
                now_record(
                    iid,
                    fc,
                    Phase.ACTIVE if onset else Phase.FAILED,
                    target,
                    cleanup,
                    {"onset_observed": onset},
                )
            )
            emit(
                onset or fc == "healthy_control",
                f"onset {fc}",
                "observed"
                if onset
                else ("no-op (healthy control)" if fc == "healthy_control" else "NOT observed"),
            )
        finally:
            led.append(now_record(iid, fc, Phase.CLEARING, target, cleanup))
            fault.clear()
            led.append(now_record(iid, fc, Phase.CLEARED, target, cleanup))
        time.sleep(2)


def check_no_dirty_state() -> None:
    dirty = []
    for _, node, netdev, _ in CAMPAIGN:
        if node == "-":
            continue
        # residual qdisc?
        rc = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "root",
                f"clab-closcall-2s4l-{node}",
                "sh",
                "-c",
                f"tc qdisc show dev {netdev} | grep -qE 'netem|tbf' && echo dirty || true",
            ],
            capture_output=True,
            text=True,
        )
        if "dirty" in rc.stdout:
            dirty.append(f"{node}:{netdev} qdisc")
        # interface down?
        st = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "root",
                f"clab-closcall-2s4l-{node}",
                "sh",
                "-c",
                f"ip -br link show {netdev}",
            ],
            capture_output=True,
            text=True,
        )
        if " DOWN " in st.stdout or st.stdout.strip().split()[1:2] == ["DOWN"]:
            dirty.append(f"{node}:{netdev} down")
    # gnmic back up?
    g = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "closcall-gnmic"],
        capture_output=True,
        text=True,
    )
    if g.stdout.strip() != "true":
        dirty.append("gnmic not running")
    emit(not dirty, "no dirty state after campaign", "clean" if not dirty else str(dirty))


def check_reconciler() -> None:
    outstanding = Ledger(LEDGER).outstanding()
    emit(
        not outstanding,
        "reconciler: no outstanding injections",
        "all injections cleared/settled"
        if not outstanding
        else f"{len(outstanding)} outstanding: {[r.injection_id for r in outstanding]}",
    )


def main() -> int:
    print("== ClosCall fault-framework smoke campaign (Gate 5) ==")
    LEDGER.unlink(missing_ok=True)
    no_overclaim()
    run_campaign()
    check_no_dirty_state()
    check_reconciler()
    print(f"== {_fail} failed ==")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
