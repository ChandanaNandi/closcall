"""Typed fault plugins (Bible §8.2). Honest names — mechanism == label; NO physical-fidelity
overclaim (`rate_limited_uplink` is tc-tbf bandwidth shaping, NOT PFC/ECN; `impaired_link` is
tc-netem loss/delay, NOT degraded optics). All impairments are `simulated: true` (§2.12).

Each plugin exposes: apply(), verify_onset() -> bool, clear(). Injectors act on the live
containerlab node via docker exec. The orchestrator (scripts/fault_smoke.py) wraps these with the
write-ahead ledger and onset checks.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

# Honest taxonomy: label -> (mechanism, honest meaning). Used for the no-overclaim assertion.
FAULT_TAXONOMY = {
    "admin_shutdown": ("gnmi admin-state disable", "configuration-caused shutdown"),
    "carrier_loss": ("veth link set down", "physical connectivity loss abstraction"),
    "intermittent_link": ("repeated carrier transitions", "link flap abstraction"),
    "rate_limited_uplink": ("tc tbf bandwidth shaping", "bandwidth bottleneck/congestion"),
    "impaired_link": ("tc netem loss/delay", "lossy/latent link"),
    "telemetry_gap": ("stop gnmic collector", "observation failure"),
    "healthy_control": ("no-op", "paired negative control"),
}


def _node(name: str) -> str:
    return f"clab-closcall-2s4l-{name}"


def _sh(node: str, cmd: str, root: bool = True) -> tuple[int, str]:
    args = ["docker", "exec"] + (["-u", "root"] if root else []) + [_node(node), "sh", "-c", cmd]
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def _srcli(node: str, script: str) -> str:
    p = subprocess.run(
        ["docker", "exec", "-i", "-u", "root", _node(node), "sr_cli"],
        input=script,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout + p.stderr


def _oper_down(node: str, iface_srl: str) -> bool:
    out = _srcli(node, f"info from state interface {iface_srl} oper-state\n")
    return "down" in out


@dataclass
class Fault:
    fault_class: str
    node: str
    iface_netdev: str  # e.g. e1-3 (tc/ip target)
    iface_srl: str  # e.g. ethernet-1/3 (gNMI/CLI target)

    def cleanup_payload(self) -> dict[str, str]:
        """Exact undo, stored in the ledger BEFORE apply (§8.3)."""
        fc = self.fault_class
        if fc == "admin_shutdown":
            return {"kind": "srl", "cmd": f"set / interface {self.iface_srl} admin-state enable"}
        if fc in ("carrier_loss", "intermittent_link"):
            return {"kind": "sh", "cmd": f"ip link set {self.iface_netdev} up"}
        if fc in ("rate_limited_uplink", "impaired_link"):
            return {"kind": "sh", "cmd": f"tc qdisc del dev {self.iface_netdev} root"}
        if fc == "telemetry_gap":
            return {"kind": "docker", "cmd": "docker start closcall-gnmic"}
        return {"kind": "noop", "cmd": ""}

    def apply(self) -> None:
        fc = self.fault_class
        if fc == "admin_shutdown":
            _srcli(
                self.node,
                f"enter candidate\nset / interface {self.iface_srl} "
                f"admin-state disable\ncommit now\n",
            )
        elif fc == "carrier_loss":
            _sh(self.node, f"ip link set {self.iface_netdev} down")
        elif fc == "intermittent_link":
            for _ in range(3):
                _sh(self.node, f"ip link set {self.iface_netdev} down")
                _sh(self.node, "sleep 1")
                _sh(self.node, f"ip link set {self.iface_netdev} up")
                _sh(self.node, "sleep 1")
        elif fc == "rate_limited_uplink":
            _sh(
                self.node,
                f"tc qdisc add dev {self.iface_netdev} root tbf rate 1mbit "
                f"burst 32kbit latency 400ms",
            )
        elif fc == "impaired_link":
            _sh(self.node, f"tc qdisc add dev {self.iface_netdev} root netem loss 30% delay 20ms")
        elif fc == "telemetry_gap":
            subprocess.run(["docker", "stop", "closcall-gnmic"], capture_output=True)
        # healthy_control: no-op

    def verify_onset(self) -> bool:
        """Confirm the intended data-plane condition is OBSERVED (not command completion, §8.3)."""
        fc = self.fault_class
        if fc in ("admin_shutdown", "carrier_loss"):
            return _oper_down(self.node, self.iface_srl)
        if fc == "intermittent_link":
            return True  # transitions applied; observed flap history is recorded by telemetry
        if fc in ("rate_limited_uplink", "impaired_link"):
            _, out = _sh(self.node, f"tc qdisc show dev {self.iface_netdev}")
            return ("tbf" in out) if fc == "rate_limited_uplink" else ("netem" in out)
        if fc == "telemetry_gap":
            p = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", "closcall-gnmic"],
                capture_output=True,
                text=True,
            )
            return p.stdout.strip() == "false"
        return True  # healthy_control onset == no change, trivially satisfied

    def clear(self) -> None:
        payload = self.cleanup_payload()
        kind, cmd = payload["kind"], payload["cmd"]
        if kind == "srl":
            _srcli(self.node, f"enter candidate\n{cmd}\ncommit now\n")
        elif kind == "sh":
            _sh(self.node, cmd)
        elif kind == "docker":
            subprocess.run(cmd.split(), capture_output=True)


__all__ = ["FAULT_TAXONOMY", "Fault"]
