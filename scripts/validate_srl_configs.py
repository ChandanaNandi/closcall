#!/usr/bin/env python3.12
"""Offline SR Linux config-parse check (Gate 2 exit evidence).

Renders the fabric, boots ONE throwaway SR Linux 25.3.3 node, and runs `commit validate` on each
rendered switch config (validates syntax/semantics WITHOUT persisting — every config checked
independently on one node). Tears the node down. Requires Docker + the pinned image.

IMPORTANT boundary (per pilot ruling): this proves each config *commits cleanly on the release*.
It says NOTHING about routing, convergence, or reachability — that is Gate 3. A committed config is
not a converged fabric.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.domain.fabric import load_fabric  # noqa: E402
from closcall.domain.render import SRL_IMAGE, render_all  # noqa: E402

NODE = "srl-cfgcheck"


def sh(cmd: str, timeout: int = 300) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def sr_cli(node: str, script: str, timeout: int = 120) -> str:
    """Feed a multi-line CLI script to sr_cli via stdin (no shell escaping)."""
    p = subprocess.run(
        ["docker", "exec", "-i", "-u", "root", node, "sr_cli"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return p.stdout + p.stderr


def main() -> int:
    out_dir = REPO / "lab" / "generated"
    files = render_all(load_fabric(REPO / "lab" / "fabric.yaml"), out_dir)
    configs = sorted(f for f in files if f.endswith(".cli"))
    print(f"rendered {len(configs)} switch configs")

    sh(f"docker rm -f {NODE}")
    sh(
        f"docker run -d --name {NODE} --privileged --hostname {NODE} {SRL_IMAGE} "
        f'sudo bash -c "touch /.dockerenv && /opt/srlinux/bin/sr_linux"'
    )
    print("booting node; waiting for authorized CLI...")
    rc, _ = sh(
        f'until docker exec -u root {NODE} sr_cli "info from state system information version" '
        f">/dev/null 2>&1; do sleep 3; done",
        timeout=420,
    )
    if rc != 0:
        print("FAIL: node CLI did not become ready")
        sh(f"docker rm -f {NODE}")
        return 1

    ok = 0
    for cfg in configs:
        sh(f"docker cp {out_dir / cfg} {NODE}:/tmp/{cfg}")
        script = f"enter candidate\nsource /tmp/{cfg}\ncommit validate\ndiscard stay\n"
        out = sr_cli(NODE, script)
        if "All changes are valid" in out:
            print(f"  {cfg}: VALIDATE OK")
            ok += 1
        else:
            errs = [
                ln
                for ln in out.splitlines()
                if any(w in ln.lower() for w in ("error", "invalid", "fail"))
            ]
            print(f"  {cfg}: FAIL -> {errs[:3]}")

    sh(f"docker rm -f {NODE}")
    print(f"== {ok}/{len(configs)} configs commit cleanly on SR Linux 25.3.3 ==")
    return 0 if ok == len(configs) else 1


if __name__ == "__main__":
    sys.exit(main())
