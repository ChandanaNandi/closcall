#!/usr/bin/env python3.12
"""SCRATCH, NON-CANONICAL Gate 1 resource benchmark — NOT the ClosCall fabric.

⚠️  This is a throwaway measurement harness. It boots 6 standalone SR Linux
    containers (2 spines + 4 leaves) and 4 tiny host containers purely to
    measure the RAM/CPU/disk/boot footprint of a 2s4l-sized lab on THIS host.

    It is NOT the canonical topology. It has NO BGP wiring, NO IPAM, NO ECMP.
    The real topology is generated from lab/fabric.yaml in Gate 2 and brought
    up with containerlab. Nothing here is used past the Gate 1 benchmark.

SR Linux boots its full control-plane daemon set on startup regardless of
wiring, so standalone nodes give an honest per-node and aggregate RAM figure;
veth wiring and BGP peering add negligible RAM (verified separately at Gate 3).

Measures peak VM memory used (MemTotal-MemAvailable inside the Docker Desktop
VM) across the boot/settle window, cross-checked against the sum of per-node
cgroup memory.current. Derives shard count requiring >=30% memory headroom
(Bible Gate 1 exit; default one lab).
"""

from __future__ import annotations

import subprocess
import time

SRL = (
    "ghcr.io/nokia/srlinux@sha256:f711ddadbca870996793ac9bb3fccb950aa2c6a906da64a304c5274a2c2dceee"
)
ALPINE = "alpine@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce"
SRL_NODES = [
    "bench-spine1",
    "bench-spine2",
    "bench-leaf1",
    "bench-leaf2",
    "bench-leaf3",
    "bench-leaf4",
]
HOST_NODES = ["bench-host1", "bench-host2", "bench-host3", "bench-host4"]
SETTLE_SECONDS = 240
SAMPLE_EVERY = 20
HEADROOM = 0.30
GIB = 1048576  # kB in a GiB


def sh(cmd: str, timeout: int = 120) -> str:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.stdout.strip()


def vm_mem() -> tuple[float, float]:
    out = sh(f"docker run --rm {ALPINE} cat /proc/meminfo")
    total = avail = 0.0
    for line in out.splitlines():
        if line.startswith("MemTotal:"):
            total = int(line.split()[1]) / GIB
        elif line.startswith("MemAvailable:"):
            avail = int(line.split()[1]) / GIB
    return total, avail


def teardown() -> None:
    names = " ".join(SRL_NODES + HOST_NODES)
    sh(f"docker rm -f {names} >/dev/null 2>&1", timeout=180)


def cgroup_sum() -> float:
    total = 0.0
    for n in SRL_NODES:
        v = sh(f"docker exec {n} cat /sys/fs/cgroup/memory.current 2>/dev/null")
        if v.isdigit():
            total += int(v) / (1024**3)
    return total


def main() -> None:
    print("== NON-CANONICAL 2s4l resource benchmark ==")
    teardown()  # clean start
    mem_total, base_avail = vm_mem()
    print(f"VM MemTotal: {mem_total:.2f} GiB")
    print(f"baseline MemAvailable (empty): {base_avail:.2f} GiB")

    for n in SRL_NODES:
        sh(
            f"docker run -d --name {n} --privileged --hostname {n[6:]} {SRL} "
            f'sudo bash -c "touch /.dockerenv && /opt/srlinux/bin/sr_linux" >/dev/null'
        )
    for n in HOST_NODES:
        sh(f"docker run -d --name {n} {ALPINE} sleep infinity >/dev/null")
    print(f"launched {len(SRL_NODES)} SR Linux nodes + {len(HOST_NODES)} hosts")

    peak_used = 0.0
    t0 = time.time()
    while time.time() - t0 < SETTLE_SECONDS:
        _, avail = vm_mem()
        used = mem_total - avail
        peak_used = max(peak_used, used)
        running = sh("docker ps -q | wc -l").strip()
        print(
            f"  t+{int(time.time() - t0):3}s  used={used:.2f} GiB  "
            f"peak={peak_used:.2f} GiB  running={running}"
        )
        time.sleep(SAMPLE_EVERY)

    cg = cgroup_sum()
    lab_footprint = peak_used - (mem_total - base_avail)
    print("\n== RESULTS ==")
    print(f"peak VM used (all nodes):        {peak_used:.2f} GiB")
    print(f"lab footprint (peak - base):     {lab_footprint:.2f} GiB")
    print(f"sum of SR Linux cgroup memory:   {cg:.2f} GiB (cross-check)")
    print(f"per-node avg (cgroup/6):         {cg / 6:.2f} GiB")
    disk = sh("df -k /System/Volumes/Data | tail -1 | awk '{print $4}'")
    print(f"host disk free:                  {int(disk) / GIB:.1f} GiB")

    # Shard count: how many labs fit in VM with >=30% headroom.
    usable = mem_total * (1 - HEADROOM)
    fits = int(usable // peak_used) if peak_used > 0 else 0
    shard = max(1, fits) if fits else 0
    hr = (mem_total - peak_used) / mem_total if mem_total else 0
    print(f"\nusable VM at {int(HEADROOM * 100)}% headroom: {usable:.2f} GiB")
    print(f"labs that fit with headroom:     {fits}  -> shard count = {shard} (canon default 1)")
    print(
        f"headroom with ONE lab:           {hr * 100:.0f}% "
        f"({'PASS' if hr >= HEADROOM else 'FAIL'} >= {int(HEADROOM * 100)}%)"
    )

    teardown()
    remaining = sh("docker ps -aq --filter name=bench- | wc -l").strip()
    print(f"\nteardown complete; residual bench containers: {remaining}")


if __name__ == "__main__":
    main()
