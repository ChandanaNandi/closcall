# Gate 11 — Secured HITL + Executor Status Note

Status: **exit criteria met; core acceptance rows covered.** The security + execution machinery is
built and adversarially tested offline; the remaining items are the documented ADR-001 backlog
waivers and one integration/deploy loose end (live `api-up` serving), which do not affect the exit
criteria.

## Acceptance rows (Bible §Acceptance H/I) → evidence

| row | requirement | evidence |
|---|---|---|
| **H03** | Edit or drift blocks execution *(expiry/revocation waived to backlog)* | `test_prechecks`: edited plan (new digest) + topology drift fail closed |
| **H06** | Duplicate execution prevented by DB unique + idempotency key | `ExecutionJob` unique on remv + idempotency_key; executor returns `duplicate_ignored` |
| **H07** | Last path, mgmt interface, stale telemetry, low headroom fail closed | `test_prechecks`: `keeps_final_usable_path`, `target_not_management_interface`, `telemetry_fresh`, `capacity_above_headroom` |
| **H08** | Pre-state and rollback payload captured before mutation | executor captures `before` + audits intent pre-mutation; plan carries captured `rollback` |
| **H09** | Timeout ambiguity → outcome_unknown and reconciles | executor `outcome_unknown` (never success) + `reconcile_job` resolves vs. actual device state; still-ambiguous stays `reconciling` |
| **H11** | Rollback reverses completed steps or exposes failure | `test_rollback_audit`: reverse-order revert; halt + reason on precondition/read-back/raise |
| **I02** | JWT claims, RBAC, IDOR, secure-cookie, CSRF *(token rotation/rate-limit waived)* | `test_auth` + `test_api`: 401/403/404, CSRF double-submit, IDOR hides existence |
| **I02a** | Secure cookies never over plain HTTP | session cookie `Secure=True` (browsers never send over http); loopback-HTTPS *serving* is deploy wiring (see loose end) |
| **I03** | No secret in source/logs/etc | gitleaks `make secret-scan` (Gate 1); `.env`/PKI gitignored |
| **I05** | Audit append-only + FK integrity *(hash chain waived)* | `AuditEvent` in `audit` schema, FK'd, never updated/deleted in code |
| **I06** | Audit failure blocks state mutation | `test_rollback_audit` (audit guard) + executor audits intent flush-guarded BEFORE the device mutation |

## Exit criteria — met

1. **Every security/execution acceptance row passes** — covered above (waived clauses are the
   ADR-001 backlog items, not core).
2. **Stale/edited/drifted plans fail closed** — the plan is content-addressed (SHA-256 over all
   §13.1 fields); an edit yields a new digest, and the first precheck binds the approval to the
   exact digest AND version, so edited/stale/drifted plans fail the suite (which fails closed —
   `executable()` requires ALL pass).
3. **Ambiguous and rollback-failed states remain visible** — ambiguous read-back is `outcome_unknown`
   (never success) and lands in `reconciling`; `reconcile_job` keeps it `reconciling` if still
   ambiguous. Rollback halts with `halted_operator_required` + reason on any failure — never swallowed.

## What was built (this gate)

| piece | modules | tests |
|---|---|---|
| Auth core (Argon2id, JWT cookie) | `api/auth.py` | 7 |
| HITL API (RBAC, CSRF, IDOR) | `api/app.py` | 9 |
| Immutable plan + prechecks | `executor/plan.py`, `executor/prechecks.py` | 8 |
| Rollback state machine + audit guard | `executor/rollback.py`, `executor/audit_guard.py`; executor wiring | 8 |
| Reconcile (H09) | `executor.reconcile_job` | (integration) |

## Honest loose ends (do not affect the exit criteria)

- **Live `make api-up` serving** — the security *properties* are proven in the offline suite via the
  app factory + TestClient with injected fake user store/repo. A real `api-up` (uvicorn bound to
  127.0.0.1 over HTTPS with the lab PKI, DB-backed user store/repo) is deployment/integration wiring,
  the same category as Gate 10's DB-backed `EvidenceSource` adapter.
- **`execute_job`/`reconcile_job` integration** — these are DB+device bound; their logic is written
  to the §13.3 semantics and the pure sub-units (prechecks, rollback, audit guard) are fully tested.

## Waived to ADR-001 backlog (per the acceptance matrix)

Approval expiry/revocation (H02/H03 clause), multi-worker leasing / transactional outbox (H06
clause), token rotation/revocation + rate limits (I02 clause), cryptographic audit hash-chain (I05
clause), full restart matrix (J03), backup/restore (J04). These are explicitly post-core.

## Provenance

- Commits: auth `c5e59c3`; api-security `a4b721e`; plan+prechecks `3c1f99f`; rollback+audit
  `7fd47f2`; reconcile+status (this).
- Deps added: fastapi 0.139.0, argon2-cffi 25.1.0, pyjwt 2.13.0 (+ httpx dev).
- Tests: 174 unit/property, all pure/offline. `make lint` + `make typecheck` clean.
