#!/usr/bin/env python3.12
"""B12 teardown residue check: after `make lab-down`, nothing must remain.

Verifies no residual containers, docker networks, the clab working directory, or dangling veth
interfaces in the Docker VM (Bible §7.3: teardown leaves no containers/veth/qdisc/network residue).
Run AFTER lab-down.
"""

from __future__ import annotations

import subprocess
import sys

ALPINE = "alpine@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce"


def sh(cmd: str) -> str:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=60
    ).stdout.strip()


def main() -> int:
    fails = []

    containers = sh("docker ps -aq --filter name=clab-closcall-2s4l | wc -l").strip()
    if containers != "0":
        fails.append(f"{containers} residual containers")

    nets = sh("docker network ls --filter name=closcall -q | wc -l").strip()
    if nets != "0":
        fails.append(f"{nets} residual networks")

    workdir = sh("ls -d lab/generated/clab-closcall-2s4l 2>/dev/null")
    if workdir:
        fails.append(f"working dir remains: {workdir}")

    # Dangling veths in the VM: containerlab veth pairs are named with a clab hash; after teardown
    # none should reference the lab. Inspect the VM init namespace for leftover clab veths.
    veths = sh(
        "docker run --rm --privileged --pid=host " + ALPINE + " nsenter -t 1 -m -n sh -c "
        "'ip -o link show 2>/dev/null | grep -c clab || true'"
    ).strip()
    if veths and veths not in ("0", ""):
        fails.append(f"{veths} residual clab veth links in VM")

    if fails:
        print(f"[FAIL] B12 teardown residue: {'; '.join(fails)}")
        return 1
    print("[PASS] B12 teardown: no residual containers, networks, working dir, or clab veths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
