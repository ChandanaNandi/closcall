# ClosCall — Operator Guide / Runbook

Gate 13 handoff deliverable. This runbook walks a single operator through the ClosCall
lifecycle: environment bring-up, health verification, incident understanding, the
human-in-the-loop (HITL) approval flow, guarded execution with rollback/reconciliation,
teardown, and the known operational limitations.

**Ground rules for this document.** Every `make <target>` and CLI flag below was verified
against the repository's `Makefile` and source at the time of writing. Targets that the
`Makefile` stubs as "blocked — implemented at a later gate" are called out explicitly and
are **not** presented as runnable. Where a capability is waived or deferred, the guide says
so and points at the governing ADR. Do not infer that an unlisted command exists.

Scope reminder (ADR-002, threat-model §1/§10-A1): ClosCall is a **single-operator lab**
bound to loopback, with **no untrusted network callers**. A malicious human on the same
host or LAN is explicitly out of scope for core. See "Known limitations" at the end.

---

## 0. Prerequisites

- macOS host with Docker Desktop (canon runtime, ADR-002; not OrbStack).
- `python3.12` on the host PATH (used by `make doctor` before the venv exists).
- `uv` (project venv + dependency manager), and the pinned toolchain probed by `doctor`.
- Docker Desktop **file sharing restricted to the ClosCall repo directory only** — this is
  a load-bearing security condition (ADR-002). `make doctor` fails closed if any broader
  host tree (`/Users`, `/Volumes`, `/private`, `/tmp`, `/var/folders`) is reachable from
  inside the Docker VM.
- Postgres password is supplied via the `CLOSCALL_DB_PASSWORD` environment variable for
  any DB-touching target (migrations, corpus, manifest emission).

---

## 1. Environment bring-up

Run in order. Each target is non-interactive, returns non-zero on failure, and prints the
artifact/run IDs it creates.

### 1.1 Capability + boundary check
```
make doctor
```
Reports exact tool versions, Docker VM facts (kernel/arch/cpu/mem), disk headroom
(with the ≥60 GiB corpus-gate threshold as a WARN), and runs the **ADR-002 fail-closed
file-sharing probe**. If `doctor` FAILs on the boundary probe, stop and fix Docker Desktop
file sharing before proceeding — do not work around it.

### 1.2 Install the project
```
make bootstrap        # uv sync --frozen + pre-commit install
```

### 1.3 Database
```
make db-up            # docker compose up -d postgres
CLOSCALL_DB_PASSWORD=... make db-migrate   # alembic upgrade head
```

### 1.4 Lab fabric (2 spine / 4 leaf, "closcall-2s4l")
```
make render           # generate lab/generated/ config + manifest.json (offline)
make fabric-validate  # static validity of lab/fabric.yaml
make lab-up           # render + clab deploy; brings up closcall-2s4l
```
`lab-up` depends on `render`, so a bare `make lab-up` re-renders first. Optional offline
config-parse against the pinned SR Linux image: `make render-validate` (needs Docker +
the pinned image). PKI for lab management is host-local and gitignored: `make pki`.

### 1.5 Telemetry / observation plane
```
make telemetry-up     # docker compose up -d (Prometheus on http://127.0.0.1:9090, loopback)
```

---

## 2. Health verification

Bring the fabric and telemetry up first, then verify convergence before trusting any
downstream detection.

### 2.1 Network acceptance — `make lab-check`
Runs `scripts/lab_check.py` against the **running, converged** fabric. Reachability is
proven strictly over the **data plane** (host data IPs routed via the leaf, never the mgmt
network). Each check prints `[PASS]`/`[FAIL]` with evidence and contributes to the exit
code:

