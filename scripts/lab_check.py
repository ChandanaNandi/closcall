#!/usr/bin/env python3.12
"""Network acceptance checks against a RUNNING fabric (Bible §7.3; acceptance B03-B08).

Assumes `make lab-up` has deployed and converged the 2s4l fabric. Each check prints PASS/FAIL with
evidence and contributes to the exit code. B09 (ECMP distribution) is intentionally NOT here — it
has an integrity pre-registration gate and lives in its own module after sign-off.

Boundary honored: reachability is proven strictly over the DATA plane (host data IPs routed via the
leaf, never the mgmt network); B05 proves the import policy REJECTS forbidden prefixes behaviorally
against the live RIB, not just syntactically (R17 #1).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.domain.fabric import allocate, load_fabric  # noqa: E402

SPINES = ["spine1", "spine2"]
LEAVES = ["leaf1", "leaf2", "leaf3", "leaf4"]
SWITCHES = SPINES + LEAVES
HOSTS = ["host1", "host2", "host3", "host4"]

_fail = 0


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def cli(sw: str, cmd: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "-u", "root", f"clab-closcall-2s4l-{sw}", "sr_cli", cmd],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout + p.stderr


def cli_stdin(sw: str, script: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "-i", "-u", "root", f"clab-closcall-2s4l-{sw}", "sr_cli"],
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout + p.stderr


def host(h: str, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["docker", "exec", f"clab-closcall-2s4l-{h}", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return p.returncode, p.stdout + p.stderr


def discard(sw: str) -> None:
    """Clear any stale candidate datastore (SR Linux candidates persist until discarded)."""
    cli_stdin(sw, "enter candidate\ndiscard stay\n")


def route_table(sw: str) -> str:
    return cli(sw, "show network-instance default route-table ipv4-unicast summary")


def bgp_summary(sw: str) -> str:
    return cli(sw, "show network-instance default protocols bgp neighbor")


def check_b03() -> None:
    """Expected eBGP sessions only are established."""
    expected = {sw: (4 if sw in SPINES else 2) for sw in SWITCHES}
    ok = True
    details = []
    for sw in SWITCHES:
        out = bgp_summary(sw)
        est = 0
        cfg = 0
        for line in out.splitlines():
            if "configured sessions are established" in line:
                parts = line.split(",")
                cfg = int(parts[0].strip().split()[0])
                est = int(parts[1].strip().split()[0])
        if est != expected[sw] or cfg != expected[sw]:
            ok = False
            details.append(f"{sw}:{est}/{cfg}!={expected[sw]}")
    emit(
        ok,
        "B03 expected BGP sessions",
        "all switches: exactly expected sessions established" if ok else "; ".join(details),
    )


def check_b04(topo) -> None:  # type: ignore[no-untyped-def]
    """Adj-RIB/RIB prefix sets match the IPAM manifest (only fabric prefixes, learned via BGP)."""
    loopbacks = {n.loopback.split("/")[0]: n.name for n in topo.nodes if n.loopback}
    host_subnets = {hn.subnet for hn in topo.host_networks}
    ok = True
    details = []
    for leaf in LEAVES:
        rt = route_table(leaf)
        bgp_prefixes = {
            line.split("|")[1].strip()
            for line in rt.splitlines()
            if "| bgp " in line and "|" in line
        }
        # A leaf must learn every OTHER loopback and every OTHER host subnet via BGP.
        own_lo = next(n.loopback.split("/")[0] for n in topo.nodes if n.name == leaf)
        own_hs = next(hn.subnet for hn in topo.host_networks if hn.leaf == leaf)
        want = {f"{lo}/32" for lo in loopbacks if lo != own_lo} | (host_subnets - {own_hs})
        missing = want - bgp_prefixes
        # Anything learned that is NOT a fabric prefix is a leak.
        fabric = {f"{lo}/32" for lo in loopbacks} | host_subnets
        leaked = bgp_prefixes - fabric
        if missing or leaked:
            ok = False
            details.append(f"{leaf} missing={sorted(missing)} leaked={sorted(leaked)}")
    emit(
        ok,
        "B04 RIB matches IPAM",
        "leaves learn exactly the fabric loopbacks+host-subnets, nothing else"
        if ok
        else "; ".join(details),
    )


def check_b05() -> None:
    """Import policy REJECTS forbidden prefixes behaviorally (R17 #1), proven on the live RIB.

    Two complementary proofs:
      1. Config-time martian rejection: SR Linux refuses to even create a 127.0.0.0/8 route.
      2. Active advertise+reject: leaf1 originates forbidden prefixes as connected loopback routes
         (which DO get advertised), and spine1's import-fabric must drop every one of them.
    Covers: out-of-set private /24, over-length /25, stray P2P /31. (Default 0.0.0.0/0 cannot be a
    connected route; it is structurally excluded by the exact-prefix import set, corroborated by
    B04 showing no non-fabric prefix ever appears in any RIB.)
    """
    import time

    discard("leaf1")  # start from a clean candidate

    # (1) martian rejected at config time.
    martian = cli_stdin(
        "leaf1",
        "enter candidate\n"
        "set / network-instance default next-hop-groups group bh blackhole\n"
        "set / network-instance default static-routes route 127.0.0.0/8 next-hop-group bh\n"
        "commit now\n",
    )
    martian_rejected = "Invalid unicast prefix" in martian or "Error" in martian
    discard("leaf1")  # clear the failed candidate

    # (2) active advertise + reject via connected loopbacks (lo0/lo1/lo2).
    bad = {"lo0": "192.168.7.1/24", "lo1": "172.16.99.129/25", "lo2": "10.0.0.200/31"}
    bad_prefixes = {"192.168.7.0/24", "172.16.99.128/25", "10.0.0.200/31"}
    inject = "enter candidate\n"
    for lo, addr in bad.items():
        inject += f"set / interface {lo} subinterface 0 ipv4 admin-state enable\n"
        inject += f"set / interface {lo} subinterface 0 ipv4 address {addr}\n"
        inject += f"set / network-instance default interface {lo}.0\n"
    for pfx in sorted(bad_prefixes):
        plen = pfx.split("/")[1]
        inject += (
            f"set / routing-policy prefix-set badtest prefix {pfx} "
            f"mask-length-range {plen}..{plen}\n"
        )
    inject += (
        "set / routing-policy policy export-fabric statement 5 match prefix prefix-set badtest\n"
    )
    inject += "set / routing-policy policy export-fabric statement 5 action policy-result accept\n"
    inject += "commit now\n"
    out = cli_stdin("leaf1", inject)
    if "Commit failed" in out or "Error:" in out:
        emit(
            False,
            "B05 live policy rejection (R17 #1)",
            f"injection failed: {out.strip().splitlines()[-1][:100]}",
        )
        _cleanup_b05()
        return
    # Poll until leaf1 is actually advertising the forbidden prefixes (propagation takes a moment).
    adv: set[str] = set()
    for _ in range(10):
        time.sleep(2)
        advertised = cli(
            "leaf1",
            "show network-instance default protocols bgp neighbor 10.0.0.1 advertised-routes ipv4",
        )
        adv = {p for p in bad_prefixes if p in advertised}
        if adv == bad_prefixes:
            break
    time.sleep(3)
    spine_rib = route_table("spine1")
    accepted = {
        p for p in bad_prefixes if any(p in ln and "| bgp " in ln for ln in spine_rib.splitlines())
    }
    _cleanup_b05()
    time.sleep(4)
    ok = martian_rejected and adv == bad_prefixes and not accepted
    emit(
        ok,
        "B05 live policy rejection (R17 #1)",
        f"martian rejected at config-time={martian_rejected}; leaf1 advertised {len(adv)}/3 "
        f"forbidden prefixes; spine1 accepted {len(accepted)} (want 0)"
        if ok
        else f"martian={martian_rejected} advertised={sorted(adv)} LEAKED={sorted(accepted)}",
    )


def _cleanup_b05() -> None:
    cli_stdin(
        "leaf1",
        "enter candidate\n"
        "delete / routing-policy policy export-fabric statement 5\n"
        "delete / routing-policy prefix-set badtest\n"
        "delete / network-instance default static-routes\n"
        "delete / network-instance default next-hop-groups group bh\n"
        "delete / interface lo0\n"
        "delete / interface lo1\n"
        "delete / interface lo2\n"
        "commit now\n",
    )


def check_b06(topo) -> None:  # type: ignore[no-untyped-def]
    """Every remote host subnet has exactly two FIB next hops on each leaf (ECMP)."""
    host_subnets = {hn.leaf: hn.subnet for hn in topo.host_networks}
    ok = True
    details = []
    for leaf in LEAVES:
        for other, subnet in host_subnets.items():
            if other == leaf:
                continue
            det = cli(
                leaf,
                f"show network-instance default route-table ipv4-unicast prefix {subnet} detail",
            )
            nh = det.count("via [ethernet")
            if nh != 2:
                ok = False
                details.append(f"{leaf}->{subnet}:{nh}nh")
    emit(
        ok,
        "B06 two FIB next hops (ECMP)",
        "every remote host subnet has exactly 2 next hops on every leaf"
        if ok
        else "; ".join(details),
    )


def check_b07(topo) -> None:  # type: ignore[no-untyped-def]
    """Full host reachability over the DATA plane only."""
    host_ip = {hn.leaf: hn.host_ip for hn in topo.host_networks}
    leaf_of = {f"host{i}": f"leaf{i}" for i in range(1, 5)}
    ok = True
    details = []
    for src in HOSTS:
        for dst in HOSTS:
            if src == dst:
                continue
            dst_ip = host_ip[leaf_of[dst]]
            rc, _ = host(src, "ping", "-c", "2", "-W", "2", dst_ip)
            if rc != 0:
                ok = False
                details.append(f"{src}->{dst_ip} FAIL")
                continue
            # prove it went via the data plane (eth1), not mgmt (eth0)
            _, rt = host(src, "ip", "route", "get", dst_ip)
            if "eth1" not in rt:
                ok = False
                details.append(f"{src}->{dst_ip} not via data plane: {rt.strip()[:60]}")
    emit(
        ok,
        "B07 data-plane reachability",
        "all host pairs reachable via eth1 data plane (not mgmt)" if ok else "; ".join(details),
    )


def check_b08(topo) -> None:  # type: ignore[no-untyped-def]
    """MTU boundary: DF 1472 passes, DF 1473 fails (base MTU 1500)."""
    host_ip = {hn.leaf: hn.host_ip for hn in topo.host_networks}
    dst = host_ip["leaf4"]
    rc_ok, _ = host("host1", "ping", "-c", "2", "-W", "2", "-M", "do", "-s", "1472", dst)
    rc_bad, _ = host("host1", "ping", "-c", "2", "-W", "2", "-M", "do", "-s", "1473", dst)
    ok = rc_ok == 0 and rc_bad != 0
    emit(
        ok,
        "B08 MTU boundary",
        "DF 1472 passes, DF 1473 fails (MTU 1500)"
        if ok
        else f"unexpected: 1472 rc={rc_ok}, 1473 rc={rc_bad}",
    )


def wait_converged(topo, timeout: int = 150) -> bool:  # type: ignore[no-untyped-def]
    """Poll until every leaf has learned all remote fabric prefixes (route, not just session,
    convergence). Session establishment (~35 s) precedes full leaf-to-leaf route propagation."""
    import time

    loopbacks = {n.loopback.split("/")[0] for n in topo.nodes if n.loopback}
    host_subnets = {hn.subnet for hn in topo.host_networks}
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        done = True
        for leaf in LEAVES:
            rt = route_table(leaf)
            bgp = {ln.split("|")[1].strip() for ln in rt.splitlines() if "| bgp " in ln}
            own_lo = next(n.loopback.split("/")[0] for n in topo.nodes if n.name == leaf)
            own_hs = next(hn.subnet for hn in topo.host_networks if hn.leaf == leaf)
            want = {f"{lo}/32" for lo in loopbacks if lo != own_lo} | (host_subnets - {own_hs})
            if want - bgp:
                done = False
                break
        if done:
            return True
        time.sleep(3)
    return False


def main() -> int:
    topo = allocate(load_fabric(REPO / "lab" / "fabric.yaml"))
    print("== ClosCall network acceptance (B03-B08) ==")
    if not wait_converged(topo):
        print("[WARN] route convergence wait timed out; running checks anyway")
    check_b03()
    check_b04(topo)
    check_b05()
    check_b06(topo)
    check_b07(topo)
    check_b08(topo)
    print(f"== {_fail} failed ==")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
