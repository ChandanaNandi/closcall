"""Gate 13 clean-clone demo (acceptance row J06): deploy -> diagnose -> remediate -> teardown.

Drives the whole system end-to-end from a clean state and tears the lab down afterward, with NO
hidden manual repair — every step is a canonical `make` target or the deterministic vertical slice.
The stages:

  1. fabric-validate      offline machine-readable fabric check (B01)
  2. db-up + db-migrate    Postgres up and schema migrated
  3. lab-up                render configs + deploy the containerlab SR Linux fabric
  4. lab-check             network acceptance B03-B08 on the converged fabric
  5. vertical-slice        the LIVE deterministic happy path:
                inject admin_shutdown -> rules detect -> idempotent correlator opens ONE incident
                -> typed-claim evidence -> diagnosis -> immutable plan (SHA-256 digest) -> approval
                + durable job (same txn) -> **isolated executor runs LIVE** (real sr_cli set
                admin-state enable -> read-back -> recovery -> audit chain). The injector's cleanup
                is NEVER the remediation.
  6. reports-v3 + readme    regenerate the immutable v3 evaluation bundle + README numbers
  7. lab-down              teardown (ALWAYS runs — deploy-to-teardown, no residue: B12)

HONEST SCOPE (labeled, not hidden):
  * The executor runs LIVE for the allowlisted, safe action only — re-enabling admin-state on a
    non-management fabric interface (the reversal of admin_shutdown). It enforces the NARROWER
    precheck subset (approval-digest + allowlist + mgmt-interface). The full §13.2 fail-closed suite
    (last-path / headroom / stale-telemetry / drift) is built and unit-tested but not yet wired to
    the live path — see docs/decisions/ADR-004-h07-precheck-wiring-waiver.md.
  * There is NO live HTTP API server in this demo (`api-up`/`executor-up` are backlog). The HITL
    approval is exercised through the durable DB plan/approval/job records, not a browser session.

Non-interactive; returns non-zero if any stage fails (teardown still runs). Set DEMO_KEEP=1 to skip
the final teardown for inspection.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_env() -> None:
    """Populate CLOSCALL_DB_PASSWORD from .env if unset (best-effort; clean-clone convenience)."""
    if os.environ.get("CLOSCALL_DB_PASSWORD"):
        return
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def banner(n: int, total: int, title: str) -> None:
    print(f"\n{'=' * 72}\n[demo {n}/{total}] {title}\n{'=' * 72}", flush=True)


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=REPO).returncode


def main() -> int:
    load_env()
    t0 = time.monotonic()
    print("ClosCall - clean-clone demo (J06): deploy -> diagnose -> remediate -> teardown")
    print("executor scope: LIVE admin_shutdown reversal, narrower H07 subset (ADR-004);")
    print("HITL via durable DB records (no live HTTP API server - that is backlog).")

    # A clean start makes the demo idempotent regardless of prior residue (on a true clean clone
    # these are no-ops). Not hidden repair: explicit, logged teardown-before-deploy. telemetry-down
    # is required BEFORE lab-up: gnmic/prometheus sit on the closcall-mgmt network and squat the
    # spine mgmt addresses; the fabric must deploy on a free mgmt network first (deploy order).
    stages: list[tuple[str, list[str]]] = [
        ("fabric-validate (B01 offline)", ["make", "fabric-validate"]),
        ("clean-start: teardown residual lab", ["make", "lab-down"]),
        ("clean-start: free mgmt net (telemetry-down)", ["make", "telemetry-down"]),
        ("db-up", ["make", "db-up"]),
        ("db-migrate", ["make", "db-migrate"]),
        ("lab-up (render + deploy fabric)", ["make", "lab-up"]),
        ("lab-check (B03-B08)", ["make", "lab-check"]),
        ("vertical-slice (LIVE inject->diagnose->execute->audit)", ["make", "vertical-slice"]),
        ("reports-v3 (immutable v3 eval bundle)", ["make", "reports-v3"]),
        ("readme-tables (regenerate README numbers)", ["make", "readme-tables"]),
    ]
    total = len(stages) + 1  # + final teardown

    failed_stage: str | None = None
    for i, (title, cmd) in enumerate(stages, start=1):
        banner(i, total, title)
        if run(cmd) != 0:
            failed_stage = title
            print(f"\n[demo] STAGE FAILED: {title}", flush=True)
            break

    # teardown ALWAYS (deploy-to-teardown; no residue) unless explicitly kept
    if os.environ.get("DEMO_KEEP") == "1":
        print("\n[demo] DEMO_KEEP=1 - skipping teardown (lab left running for inspection)")
    else:
        banner(total, total, "lab-down (teardown, always runs)")
        if run(["make", "lab-down"]) != 0:
            print("[demo] WARNING: teardown returned non-zero - check for residue (B12)")

    dt = time.monotonic() - t0
    if failed_stage:
        print(f"\n[demo] FAILED at: {failed_stage}  ({dt:.0f}s elapsed)")
        return 1
    print(f"\n[demo] COMPLETE: deploy->diagnose->remediate->teardown, no manual repair ({dt:.0f}s)")
    print("  evidence: evals/reports/gate6-slice.txt (live slice) + gate12_5-evaluation.md (eval)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