| Check | Meaning |
|-------|---------|
| **B03** | Expected BGP sessions are established (fabric underlay is up). |
| **B04** | RIB matches the IPAM plan (no missing/extra fabric prefixes). |
| **B05** | Import policy **behaviorally rejects** a forbidden prefix against the live RIB — not just a syntactic check (R17 #1). |
| **B06** | Two FIB next hops present (ECMP path diversity). |
| **B07** | Data-plane reachability host-to-host over the routed fabric. |
| **B08** | MTU boundary behaves as configured. |

Note: **B09 (ECMP distribution) is intentionally NOT in `lab-check`** — it sits behind an
integrity pre-registration gate and lives in its own module after sign-off. Don't expect it
here.

### 2.2 Telemetry acceptance — `make telemetry-check`
Runs `scripts/telemetry_check.py` against the running observation plane (assumes `lab-up` +
`telemetry-up`). It confirms: every node/eligible interface appears (C02); a known state
change is visible within a measured bound; **collector interruption is detected and blocks
automation** (C06/C07, fail-closed); and evidence snapshot hashes reproduce (C08). Writes
an evidence report to `evals/reports/gate4-telemetry.txt`.

### 2.3 Optional smoke checks
```
make traffic-smoke    # §8.1 traffic generator smoke (needs fabric up)
make fault-smoke      # fault-framework smoke campaign (needs fabric + telemetry up)
```

---

## 3. Understanding an incident: detection → localization → diagnosis

ClosCall's runtime pipeline is: telemetry/detector signal → **one incident** → localization
ranking → evidence-grounded diagnosis → drafted plan (HITL). The evaluation of that pipeline
is done offline over a frozen corpus; the read-only evaluation targets are:

### 3.1 Corpus (offline data plane)
```
make corpus-status    # where the corpus stands
make corpus           # run/extend the corpus
make corpus-verify    # integrity/consistency of the finished corpus
```

### 3.2 Detection, localization, manifest
```
make evaluate-sensors        # classical detection ensemble over the finished corpus (read-only)
make capture-baseline        # healthy fabric-wide baseline for localization
make evaluate-localization   # rule-baseline localization eval
make emit-manifest           # §9.4 dataset manifest binding the run
```
The v3 "under-load" release anchor is a **separate immutable lineage** (v2 targets
untouched):
```
make evaluate-sensors-v3     # scripts/evaluate_sensors_v3.py
make emit-manifest-v3        # scripts/emit_manifest_v3.py  (needs CLOSCALL_DB_PASSWORD)
make reports-v3             # scripts/consolidate_eval_v3.py -> evals/reports/gate12_5-evaluation.md
make readme-tables          # README results block + docs/RESULTS.md from the immutable v3 run id
```
Consolidated v2 report: `make reports`. Human-readable evaluation reports are written under
`evals/reports/` (e.g. `gate12_5-evaluation.md`, `gate9-detection.txt`,
`gate9-localization.txt`).

### 3.3 Incident correlation (behavior to expect)
`src/closcall/incidents/correlator.py`: a detector signal opens **exactly one** incident.
Concurrent/duplicate signals with the same `(source, source_event_id)` **attach** to the
existing incident (unique constraint + ON CONFLICT upsert) rather than spawning duplicates.
Every open/attach appends an incident event **and** an append-only audit row in the *same*
transaction.

### 3.4 LLM diagnosis qualification — `make qualify-llm`
```
make qualify-llm      # requires a running Ollama + candidate models
```
Runs each candidate Ollama model as the diagnostic workflow's *Hypothesizer* over a small
validation set plus a prompt-injection fixture, scoring: strict schema success, diagnosis
accuracy (validation only), abstention quality, tokens, latency, and injection resistance.
Report: `evals/reports/gate10-llm.txt`.

**Diagnosis safety invariant** (`src/closcall/workflow/diagnose.py`): the workflow commits a
diagnosis only if **all** its claims are `supported` by the deterministic verifier; otherwise
the outcome is an honest `undiagnosed` — never fabricated certainty. The LLM is an
**untrusted component**: it only proposes hypotheses, which the verifier gates; a drafted
plan maps a *verified* diagnosis class to an **allow-listed template id** — no untrusted text
and no evidence-derived free parameters reach the plan. If the LLM is unavailable, a
deterministic `RuleHypothesizer` fallback is used.

---

## 4. The HITL approval flow

> **Status note (honest).** The approval/executor logic is implemented as library modules
> with unit-test coverage (`src/closcall/api/`, `src/closcall/executor/`). The Makefile
> targets that would stand up the **live** service and worker — `api-up`, `executor-up`,
> `evaluate-agent`, `evaluate-e2e`, `nika`, `demo` — are currently **stubbed** and fail with
> "blocked — implemented at a later gate." So the flow below describes the enforced code
> path (what the modules guarantee and how tests exercise them), not a `make`-runnable live
> server. The `demo` runnable is being built separately.

### 4.1 The immutable plan (`src/closcall/executor/plan.py`)
A `Plan` is a frozen, content-addressed dataclass. Its `digest()` is a SHA-256 over the
canonical serialization of **every** field (actions, topology hash, pre/postconditions,
recovery predicate, rollback, risk class, provenance). Therefore **any** edit produces a
different digest, which **invalidates** any approval bound to the old digest — an edit
supersedes the old version (Bible §13.1). Each `Action` is one allow-listed verb with
bounded parameters (`action`, `node`, `interface`, `value`).

### 4.2 Authentication (`src/closcall/api/auth.py`)
Argon2id password hashing; a short-lived (**15-minute**) signed JWT (HS256) carried in a
cookie with `HttpOnly` + `Secure` + `SameSite=Strict`. No refresh token is stored — the
access token is re-issued on login. `verify_token` fails closed on bad signature, malformed
token, or expiry.

### 4.3 RBAC, CSRF, IDOR (`src/closcall/api/app.py`)
- **AuthN**: the session JWT cookie; missing/invalid → **401**.
- **RBAC**: role-gated dependencies. As implemented, `require_reader` admits
  `viewer`/`operator`/`approver`; the write action (`/incidents/{id}/ack`) requires
  `operator`. Wrong role → **403**.
- **CSRF**: double-submit. Login also sets a **non-HttpOnly** CSRF cookie; every
  state-changing request must echo it in the `X-CSRF-Token` header, compared in constant
  time. Missing/mismatch → **403**.
- **IDOR**: resource access is authorization-checked (the principal must be in the
  incident's `authorized_users`), not merely authenticated; unauthorized → **404** so
  existence is not leaked.

> **Discrepancy to note (honest).** The shipped API in `app.py` implements the roles
> `viewer` / `operator` / `approver`. The threat model and Contracts describe a
> `viewer` / `approver` / `auditor` / `admin` set and an approve/reject-by-exact-digest
> endpoint. The endpoint surface currently in `app.py` is `login` / `logout` / `me` /
> `GET incident` / `ack`; a dedicated approve-decision HTTP route is **not yet wired here**.
> The approval *binding* itself is enforced in the executor precheck (§5.1), where an
> `ApprovalDecision` row must exist for the exact `plan_digest` and version.

---

## 5. Execution + safety (`src/closcall/executor/`)

The executor is the **only** component that holds device-mutation capability. It has no
public ingress and accepts only a durable, approved job. The allowed action in the current
slice scope is narrow: **re-enable admin-state on a NON-management fabric interface** — the
safe reversal of an `admin_shutdown` fault (`ALLOWED_ACTIONS = {"set_admin_state"}`,
`ALLOWED_VALUES = {"enable"}`).

### 5.1 Fail-closed prechecks
Two layers exist; know which is which.

**(a) The full §13.2 suite — `executor/prechecks.py` (`run_prechecks`).** A pure function
over a `PrecheckContext`; `executable()` returns true only if **every** check passed
(fails closed). The 11+ checks:
1. valid approval for the **exact** digest **and** plan version;
2. no topology/config drift (`current_topology_hash == plan.topology_hash`);
3. **fresh, complete** telemetry;
4. action/parameters allow-listed;
5. target is **not** a management interface;
6. no competing execution on the target;
7. **alternate path healthy**;
8. remaining capacity **above configured headroom**;
9. change **cannot remove the final usable path**;
10. audit store and database writable;
11. recovery predicate defined **and** a rollback procedure captured.

**(b) The DB-integrated executor path — `executor/executor.py` (`_precheck`).** Before a
mutation, `execute_job` enforces a **subset**: a valid `approve` `ApprovalDecision` bound to
the exact `plan_digest`, the action/value allow-list, and the management-interface guard.

> **Gap to flag (honest).** The richer environment checks in layer (a) — drift, stale
> telemetry, last-path, headroom, competing-execution — are implemented and unit-tested as a
> pure suite, but `execute_job` in `executor.py` does **not** yet call `run_prechecks`; its
> inline `_precheck` covers approval-binding + allowlist + mgmt-interface only. Treat the
> full envelope as *specified and unit-proven* but *not yet wired end-to-end into the live
> mutation path*. This should be closed before any real device is targeted.

### 5.2 Execution semantics (what `execute_job` does)
1. **Competing-execution guard**: one execution per job (also a DB unique constraint);
   a second attempt returns `duplicate_ignored`.
2. **Pre-state capture**: reads `oper_state` before touching anything.
3. **Audit-write-first**: persists the mutation *intent* durably **before** touching the
   device. If the audit/DB write fails, `AuditUnavailable` is raised and the state change
   **never happens**.
4. **Smallest guarded mutation**: `set_admin_state(node, iface, "enable")`.
5. **Read-back**: reads `oper_state` again. `up` → `succeeded`; empty/`unknown` →
   `outcome_unknown` (**never** success); anything else → `failed`.
6. Writes an `Execution` row, a `RecoveryCheck` (`oper_state_up`), and an `execution.apply`
   audit event. Job status becomes `completed` on success, else `reconciling`.

### 5.3 Rollback (`executor/rollback.py`)
A **separate** state machine. It reverses the captured rollback actions for the **completed**
forward steps, in reverse order, and **only while rollback preconditions still hold**
(re-checked before *every* step). Any unsafe precondition, a raised actuator call, or a
failed read-back stops immediately and returns `halted_operator_required` with a reason — the
ambiguous/failed state stays visible and is never silently swallowed. Outcomes:
`rolled_back` / `halted_operator_required` / `not_needed`.

### 5.4 Reconciliation (`reconcile_job`)
On executor restart, a job left `running`/`reconciling` is reconciled against the
**authoritative device read** *before* any retry. Device `up` → `completed`;
empty/`unknown` → stays `reconciling` (visible, operator-owned — never silently marked done);
otherwise → `retryable_failed`. An `execution.reconcile` audit event records the resolution.

**Operator action:** any job sitting in `reconciling` requires you to inspect device state and
resolve it deliberately. It will not clear itself.

---

## 6. Teardown + residue verification

```
make lab-down         # clab destroy AND rm -rf lab/generated/clab-closcall-2s4l
make telemetry-down   # docker compose down
```
`lab-down` deliberately removes the containerlab working directory as well — leaving it behind
is a B12 residue failure (R18). After teardown, confirm no `clab-closcall-2s4l-*` containers
remain (`docker ps`) and that `lab/generated/clab-closcall-2s4l/` is gone. Re-run
`make doctor` if you changed Docker Desktop settings during the session.

---

## 7. Known operational limitations

Read these before relying on ClosCall for anything beyond the lab.

**A. Waived from core (ADR-001, Amendment A1 — hardening backlog, not shipped):**
- **Approval expiry and revocation** binding/blocking (H02/H03). An approval does not
  time out or get revoked; only an *edit* (new digest) invalidates it.
- **Multi-worker executor leasing + transactional outbox** (H06). Core is a single executor.
- **JWT rotation/revocation infrastructure and rate limits** (I02). Secure cookie, CSRF,
  JWT claims, RBAC, and IDOR **remain core**; rotation/rate-limiting do not.
- **Cryptographic tamper-evident audit hash chain** (I05). Append-only audit with FK
  integrity remains core; a hash chain does not.
- **Full multi-service restart matrix** (J03). Executor + PostgreSQL restart determinism
  remains core; the broader matrix does not.
- **Backup/restore program** (J04).

Rationale (ADR-001): single-operator lab, no untrusted callers; these add zero evaluation
rows and materially delay completion. They may return to core **only** by a superseding ADR.

**B. Lab runtime boundary (ADR-002):** lab isolation depends on Docker Desktop file sharing
being restricted to the repo directory only. ClosCall does **not** defend against a
host-privileged attacker: a `--privileged` container plus broad host file-sharing would make
host files reachable. The primary controls are (1) emptied file-sharing surface (repo path
only) and (2) no blanket `--privileged` for lab containers. This is **not** equivalent to a
dedicated hypervisor VM; `make doctor` is the fail-closed gate that enforces it.

**C. Same-host trust assumption (threat-model §1 / §10 A1):** a malicious human on the same
host or LAN is **out of scope for core**. Loopback binding is the only claimed control at
that boundary. Prometheus (`127.0.0.1:9090`) and the API are loopback-only by design.

**D. Not-yet-runnable surfaces:** `api-up`, `executor-up`, `evaluate-agent`, `evaluate-e2e`,
`nika`, and `demo` are stubbed in the `Makefile` and fail explicitly rather than pretending
to run. The HITL/executor **logic** exists and is unit-tested, but there is no `make` target
that stands up the live API + executor against a real device today (see §4/§5 status notes).

---

## Appendix — sources read to document each flow

- **Make targets / runnability**: `Makefile` (the `NOT_READY` sentinel and its target list).
- **Bring-up + boundary probe**: `scripts/doctor.py`, `ADR-002-lab-runtime-boundary.md`.
- **B03-B08 health checks**: `scripts/lab_check.py` (docstring + `check_b03..b08`).
- **Telemetry health**: `scripts/telemetry_check.py`.
- **Incident correlation**: `src/closcall/incidents/correlator.py`.
- **Diagnosis / LLM qualification**: `src/closcall/workflow/diagnose.py`,
  `scripts/qualify_llm.py`.
- **Immutable plan / digest**: `src/closcall/executor/plan.py`.
- **AuthN / RBAC / CSRF / IDOR**: `src/closcall/api/auth.py`, `src/closcall/api/app.py`.
- **Prechecks (full suite)**: `src/closcall/executor/prechecks.py`.
- **Execution / reconciliation**: `src/closcall/executor/executor.py`.
- **Rollback**: `src/closcall/executor/rollback.py`.
- **HITL / executor spec**: `planning/03-Canonical-Execution-Bible.md` §13.1-13.3.
- **Waivers + assumptions**: `docs/decisions/ADR-001-scope-waivers.md`,
  `docs/threat-model.md` §1 / §7 / §10.

### Items I could NOT fully confirm in code (flagged in-line above)
1. **Full §13.2 precheck suite is not wired into the live mutation path.**
   `executor.py::execute_job` calls its own inline `_precheck` (approval-binding + allowlist +
   mgmt-interface only); the drift / stale-telemetry / last-path / headroom /
   competing-execution checks live in `prechecks.py::run_prechecks` (pure, unit-tested) but are
   not invoked by `execute_job`. Documented as specified-and-unit-proven, not end-to-end wired.
2. **Role set + approve endpoint discrepancy.** `app.py` implements `viewer`/`operator`/
   `approver` and exposes `login`/`logout`/`me`/`GET incident`/`ack`. The Contracts/threat-model
   describe `viewer`/`approver`/`auditor`/`admin` and an approve/reject-by-digest route; that
   HTTP route is not present in `app.py`. Approval binding is enforced at the executor precheck
   via the `ApprovalDecision` row, not (yet) via a dedicated API endpoint.
3. **Live HITL surface (Gate 14 update).** `demo`, `api-up`, `api-seed`, `api-smoke` now run; the
   browser approval UI is live (see §8). `executor-up` remains `NOT_READY` (the UI runs the executor
   in-process, D1). `tests/integration|security|failure` are still empty — the UI is covered by
   `tests/unit/test_ui.py` (incl. the no-side-door test) and the clean-clone `make api-smoke`.

## 8. Approving via the browser UI (Gate 14)

- `make api-up` seeds login users and serves the HITL UI on **loopback HTTPS** (lab PKI) at
  `https://127.0.0.1:8443/ui/login`. Users: `viewer1` / `operator1` / `approver1`, password
  `CLOSCALL_SEED_PASSWORD` (default `closcall-demo`). Accept the self-signed lab cert.
- The front door (`/ui/`) is a **results dashboard**: the study's headline (detection blind to gray
  faults; learned localization recovers them), corpus scale, the per-class AUROC chart with CIs, and
  the safety architecture — every number parsed live from the content-hashed artifacts the v3
  manifest binds (J07; never hand-typed).
- Flow: incident list → case file (evidence, localized link, drafted plan + digest) → **Approve /
  Edit / Reject** (approver role only). Approve drives the SAME `execute_job` as the vertical slice.
- **Honest labels shown in the UI itself:** a sticky banner directly above the approve button states
  the live executor enforces only approval-binding + allowlist + mgmt-interface, and that the full
  fail-closed suite is not wired to the live path (H07 / ADR-004). Server start prints the D1 note
  (in-process executor; production would use the durable job queue — backlogged).
- **No side door:** the approve action re-runs the approval↔digest binding and refuses a mismatched
  or absent approval (`tests/unit/test_ui.py::test_side_door_tampered_digest_refused_and_no_mutation`).
- `make api-smoke` proves the whole flow clean-clone (login → list → case file → approve) with a fake
  device, no live lab. Auth is the Gate 11 JWT carried in an httpOnly cookie (transport-only, ADR-005).
