"""The executor's device access (Bible §13.3) — holds the sr_cli mutation capability.

Shared by the Gate 6 vertical slice and the Gate 14 UI server so remediation runs the exact same
way from either entry point. `discard stay` clears the SR Linux shared candidate first: a prior tool
(e.g. lab-check) can leave it dirty and make `commit now` fail. Injected as a `Device` protocol so
the credential boundary is explicit and the executor stays unit-testable with a fake.
"""

from __future__ import annotations

import subprocess


class FabricDevice:
    def get_oper_state(self, node: str, interface: str) -> str:
        p = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "root",
                f"clab-closcall-2s4l-{node}",
                "sr_cli",
                f"info from state interface {interface} oper-state",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "down" if "down" in p.stdout else ("up" if "up" in p.stdout else "unknown")

    def set_admin_state(self, node: str, interface: str, value: str) -> None:
        srl_val = "enable" if value == "enable" else "disable"
        script = (
            "enter candidate\ndiscard stay\n"
            f"set / interface {interface} admin-state {srl_val}\ncommit now\n"
        )
        subprocess.run(
            ["docker", "exec", "-i", "-u", "root", f"clab-closcall-2s4l-{node}", "sr_cli"],
            input=script,
            capture_output=True,
            text=True,
            timeout=30,
        )


__all__ = ["FabricDevice"]
