# ADR-004 — H07 full precheck-suite live wiring waived to backlog (Amendment A2)

Status: accepted
Date: 2026-07-05 (Gate 13)

## Context
Acceptance row **H07** requires: *"Last path, management interface, stale telemetry, and low headroom
fail closed."* The full §13.2 precheck suite `run_prechecks` (`src/closcall/executor/prechecks.py`)
implements all twelve checks — including `keeps_final_usable_path`, `alternate_path_healthy`,
`capacity_above_headroom`, `telemetry_fresh_and_complete`, and `no_topology_drift` — and is
unit-tested to fail closed (`tests/unit/test_prechecks.py`).

During Gate 13 packaging a gap was found: the **live** device-mutation path
(`executor.execute_job` → `_precheck`) enforces only a **narrower subset** of these checks —
approval-binding to the exact plan digest/version, the action/value allowlist, and the
management-interface guard. It does **not** call `run_prechecks`. Two reasons it is not a quick wire:

1. **Plan representation mismatch.** `execute_job` stores the plan as a flat dict
   `rv.plan_json = {action, value, node, interface}`; `run_prechecks` consumes a structured `Plan`
   object (`.actions[]`, `.topology_hash`, `.plan_version`, `.recovery_predicate`, `.rollback`) that
   has no `from_json` deserializer.
2. **No real fact providers.** Every environment fact in `PrecheckContext` exists today only as a
   hardcoded test fixture. There is no code that computes a live topology-hash read, telemetry
   freshness/completeness, alternate-path health, capacity headroom, or the final-path check.

Wiring the call quickly by feeding hardcoded `True` context would be **safety theater** — the suite
would "run" while every real check is a no-op, strictly worse than the honest narrow precheck. Doing
it properly is an afternoon of risky work on the sole device-mutation path, with no integration-test
scaffold (`tests/integration|security|failure|e2e` are empty) to catch regressions.

## Decision
Waive the **full-suite live wiring** of H07 to the hardening backlog. The live execution path keeps
its honest narrow subset (approval-digest + allowlist + mgmt-interface). H07 is downgraded from green
to **PARTIAL** in the acceptance matrix and stated plainly as a limitation. Nothing is claimed that
the live path does not enforce.

Explicitly deferred (backlog), the minimum to fully green H07:
- a `Plan` deserializer reconciling `rv.plan_json` with the structured `Plan`;
- five real `PrecheckContext` fact providers: live topology-hash, telemetry freshness/completeness,
  alternate-path health, capacity headroom, final-usable-path check;
- an integration test proving `execute_job` fails closed on the live path when any provider trips.

## Alternatives considered
- **Wire it now with stubbed context.** Rejected: safety theater; falsely green.
- **Rush the honest wiring to hit Gate 13.** Rejected: security-critical code under finish-line
  pressure, no test scaffold — the wrong tradeoff for a demo step already decided to be simulated.

## Consequences
- The release README/LIMITATIONS and the traceability map must state the H07 subset precisely.
- The clean-clone demo (J06) simulates the executor step offline; it does not exercise a live device
  mutation, consistent with this waiver.
- The full suite is already built and unit-tested; promotion back to core is a wiring + provider +
  integration-test task, not a redesign. Promotion requires a superseding ADR.
