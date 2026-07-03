#!/usr/bin/env python3.12
"""B09 ECMP distribution test against a running fabric.

Pre-registered in evals/protocols/b09-ecmp.md (frozen tolerance).

Generates 256 distinct-five-tuple UDP flows host1->host4 (varying source port) and measures the
egress packet split across leaf1's two spine uplinks. PASS iff each path carries 35-65% (immutable
tolerance). Also snapshots VM memory at flow-test peak (§17 guard).
"""

from __future__ import annotations

import re
import subprocess
import sys
import time

N_FLOWS = 256
LOW, HIGH = 0.35, 0.65
DST = "172.16.4.10"
UPLINKS = ("ethernet-1/1", "ethernet-1/2")
ALPINE = "alpine@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce"


def cli(sw: str, cmd: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "-u", "root", f"clab-closcall-2s4l-{sw}", "sr_cli", cmd],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout + p.stderr


def egress_pkts(iface: str) -> int:
    """Egress unicast packets on leaf1's uplink subinterface (from state counters)."""
    out = cli("leaf1", f"info from state interface {iface} subinterface 0 statistics")
    m = re.search(r"out-packets\s+(\d+)", out)
    return int(m.group(1)) if m else -1


def vm_used_gib() -> float:
    p = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            ALPINE,
            "awk",
            "/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print (t-a)/1048576}",
            "/proc/meminfo",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        return float(p.stdout.strip())
    except ValueError:
        return -1.0


def main() -> int:
    print("== B09 ECMP distribution (pre-registered: 35-65% @ 256 flows) ==")
    before = {i: egress_pkts(i) for i in UPLINKS}

    # 256 distinct flows: vary UDP source port; small burst each. nping is in netshoot.
    script = (
        "for p in $(seq 20000 20255); do "
        "nping --udp -c 3 --source-port $p -p 9999 --data-length 64 " + DST + " >/dev/null 2>&1; "
        "done; echo done"
    )
    peak_mem = vm_used_gib()
    proc = subprocess.Popen(
        ["docker", "exec", "clab-closcall-2s4l-host1", "sh", "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    while proc.poll() is None:
        peak_mem = max(peak_mem, vm_used_gib())
        time.sleep(3)
    time.sleep(3)

    after = {i: egress_pkts(i) for i in UPLINKS}
    delta = {i: after[i] - before[i] for i in UPLINKS}
    total = sum(delta.values())
    print(f"VM memory peak during flow test: {peak_mem:.2f} GiB of 15.6 (§17 guard)")
    if total <= 0:
        print(f"FAIL B09: no egress delta measured ({delta})")
        return 1
    shares = {i: delta[i] / total for i in UPLINKS}
    for i in UPLINKS:
        print(f"  {i}: {delta[i]} pkts ({shares[i] * 100:.1f}%)")
    ok = all(LOW <= s <= HIGH for s in shares.values())
    print(
        f"{'PASS' if ok else 'FAIL'} B09 ECMP: both paths within "
        f"[{int(LOW * 100)}%, {int(HIGH * 100)}%] — split "
        f"{shares[UPLINKS[0]] * 100:.1f}/{shares[UPLINKS[1]] * 100:.1f}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
