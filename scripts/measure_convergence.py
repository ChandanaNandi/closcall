#!/usr/bin/env python3.12
"""Measure first-boot CLI readiness and full-fabric BGP convergence from a CLEAN deploy.

First-class Gate 3 deliverables (R17 #2, #3): these numbers feed Gate 4's corpus per-incident
timing. Tears down any existing lab, deploys fresh, then times:
  - first-boot: wall seconds until every switch's sr_cli answers (as root);
  - convergence: wall seconds (from deploy return) until every switch reports all its configured
    eBGP sessions established.

Run standalone; it manages its own deploy/teardown. Requires Docker + pinned images.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SWITCHES = ["spine1", "spine2", "leaf1", "leaf2", "leaf3", "leaf4"]
EXPECTED = {"spine1": 4, "spine2": 4, "leaf1": 2, "leaf2": 2, "leaf3": 2, "leaf4": 2}


def sh(cmd: str, timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=REPO)
    return p.returncode, p.stdout + p.stderr


def cli(sw: str, cmd: str) -> tuple[int, str]:
    return sh(f'docker exec -u root clab-closcall-2s4l-{sw} sr_cli "{cmd}"', timeout=60)


def established(sw: str) -> int:
    rc, out = cli(sw, "show network-instance default protocols bgp neighbor")
    if rc != 0:
        return -1
    for line in out.splitlines():
        # summary line: "N configured neighbors, M configured sessions are established, ..."
        if "configured sessions are established" in line:
            try:
                return int(
                    line.split("configured sessions are established")[0].split(",")[-1].strip()
                )
            except ValueError:
                return 0
    return 0


def now() -> float:
    return time.monotonic()


def main() -> int:
    print("tearing down any existing lab...")
    sh("make lab-down", timeout=300)
    sh("docker network ls --filter name=closcall -q | xargs -r docker network rm", timeout=60)

    print("clean deploy...")
    t_deploy0 = now()
    rc, out = sh("make lab-up", timeout=600)
    t_deploy = now() - t_deploy0
    if rc != 0:
        print("DEPLOY FAILED:\n" + out[-800:])
        return 1
    print(f"deploy wall: {t_deploy:.1f}s")

    # First-boot: all switch CLIs answer.
    t0 = now()
    first_boot = None
    while now() - t0 < 420:
        if all(cli(sw, "info from state system information version")[0] == 0 for sw in SWITCHES):
            first_boot = now() - t0
            break
        time.sleep(3)
    print(
        f"first-boot CLI-ready (all 6 switches): {first_boot:.1f}s"
        if first_boot
        else "first-boot TIMEOUT"
    )

    # Convergence: every switch reports all its sessions established.
    t1 = now()
    converged = None
    counts: dict[str, int] = {}
    while now() - t1 < 300:
        counts = {sw: established(sw) for sw in SWITCHES}
        if all(counts[sw] >= EXPECTED[sw] for sw in SWITCHES):
            converged = now() - t1
            break
        time.sleep(2)
    total = (first_boot or 0) + (converged or 0)
    if converged is not None:
        print(f"BGP convergence (after CLI ready): {converged:.1f}s")
        print(f"first-boot + convergence total: {total:.1f}s")
    else:
        print(f"convergence TIMEOUT; last counts: {counts}")
    return 0 if (first_boot and converged is not None) else 1


if __name__ == "__main__":
    sys.exit(main())
