#!/usr/bin/env python3.12
"""Gate 3 acceptance orchestrator: run the full §7.3 suite TWICE from clean deployment.

Exit criterion (Bible Gate 3): all network acceptance criteria pass twice from clean deployment,
with packet-loss/convergence evidence retained. Each run: deploy fresh -> converge -> B03-B08
(lab_check) -> B09 (ECMP) -> B10/B11 (reconvergence) -> teardown -> B12 residue. Per-run evidence
is written to evals/reports/gate3-run<N>.txt. No warm state carries between runs.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "evals" / "reports"


def run(cmd: str, timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=REPO)
    return p.returncode, p.stdout + p.stderr


def sr_ready() -> bool:
    rc, _ = run(
        "docker exec -u root clab-closcall-2s4l-leaf1 sr_cli "
        '"info from state system information version"',
        timeout=60,
    )
    return rc == 0


def one_run(n: int) -> tuple[bool, str]:
    log: list[str] = [f"===== Gate 3 acceptance — clean run {n} ====="]

    run("make lab-down")
    run("docker network ls --filter name=closcall -q | xargs -r docker network rm")
    rc, out = run("make lab-up", timeout=300)
    log.append(out.strip().splitlines()[-1] if out.strip() else "(lab-up)")
    if rc != 0:
        return False, "\n".join([*log, "DEPLOY FAILED"])

    for _ in range(60):
        if sr_ready():
            break
        time.sleep(3)
    time.sleep(10)

    passed = True
    for name, script in (
        ("B03-B08", "scripts/lab_check.py"),
        ("B09", "scripts/b09_ecmp.py"),
        ("B10-B11", "scripts/b10_b11_convergence.py"),
    ):
        rc, out = run(f"uv run python {script}", timeout=600)
        passed = passed and rc == 0
        log.append(f"--- {name} (rc={rc}) ---")
        log.append(out.strip())

    run("make lab-down")
    rc, out = run("uv run python scripts/b12_teardown.py")
    passed = passed and rc == 0
    log.append(f"--- B12 (rc={rc}) ---")
    log.append(out.strip())

    log.append(f"===== run {n}: {'ALL PASS' if passed else 'FAILURES PRESENT'} =====")
    return passed, "\n".join(log)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    results = []
    for n in (1, 2):
        ok, report = one_run(n)
        (REPORTS / f"gate3-run{n}.txt").write_text(report + "\n")
        print(f"run {n}: {'PASS' if ok else 'FAIL'}  -> evals/reports/gate3-run{n}.txt")
        results.append(ok)
    both = all(results)
    print(f"== Gate 3 acceptance: {'BOTH RUNS PASS' if both else 'NOT ALL PASS'} ==")
    return 0 if both else 1


if __name__ == "__main__":
    sys.exit(main())
