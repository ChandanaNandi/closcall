"""§8.1 traffic smoke — prove the generator puts measurable load on the fabric (make traffic-smoke).

Loads a profile, starts iperf3 servers on the receivers, runs the planned host<->host flows
across the Clos via `docker exec iperf3 -J`, aggregates the §8.1 record (offered/observed bitrate,
retransmits, RTT, completion), and verifies observed load clears a floor. Needs the lab up.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.traffic.generator import (  # noqa: E402
    Flow,
    FlowResult,
    TrafficProfile,
    plan_flows,
    run_traffic,
)

HOSTS = ["host1", "host2", "host3", "host4"]
SMOKE_DURATION_S = 5
MIN_OBSERVED_BPS = 50_000_000  # aggregate floor to call it "measurable load"
FABRIC_MTU = 1500  # hosts default to 9500 (jumbo) but fabric links are 1500 -> MTU black hole


def _container(host: str) -> str:
    return f"clab-closcall-2s4l-{host}"


def _host_ip(host: str) -> str:
    return f"172.16.{host[-1]}.10"  # hostN -> 172.16.N.10 (per fabric.yaml host_subnet_template)


def _dexec(host: str, args: list[str], *, detach: bool = False, timeout: int = 30) -> str:
    cmd = ["docker", "exec", *(["-d"] if detach else []), _container(host), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def _start_servers(flows: list[Flow]) -> None:
    for dst, port in sorted({(f.dst, f.base_port) for f in flows}):
        _dexec(dst, ["iperf3", "-s", "-p", str(port), "-1"], detach=True)


def _cleanup() -> None:
    for host in HOSTS:
        _dexec(host, ["pkill", "-f", "iperf3"], timeout=10)


def prepare_hosts() -> None:
    """Normalize host eth1 MTU to the fabric MTU so large TCP/UDP isn't black-holed (latent bug)."""
    for host in HOSTS:
        _dexec(host, ["ip", "link", "set", "dev", "eth1", "mtu", str(FABRIC_MTU)])


def _iperf_runner(flow: Flow, profile: TrafficProfile) -> FlowResult:
    out = _dexec(
        flow.src,
        [
            "iperf3",
            "-c",
            _host_ip(flow.dst),
            "-p",
            str(flow.base_port),
            "-P",
            str(flow.streams),
            "-t",
            str(SMOKE_DURATION_S),
            "-b",
            str(profile.target_bitrate_bps),
            "-J",
        ],
        timeout=SMOKE_DURATION_S + 20,
    )
    try:
        end = json.loads(out)["end"]
        bps = float(end.get("sum_received", {}).get("bits_per_second", 0.0))
        retr = int(end.get("sum_sent", {}).get("retransmits", 0) or 0)
        rtt_us = end.get("streams", [{}])[0].get("sender", {}).get("mean_rtt", 0) or 0
        return FlowResult(flow, bps, retr, float(rtt_us) / 1000.0, completed=bps > 0)
    except (ValueError, KeyError, IndexError):
        return FlowResult(flow, 0.0, 0, 0.0, completed=False)


def main() -> int:
    profiles = yaml.safe_load((REPO / "configs" / "traffic-profiles.yaml").read_text())["profiles"]
    spec = profiles["collective_base"]
    profile = TrafficProfile(name="collective_base", **spec)
    flows = plan_flows(profile, HOSTS)
    print(f"traffic-smoke: profile={profile.name} pattern={profile.pattern} flows={len(flows)}")
    try:
        prepare_hosts()  # fix the MTU black hole before generating load
        _start_servers(flows)
        result = run_traffic(profile, HOSTS, _iperf_runner)
    finally:
        _cleanup()

    gbps = result.observed_bps / 1e9
    print(
        f"  offered={result.requested_bps / 1e9:.1f} Gbps  observed={gbps:.2f} Gbps  "
        f"completed={result.completed}/{result.flows}  retransmits={result.retransmits}  "
        f"rtt_mean={result.rtt_ms_mean:.2f}ms"
    )
    ok = result.observed_bps >= MIN_OBSERVED_BPS and result.completed > 0
    print(f"  {'PASS' if ok else 'FAIL'}: measurable load on the fabric")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
