# ClosCall — Project Home
### Evidence-grounded incident command for AI datacenter fabrics.

<!-- BEGIN GENERATED: results (make readme-tables) -->
## Results (v3 under-load anchor)

*Generated from immutable run id `dd8def51705710fa...` (`gate8-full-corpus-v3`, code `8dd27542a424`). Regenerate:
`make readme-tables`. Full tables: [`docs/RESULTS.md`](docs/RESULTS.md).*

**Thesis, on real under-load data:** classical single-interface detection is blind to *gray* faults;
relational/temporal learned *localization* recovers them.

| study | result |
|---|---|
| Detection (test, classical ensemble) | recall **0.60** (78/130 faults) - blunt only; gray = 0 (structural blind spot, even under load) |
| Localization AUROC, `rate_limited_uplink` | rule 0.500 -> MLP 0.910 / GNN 0.907 |
| Localization AUROC, `impaired_link` | rule 0.500 -> MLP 0.910 / GNN 0.721 |
| Localization AUROC, blunt faults | rule ~0.92 -> learned ~0.94-0.996 |

Gray-fault localization is recovered from throughput instability (temporal) + cross-link comparison
- structure a single-interface detector cannot use. Honest limits (gray top-1, healthy control at
chance) are in [`docs/RESULTS.md`](docs/RESULTS.md).
<!-- END GENERATED: results -->


## Document canon (precedence on conflict — highest wins)
1. `planning/05-Acceptance-Matrix.md` — what "done" measurably means (AMENDED A1: waivers marked in-document per its Master release rule)
2. `planning/04-Data-API-and-State-Contracts.md` — schemas, APIs, and core state machines
3. `planning/03-Canonical-Execution-Bible.md` — the execution plan (Gates 0–13)
4. `planning/02-Build-Bible.md` — superseded where it conflicts with 03/04; retained for rationale
5. `planning/01-Project-Spec.md` — positioning, evaluation philosophy, related work (authoritative for WHY)
- `docs/decisions/` — ADRs (ADR-001 = scope waivers)
- `docs/backlog.md` — hardening backlog (exists; deferred items live here)
- `research/research-log.md` + `research/source-register.md` — evidence trail, append-only

## Scope status
The A1 scope ruling is now PROPAGATED into document 05 itself (waived rows marked, ADR-001 attached,
backlog created) — the deferral is no longer a README-only note and the canon is internally consistent.
Core keeps: causal ML windows and all leakage protections; honest fault taxonomy; remediation as
operational response separate from chaos cleanup (alternate-capacity + last-path checks); edge-level GNN
ranking; out-of-fold TS scores; typed-predicate claim verification; executable schema; designed dedup;
immutable plan digest bound to approval; pre-state capture; outcome_unknown reconciliation; isolated
executor; secure-cookie authentication with CSRF; specified rules baseline; RIB/FIB + ECMP
validation; timestamp discipline; measurement-first sharding. Deferred (ADR-001): approval
expiry/revocation; executor leasing/outbox; token rotation/revocation infrastructure and rate limits;
audit hash chain; full restart matrix; backup/restore.

## Source-pinning policy (A1)
Fast-moving external repositories (NIKA first among them) are cited ONLY by exact commit SHA with access
date; all reported statistics are statistics of that SHA. "Fetched from main" is not a citation. Two
same-day fetches of NIKA's main returned conflicting statistics during planning — the SHA rule exists
because of that incident.

## Release limitations and negative findings (acceptance row J08 — PUBLISHED)
The full ledger is **[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)** (scientific limits, negative and
corrected findings, A1/A2 scope waivers, runtime/trust boundaries). Headlines:
- Detection is structurally blind to *gray* faults even under load; learned localization recovers
  them (the thesis). Gray exact-link top-1 is the honest weak spot; healthy control at chance.
- Live remediation enforces a narrower safety subset than the full precheck suite (H07 PARTIAL,
  ADR-004); executor demoed via the deterministic slice, no live HTTP API server (backlog).
- Runtime isolation relies on the Docker Desktop VM boundary, not a dedicated hypervisor VM
  (`docs/decisions/ADR-002-lab-runtime-boundary.md`); no defense against a same-host privileged
  attacker (threat-model assumption A1, `docs/threat-model.md`).
- A1 scope waivers (approval expiry/revocation, executor leasing/outbox, token rotation/rate limits,
  audit hash chain, full restart matrix, backup/restore) — `docs/decisions/ADR-001-scope-waivers.md`.

Evidence index for every acceptance row: **[`docs/TRACEABILITY.md`](docs/TRACEABILITY.md)**.
Operator runbook: **[`runbooks/operator-guide.md`](runbooks/operator-guide.md)**.
Data/model cards: **[`docs/DATA_CARD.md`](docs/DATA_CARD.md)**, **[`docs/MODEL_CARD.md`](docs/MODEL_CARD.md)**.

## Rules of this folder
1. Planning is CLOSED. Documents change only via ADR-style corrections when build reality contradicts them.
2. research-log.md is append-only.
3. Anything not in the canon is out of scope until the acceptance matrix (as amended) is green.
4. The next artifact is Gate 0 of the Canonical Execution Bible. No further planning documents may be created.
