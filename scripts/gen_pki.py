#!/usr/bin/env python3.12
"""Generate the local lab management PKI (Bible Gate 2 work item; §4 local dev CA).

Creates, under lab/pki/ (gitignored — never committed, I03 scan covers it):
  - ca/ca.crt, ca/ca.key           the lab-only development CA
  - <switch>/<switch>.crt/.key     per-switch gNMI server cert, SAN = hostname + mgmt IP

Regime (ADR-002 / threat-model A2): the CA private key is a host secret, never committed, never
logged. This material is EXCLUDED from the render determinism manifest (A04) because certs carry
random serials/keys — see docs and render.py. Certs are consumed when gNMI TLS is wired in Gate 3/4;
Gate 2 delivers the generation mechanism.

Uses the host `openssl` (recorded in docs/toolchain.md); no new Python dependency.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.domain.fabric import allocate, load_fabric  # noqa: E402

PKI = REPO / "lab" / "pki"
DAYS = "3650"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def gen_ca() -> tuple[Path, Path]:
    ca_dir = PKI / "ca"
    ca_dir.mkdir(parents=True, exist_ok=True)
    key, crt = ca_dir / "ca.key", ca_dir / "ca.crt"
    if not (key.exists() and crt.exists()):
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(crt),
                "-days",
                DAYS,
                "-subj",
                "/CN=ClosCall Lab CA/O=ClosCall",
            ]
        )
        key.chmod(0o600)
    return key, crt


def gen_node_cert(node: str, mgmt_ip: str, ca_key: Path, ca_crt: Path) -> None:
    d = PKI / node
    d.mkdir(parents=True, exist_ok=True)
    key, csr, crt = d / f"{node}.key", d / f"{node}.csr", d / f"{node}.crt"
    san = f"subjectAltName=DNS:{node},IP:{mgmt_ip}"
    run(
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(csr),
            "-subj",
            f"/CN={node}",
            "-addext",
            san,
        ]
    )
    run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(ca_crt),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(crt),
            "-days",
            DAYS,
            "-copy_extensions",
            "copyall",
        ]
    )
    key.chmod(0o600)
    csr.unlink()


def main() -> int:
    topo = allocate(load_fabric(REPO / "lab" / "fabric.yaml"))
    ca_key, ca_crt = gen_ca()
    switches = [n for n in topo.nodes if n.role in ("spine", "leaf")]
    for n in switches:
        gen_node_cert(n.name, n.management, ca_key, ca_crt)
    print(f"lab CA + {len(switches)} switch gNMI certs generated under lab/pki/ (gitignored)")
    print("CA private key is a host secret — never committed (threat-model A2, I03).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
