# ClosCall — Project Home
### Evidence-grounded incident command for AI datacenter fabrics.

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

## Release limitations queue (for acceptance row J08)
These are known limitations to be written into the release README's limitations section at J08.
Appended as build reality establishes them; not a planning-document rewrite.
- Runtime isolation relies on the Docker Desktop VM boundary plus emptied host file-sharing, not a
  dedicated hypervisor VM; documented residual risk (see `docs/decisions/ADR-002-lab-runtime-boundary.md`).
- Core does not defend against a same-host human/privileged attacker; loopback binding is the only
  claimed network control (threat-model assumption A1, `docs/threat-model.md`).

## Rules of this folder
1. Planning is CLOSED. Documents change only via ADR-style corrections when build reality contradicts them.
2. research-log.md is append-only.
3. Anything not in the canon is out of scope until the acceptance matrix (as amended) is green.
4. The next artifact is Gate 0 of the Canonical Execution Bible. No further planning documents may be created.
