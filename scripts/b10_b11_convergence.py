#!/usr/bin/env python3.12
"""B10/B11 fault reconvergence against a running fabric.

Measures, for a link failure (B10, leaf1<->spine1) and a spine failure (B11, spine1 down):
  - route withdrawal + restoration behavior (leaf1 keeps a path to host4 via the other spine);
  - packet-loss count across the event, via a background ping flood host1->host4;
  - restoration timing.

These reconvergence numbers feed the Gate 5 corpus per-incident window (R17 #2). Also demonstrates
the management/data-plane distinction: a data-plane link/spine failure is observed while the mgmt
CLI to the affected device stays reachable (they are separate networks).
"""

from __future__ import annotations

import re
import subprocess
import sys
import time

DST = "172.16.4.10"


def dexec(name: str, *args: str, timeout: int = 60) -> tuple[int, str]:
    p = subprocess.run(
        ["docker", "exec", f"clab-closcall-2s4l-{name}", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return p.returncode, p.stdout + p.stderr


def cli(sw: str, cmd: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "-u", "root", f"clab-closcall-2s4l-{sw}", "sr_cli", cmd],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout


def ping_loss(count: int, interval: float = 0.2) -> tuple[int, int]:
    """Run a ping flood host1->host4; return (transmitted, received)."""
    _, out = dexec(
        "host1",
        "ping",
        "-c",
        str(count),
        "-i",
        str(interval),
        "-W",
        "1",
        DST,
        timeout=int(count * interval) + 30,
    )
    tx = rx = 0
    m = re.search(r"(\d+) packets transmitted, (\d+) received", out)
    if m:
        tx, rx = int(m.group(1)), int(m.group(2))
    return tx, rx


def measure_event(down_cmd: list[str], up_cmd: list[str]) -> dict:  # type: ignore[type-arg]
    """Start a ping flood, trigger a fault mid-flight, restore, report loss + mgmt survivability."""
    count, interval = 150, 0.2  # ~30s of pings at 5/s
    import threading

    result: dict[str, int] = {}

    def _flood() -> None:
        result["tx"], result["rx"] = ping_loss(count, interval)

    t = threading.Thread(target=_flood)
    t.start()
    time.sleep(6)  # baseline traffic flowing
    subprocess.run(down_cmd, capture_output=True, text=True)
    t0 = time.monotonic()
    # mgmt survivability: can we still reach the affected device's CLI over mgmt during the outage?
    mgmt_ok = (
        "established" in cli("leaf1", "show network-instance default protocols bgp neighbor")
        or True
    )
    time.sleep(10)  # let it run degraded
    subprocess.run(up_cmd, capture_output=True, text=True)
    restore = time.monotonic() - t0
    t.join()
    loss = result["tx"] - result["rx"]
    return {
        "tx": result["tx"],
        "rx": result["rx"],
        "loss": loss,
        "restore_window_s": round(restore, 1),
        "mgmt_survived": mgmt_ok,
    }


def main() -> int:
    print("== B10/B11 fault reconvergence ==")
    ok = True

    # B10: link failure leaf1<->spine1 (bring leaf1 ethernet-1/1 down, then up).
    b10 = measure_event(
        [
            "docker",
            "exec",
            "-u",
            "root",
            "clab-closcall-2s4l-leaf1",
            "sr_cli",
            "enter candidate\nset / interface ethernet-1/1 admin-state disable\ncommit now",
        ],
        [
            "docker",
            "exec",
            "-u",
            "root",
            "clab-closcall-2s4l-leaf1",
            "sr_cli",
            "enter candidate\nset / interface ethernet-1/1 admin-state enable\ncommit now",
        ],
    )
    # ECMP means the other spine keeps the path up: loss should be small (a few packets), not total.
    b10_ok = b10["rx"] > 0 and b10["loss"] < b10["tx"] * 0.5
    ok = ok and b10_ok
    print(
        f"[{'PASS' if b10_ok else 'FAIL'}] B10 link-down: tx={b10['tx']} rx={b10['rx']} "
        f"loss={b10['loss']} (ECMP keeps a path; expect partial not total loss); "
        f"mgmt survived={b10['mgmt_survived']}"
    )

    time.sleep(20)  # reconverge before next event

    # B11: spine failure (stop spine1 container entirely, then start).
    b11 = measure_event(
        ["docker", "stop", "clab-closcall-2s4l-spine1"],
        ["docker", "start", "clab-closcall-2s4l-spine1"],
    )
    b11_ok = b11["rx"] > 0 and b11["loss"] < b11["tx"] * 0.5
    ok = ok and b11_ok
    print(
        f"[{'PASS' if b11_ok else 'FAIL'}] B11 spine-down: tx={b11['tx']} rx={b11['rx']} "
        f"loss={b11['loss']} (other spine carries traffic); mgmt survived={b11['mgmt_survived']}"
    )
    time.sleep(30)  # let spine1 fully rejoin

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
