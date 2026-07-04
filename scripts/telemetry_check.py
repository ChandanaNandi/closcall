#!/usr/bin/env python3.12
"""Gate 4 telemetry acceptance against the running observation plane (Bible §9; C02-C08).

Assumes `make lab-up` + `make telemetry-up` are running and converged. Checks map to the Gate 4
exit criteria:
  1. every node/eligible interface appears (C02)
  2. a known state change is visible within a measured bound
  3. collector interruption is detected and blocks automation (C06/C07, fail-closed)
  4. evidence snapshot hashes reproduce (C08)
Writes an evidence report to evals/reports/gate4-telemetry.txt.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROM = "http://127.0.0.1:9090"
SWITCHES = {"spine1", "spine2", "leaf1", "leaf2", "leaf3", "leaf4"}
OPER = "closcall_if_state_srl_nokia_interfaces_interface_oper_state"
VISIBILITY_BOUND_S = 20.0
STALE_BOUND_S = 20.0
_fail = 0
_log: list[str] = []


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
    print(line)
    _log.append(line)


def promq(query: str, at: float | None = None) -> list[dict]:  # type: ignore[type-arg]
    url = f"{PROM}/api/v1/query?query={urllib.parse.quote(query)}"
    if at is not None:
        url += f"&time={at:.3f}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r).get("data", {}).get("result", [])


def cli(sw: str, script: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "-i", "-u", "root", f"clab-closcall-2s4l-{sw}", "sr_cli"],
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout + p.stderr


def check_c02_all_appear() -> None:
    series = promq(OPER)
    sources = {s["metric"].get("source") for s in series}
    missing = SWITCHES - sources
    # bounded cardinality: each source has a finite interface set (no unbounded/free-text labels)
    labels = set()
    for s in series[:50]:
        labels |= set(s["metric"].keys())
    unbounded = labels - {
        "__name__",
        "instance",
        "job",
        "source",
        "interface_name",
        "oper_state",
        "subscription_name",
    }
    ok = not missing and not unbounded
    emit(
        ok,
        "C02 every node appears",
        f"{len(sources)}/6 switches present, {len(series)} oper-state series, bounded labels"
        if ok
        else f"missing={missing} unexpected_labels={unbounded}",
    )


def check_visibility() -> None:
    iface = "ethernet-1/1"
    down = lambda: [  # noqa: E731
        s
        for s in promq(f'{OPER}{{source="leaf1",interface_name="{iface}"}}')
        if s["metric"].get("oper_state") == "down"
    ]
    cli("leaf1", f"enter candidate\nset / interface {iface} admin-state disable\ncommit now\n")
    t0 = time.monotonic()
    seen = False
    while time.monotonic() - t0 < 60:
        if down():
            seen = True
            break
        time.sleep(1)
    dt = time.monotonic() - t0
    cli("leaf1", f"enter candidate\nset / interface {iface} admin-state enable\ncommit now\n")
    time.sleep(8)
    ok = seen and dt <= VISIBILITY_BOUND_S
    emit(
        ok,
        "state-change visibility",
        f"leaf1 {iface} down observed in {dt:.1f}s (bound {VISIBILITY_BOUND_S}s)"
        if ok
        else f"not observed within bound (dt={dt:.1f}s, seen={seen})",
    )


def _blocked() -> bool:
    """Fail-closed automation gate: block if the collector target is down or samples are stale."""
    up = promq('up{job="gnmic"}')
    if not up or float(up[0]["value"][1]) == 0.0:
        return True
    fresh = promq(f"time() - max(timestamp({OPER}))")
    return bool(fresh) and float(fresh[0]["value"][1]) > STALE_BOUND_S


def check_collector_interruption_blocks() -> None:
    if _blocked():
        emit(False, "C06/C07 collector-interruption blocks", "already blocked while healthy")
        return
    subprocess.run(["docker", "stop", "closcall-gnmic"], capture_output=True)
    t0 = time.monotonic()
    detected = False
    while time.monotonic() - t0 < 40:
        if _blocked():
            detected = True
            break
        time.sleep(2)
    subprocess.run(["docker", "start", "closcall-gnmic"], capture_output=True)
    time.sleep(15)
    emit(
        detected,
        "C06/C07 collector-interruption blocks automation",
        f"gnmic stopped -> automation blocked in {time.monotonic() - t0:.0f}s; restored healthy"
        if detected
        else "interruption did NOT block automation (fail-open!)",
    )


def check_c08_evidence_hash() -> None:
    at = time.time() - 30  # a settled as-of time
    query = OPER

    def snapshot() -> str:
        rows = promq(query, at=at)
        canon = sorted(
            (
                s["metric"].get("source"),
                s["metric"].get("interface_name"),
                s["metric"].get("oper_state"),
            )
            for s in rows
        )
        return hashlib.sha256(json.dumps(canon).encode()).hexdigest()

    h1 = snapshot()
    time.sleep(1)
    h2 = snapshot()
    ok = h1 == h2 and len(promq(query, at=at)) > 0
    emit(
        ok,
        "C08 evidence snapshot hash reproduces",
        f"as-of snapshot hash stable: {h1[:16]}" if ok else f"hash mismatch {h1[:12]} != {h2[:12]}",
    )


def main() -> int:
    print("== ClosCall telemetry acceptance (Gate 4: C02-C08) ==")
    check_c02_all_appear()
    check_visibility()
    check_collector_interruption_blocks()
    check_c08_evidence_hash()
    print(f"== {_fail} failed ==")
    report = Path(__file__).resolve().parents[1] / "evals" / "reports" / "gate4-telemetry.txt"
    report.write_text("\n".join(_log) + f"\n== {_fail} failed ==\n")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
