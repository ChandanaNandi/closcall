#!/usr/bin/env python3.12
"""``make doctor`` — report exact machine capabilities and enforce the ADR-002
lab-runtime boundary check.

Stdlib only, run with the host ``python3.12`` (not the project venv), so it works
on a fresh clone before ``bootstrap``. Prints one line per check with a status
tag and exits non-zero if any hard check FAILs. WARN never fails the run.

Checks:
- required tools present, with exact versions (Bible §4 "verify, don't assume");
- Docker daemon reachable + VM facts (kernel/arch/cpu/mem);
- ADR-002 file-sharing probe: FAIL-CLOSED if any host tree is reachable from a
  privileged container via the VM init mount namespace;
- disk headroom, with the >=60 GiB corpus-gate threshold (R10) reported as WARN.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

# Pinned probe image (digest recorded in docs/toolchain.md). "latest" is forbidden.
PROBE_IMAGE = "alpine@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce"

# Host trees that must NOT be present inside the VM after ADR-002 file-sharing is emptied.
HOST_TREES = ("Users", "Volumes", "private", "tmp", "var", "host")

CORPUS_MIN_FREE_GIB = 60  # R10 ruling: corpus blocked below this.

_fail = 0
_warn = 0


def _emit(status: str, name: str, detail: str) -> None:
    global _fail, _warn
    if status == "FAIL":
        _fail += 1
    elif status == "WARN":
        _warn += 1
    print(f"[{status:4}] {name}: {detail}")


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def check_tools() -> None:
    tools = {
        "git": ["git", "--version"],
        "python3.12": ["python3.12", "--version"],
        "uv": ["uv", "--version"],
        "docker": ["docker", "--version"],
        "caddy": ["caddy", "version"],
        "gitleaks": ["gitleaks", "version"],
        "syft": ["syft", "version"],
        "trivy": ["trivy", "--version"],
    }
    for name, cmd in tools.items():
        if shutil.which(cmd[0]) is None:
            _emit("FAIL", f"tool {name}", "not on PATH")
            continue
        rc, out = _run(cmd, timeout=30)
        lines = out.splitlines()
        # Prefer the first line that carries a version number (syft prints
        # "Application: syft" before its "Version:" line).
        detail = next((ln.strip() for ln in lines if any(c.isdigit() for c in ln)), "")
        _emit("PASS" if rc == 0 else "FAIL", f"tool {name}", detail or f"exit {rc}")


def check_docker_vm() -> bool:
    rc, out = _run(
        ["docker", "info", "--format", "{{.ServerVersion}} {{.OSType}}/{{.Architecture}} "
         "NCPU={{.NCPU}} MemBytes={{.MemTotal}}"],
        timeout=30,
    )
    if rc != 0:
        _emit("FAIL", "docker daemon", "not reachable (is Docker Desktop running?)")
        return False
    _emit("PASS", "docker daemon", out)
    rc, kern = _run(["docker", "run", "--rm", PROBE_IMAGE, "uname", "-rm"], timeout=120)
    _emit("PASS" if rc == 0 else "FAIL", "vm kernel", kern if rc == 0 else "probe failed")
    return True


def check_file_sharing() -> None:
    """ADR-002: assert no host tree is reachable from the VM init namespace."""
    rc, out = _run(
        ["docker", "run", "--rm", "--privileged", "--pid=host", PROBE_IMAGE,
         "nsenter", "-t", "1", "-m", "sh", "-c",
         "mount | grep -oE '/host_mnt/[A-Za-z0-9._-]+' | sort -u"],
        timeout=120,
    )
    if rc not in (0, 1):  # 1 = grep found nothing (good); other = probe broke
        _emit("FAIL", "file-sharing probe", f"could not verify (exit {rc}): {out[:120]}")
        return
    reachable = [
        line.strip()
        for line in out.splitlines()
        if any(line.strip().endswith(f"/{t}") or f"/host_mnt/{t}" == line.strip() for t in HOST_TREES)
    ]
    if reachable:
        _emit("FAIL", "file-sharing probe",
              f"host trees reachable in VM: {', '.join(reachable)} — "
              "empty Docker Desktop file sharing (ADR-002)")
    else:
        _emit("PASS", "file-sharing probe", "no host trees reachable from VM (ADR-002)")


def check_disk() -> None:
    usage = shutil.disk_usage("/")
    free_gib = usage.free / (1024**3)
    detail = f"{free_gib:.0f} GiB free of {usage.total / (1024**3):.0f} GiB"
    if free_gib < CORPUS_MIN_FREE_GIB:
        _emit("WARN", "disk headroom",
              f"{detail} — corpus gate needs >= {CORPUS_MIN_FREE_GIB} GiB (R10); OK for non-corpus gates")
    else:
        _emit("PASS", "disk headroom", detail)


def main() -> int:
    print("== ClosCall doctor ==")
    check_tools()
    if check_docker_vm():
        check_file_sharing()
    else:
        _emit("FAIL", "file-sharing probe", "skipped — docker daemon unreachable")
    check_disk()
    print(f"== {_fail} fail, {_warn} warn ==")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
