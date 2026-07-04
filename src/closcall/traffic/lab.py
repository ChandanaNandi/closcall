"""Lab-bound background traffic control for corpus collection (Bible §8.1; docker exec).

Starts the planned collective-shaped flows as BACKGROUND iperf3 processes on the host containers so
a fault can be injected while the fabric is under load — the condition gray/congestion faults need
to leave device-counter signatures. Not unit-tested (it drives real containers); the flow *planning*
it relies on is tested in `test_traffic.py`.
"""

from __future__ import annotations

import subprocess
import time

from closcall.traffic.generator import TrafficProfile, plan_flows

HOSTS = ["host1", "host2", "host3", "host4"]
FABRIC_MTU = 1500  # hosts default to 9500 (jumbo) vs 1500 fabric links -> MTU black hole (R31)


def _container(host: str) -> str:
    return f"clab-closcall-2s4l-{host}"


def _ip(host: str) -> str:
    return f"172.16.{host[-1]}.10"


def _dexec(host: str, args: list[str], *, detach: bool = False, timeout: int = 30) -> None:
    cmd = ["docker", "exec", *(["-d"] if detach else []), _container(host), *args]
    subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def prepare_hosts(hosts: list[str] = HOSTS) -> None:
    """Normalize host eth1 MTU to the fabric MTU so large TCP/UDP isn't black-holed (R31)."""
    for host in hosts:
        _dexec(host, ["ip", "link", "set", "dev", "eth1", "mtu", str(FABRIC_MTU)])


def stop_traffic(hosts: list[str] = HOSTS) -> None:
    for host in hosts:
        _dexec(host, ["pkill", "-f", "iperf3"], timeout=10)


def start_background_traffic(
    profile: TrafficProfile, duration_s: int, hosts: list[str] = HOSTS
) -> None:
    """Launch the planned flows as detached iperf3 processes running for `duration_s` seconds."""
    prepare_hosts(hosts)
    stop_traffic(hosts)  # clean slate
    flows = plan_flows(profile, hosts)
    for dst, port in sorted({(f.dst, f.base_port) for f in flows}):
        _dexec(dst, ["iperf3", "-s", "-p", str(port)], detach=True)
    time.sleep(1)  # let servers bind
    for flow in flows:
        _dexec(
            flow.src,
            [
                "iperf3",
                "-c",
                _ip(flow.dst),
                "-p",
                str(flow.base_port),
                "-P",
                str(flow.streams),
                "-t",
                str(duration_s),
                "-b",
                str(profile.target_bitrate_bps),
            ],
            detach=True,
        )


__all__ = ["HOSTS", "prepare_hosts", "start_background_traffic", "stop_traffic"]
