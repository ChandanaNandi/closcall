# ClosCall — Threat Model and Trust Boundaries (Gate 0 deliverable)

Status: Gate 0 artifact. Grounded exclusively in the canon: Bible (`planning/03`) §2 invariants,
§3 architecture, §12.3 tool rules; Contracts (`planning/04`) §1, §3, §7, §8, §10; Acceptance
Matrix (`planning/05`) rows referenced inline; ADR-001 threat-scope ruling. Entries the canon does
not decide are marked `ASSUMPTION:` and require pilot adjudication at the Gate 0 exit review.

## 1. Threat actor scope

Per ADR-001 rationale, the deployment is a **single-operator lab with no untrusted callers**.
Consequences:

- The primary threats are *internal*: ground-truth leakage into the diagnostic plane, credential
  bleed across process boundaries, prompt injection through untrusted text, and unsafe mutation
  paths — not remote human attackers.
- Controls that remain core despite the scope ruling (secure cookies, CSRF, RBAC, IDOR, grant
  tests) exist because the browser and the LLM are still untrusted *channels* even when the
  operator is trusted (ADR-001 authentication ruling; 05 I02/I02a).
- `ASSUMPTION:` a malicious human on the same host/LAN is out of scope for core; loopback-only
  binding (Bible §3.3) is the sole network control claimed against it.

## 2. Trust-boundary and data-flow diagram

Derived from Bible §3.1 planes and §3.3 container networks. `║` marks a trust boundary; the
parenthetical names the control that enforces it.

```text
                       ┌─────────────────────────────────────────────┐
                       │ LAB DATA PLANE (lab_data network)           │
                       │ hosts <-> leaves <-> spines; traffic only   │
                       └──────────────────┬──────────────────────────┘
                                          │ device state / syslog
   ║ B1: management vs data plane (no management shortcuts in reachability tests, §3.1)
                       ┌──────────────────▼──────────────────────────┐
                       │ LAB MANAGEMENT PLANE (lab_mgmt network)     │
                       │ gNMI + syslog endpoints                     │
                       └───┬──────────────┬──────────────┬───────────┘
        read-only telemetry│    chaos identity│   restricted executor identity
                 identity  │   (lab-only fault│   (allowlisted gNMI Set)
                           │        controls) │
   ║ B2: credential separation — three distinct device identities (§3.1, §3.2; 05 I01)
        ┌──────────────────▼───┐  ┌───────────▼─────────┐  ┌─────────▼──────────┐
        │ OBSERVATION PLANE    │  │ CHAOS (evaluator     │  │ EXECUTION PLANE    │
        │ gNMIc→Prometheus→    │  │ side): fault ledger, │  │ durable job →      │
        │ dashboards; syslog→  │  │ ground-truth labels  │  │ prechecks → guarded│
        │ normalized events;   │  │ (evaluation schema)  │  │ mutation → read-   │
        │ quality monitor      │  │                      │  │ back → recovery    │
        └──────────┬───────────┘  └───────────┬──────────┘  └─────────▲──────────┘
                   │                          │                       │
   ║ B3: GROUND-TRUTH ISOLATION — evaluation schema is evaluator-only (§2.1; 04 §3; 05 E02/I07)
                   │                          ║ (DB grants, tested)   │
        ┌──────────▼───────────┐              ║                       │
        │ INCIDENT PLANE       │   labels never cross B3 into        │
        │ detectors→correlator │   runtime; runtime never crosses    │
        │ →incident state      │   into evaluation                   │
        └──────────┬───────────┘                                     │
                   │ causal snapshots (event_time <= t, §2.2)        │
        ┌──────────▼───────────┐                                     │
        │ REASONING PLANE      │                                     │
        │ read-only typed tools│                                     │
        │ →evidence→claims→    │                                     │
        │ draft plan           │                                     │
        └──────────┬───────────┘                                     │
   ║ B4: LLM/workflow has NO mutation credentials (§2.6; 05 H04)     │
        ┌──────────▼───────────┐                                     │
        │ HUMAN PLANE          │                                     │
        │ loopback HTTPS UI;   │                                     │
        │ approve/reject binds │                                     │
        │ plan digest (§2.5)   │                                     │
        └──────────┬───────────┘                                     │
   ║ B5: approval → durable job in same DB txn; executor has no public ingress (§2.7; 05 H05/H06)
                   └──────────── approved job (digest-bound) ────────┘
```

Container-network enforcement (Bible §3.3): `ingress` (proxy/UI), `app` (API/workflow/correlator),
`data` (PostgreSQL, never host-public), `observability`, `lab_mgmt` (only telemetry, chaos,
executor attach), `lab_data`. Browser services bind `127.0.0.1` only. No Docker socket in
application containers; containerlab privileged operations only inside the Linux lab VM
(OrbStack adequacy = open item, research log R8).

## 3. Assets

| Asset | Location (canon) | Why it is an asset |
|---|---|---|
| Ground-truth labels, chaos parameters, scenario keys | `evaluation` schema (04 §4.3) | leakage invalidates every evaluation claim (§2.1; 05 E02, E06, I07) |
| Frozen TEST split manifests | `evaluation.split_manifests` (04 §4.3) | tuning on TEST destroys P4/P7 (§2.11; 05 E07, F02) |
| Device mutation credential (executor gNMI Set) | secret store (04 §1) | only path to device change; bleed = unguarded mutation (§2.6) |
| Chaos identity (lab fault controls) | secret store (04 §1) | misuse fakes or corrupts ground truth (§3.2) |
| Read-only telemetry identity | secret store (04 §1) | compromise corrupts observation integrity (05 C-rows) |
| Approval decisions + immutable plan digests | `core.approval_decisions`, `core.remediation_versions` (04 §4.7) | digest binding is the HITL guarantee (§2.5; 05 H01–H03) |
| Append-only audit log | `audit.events` (04 §4.9) | attributability of every mutation (§2.10; 05 I05, I06) |
| Telemetry quality/time integrity | observation plane (§9) | stale/gapped data must block execution (§2.8; 05 C06, C07) |
| Content-addressed artifacts + manifests | artifact store (04 §1, §9) | reproducibility chain (05 A04, A05, E05) |
| Prompt registry (immutable `name.vN.md` + SHA-256) | `prompts/` (§6) | silent prompt drift invalidates reasoning comparisons (§12.4) |
| DB role credentials | secret store (04 §1, §3) | grants ARE the isolation mechanism; tested (04 §3) |
| JWT signing key, local dev CA | secret store (04 §1; 04 §7) | forgery defeats approval authenticity (05 I02/I02a) |

## 4. Actors

| Actor | Trust level | Granted (canon) | Denied (canon) |
|---|---|---|---|
| Human operator (roles `viewer`/`approver`/`auditor`/`admin`, 04 §4.1) | trusted person, untrusted browser channel | case reads, approve/reject exact digest (04 §6.2) | executor/device credentials (04 §7) |
| LLM (local, Ollama-served) | **untrusted component** | read-only typed tools, bounded templates (§12.3) | raw PromQL/gNMI/shell/URL (§1.2; 04 §6.2), any mutation, any label |
| `telemetry` principal | semi-trusted | device operational reads, signal writes | device config, ground truth (§3.2) |
| `chaos` principal | trusted evaluator-side | lab impairments, fault ledger writes | approval/executor code paths (§3.2) |
| `correlator`/`sensor` principals | semi-trusted runtime | signals→incidents; detections/rankings | labels, post-decision data, mutation (§3.2) |
| `trainer` principal | semi-trusted offline | frozen TRAIN/VALIDATION views only | TEST labels, runtime incidents (§3.2; 04 §3) |
| `workflow`/`api` principals | semi-trusted | evidence/claims/drafts; decisions | device credentials, labels, execution (§3.2) |
| `executor` principal | most-privileged runtime | approved-job reads, allowlisted gNMI Set | public ingress, labels, chaos cleanup (§3.2; §8.3) |
| `evaluator` principal | trusted offline | predictions + ground truth, metrics | runtime diagnosis decisions (§3.2) |
| `migrator` | temporary DDL | schema DDL | runtime behavior (§3.2; 04 §3) |
| External network attacker | out of core scope (ADR-001) | — | all services loopback/network-isolated (§3.3) |

## 5. Credential ownership (explicit, per Gate 0 exit criterion)

1. Device credentials exist in exactly three identities — telemetry (read-only), executor
   (allowlisted Set), chaos (lab fault controls) — owned by the secret store, referenced by
   `identity.service_principals.credential_ref`, never stored in the DB row (04 §4.1), never held
   by API, workflow, or any human role (§2.6; 04 §7; 05 H04).
2. Each process runs under its own PostgreSQL role (04 §3); `evaluation` schema grants are denied
   to api, workflow, runtime sensor, correlator, executor; trainer sees only frozen
   TRAIN/VALIDATION views; grants are covered by negative tests (05 E02, I07).
3. Human authentication: Argon2id hashes; short-lived JWT in HttpOnly/Secure/SameSite=Strict
   cookie over loopback HTTPS only; CSRF token bound to `jti` on every mutation (04 §7).
   Rotation/revocation infrastructure is deferred per ADR-001.
4. Secrets never appear in YAML, `.env.example`, logs, traces, reports, or artifacts (§6; 05 I03);
   audit serialization redacts credentials/tokens/cookies/authorization headers (04 §4.9).
5. `ASSUMPTION:` the local development CA private key (Caddy, §4) is held on the host outside the
   repository and treated with the same handling rule as other secrets; the canon names the CA but
   does not state its key-custody rule.

## 6. Ground-truth isolation (explicit, per Gate 0 exit criterion)

- The diagnostic plane can never read: labels, chaos parameters, answer-bearing scenario keys,
  post-clear data, evaluator-only tables (§2.1). Runtime incidents never expose `scenario_key`
  (04 §4.3).
- Enforcement is layered: separate DB roles + denied grants (04 §3), evaluator-only label sidecars
  in artifacts (04 §9.2/9.3), causal as-of windows excluding `t_clear`/`t_settled`/duration/split
  (§10.3), and negative tests as acceptance rows (05 E02, E06, I07; failure behavior 04 §10:
  runtime ground-truth access attempt = security failure AND gate failure).
- Ground truth joins predictions only inside the evaluator during scoring (04 §9.2).

## 7. Prompt-injection paths

The LLM is an untrusted component fed partially attacker-influenceable text. Canon rule: retrieved
logs/runbooks are untrusted text and cannot directly populate executor parameters (§12.3; 05 G05).
Enumerated ingress paths for injected instructions:

| # | Path | Source of hostile text | Canon control |
|---|---|---|---|
| PI-1 | `get_log_events` | syslog content originates on devices; fault conditions can carry arbitrary strings | logs are untrusted text; typed claims verified deterministically before narrative (§12.2/12.3) |
| PI-2 | `search_runbooks` | runbook corpus contents | same untrusted-text rule; retrieval is a bounded tool (§12.3) |
| PI-3 | `get_similar_resolved_incidents` | past incident reports (possibly LLM-authored — self-amplification) | same rule; tool enforces scope/limits (§12.3) |
| PI-4 | `get_metric_window` etc. | metric label values / interface descriptions carrying device-originated strings | bounded label set forbids free text in metric labels (§6); templates only (§9.3) |
| PI-5 | Draft-plan → executor parameters | any of the above laundered into plan fields | plans map only verified diagnosis classes to allowlisted templates with bounded parameters (§12.1; 04 §8.5); no endpoint accepts arbitrary executor JSON (04 §6.2) |
| PI-6 | Prompt files themselves | tampered prompt registry | immutable versioned prompts with SHA-256 registry (§6) |
| PI-7 | `ASSUMPTION:` human free-text fields (approval `comment`, rejection reasons) re-entering LLM context in later incidents | operator-entered text | canon is silent; proposed treatment: same untrusted-text rule as PI-3 |

Model qualification includes prompt-injection resistance fixtures before any LLM is selected
(§4.1). Adversarial claim fixtures (wrong polarity/unit/interface/time/relevance) are core
acceptance (§12.2; 05 G02).

## 8. Failure modes (fail-closed inventory)

From 04 §10 and Bible §2.8/§17 — each blocks rather than degrades:

| Failure | Required behavior | Acceptance |
|---|---|---|
| Prometheus stale/unavailable | diagnosis may abstain; execution blocked | 05 C06, C07 |
| LLM unavailable/schema failure | deterministic path or `undiagnosed`; verification never bypassed | 05 G06 |
| PostgreSQL unavailable | no approval, no execution | 04 §10 |
| Audit unwritable | no state mutation at all | 05 I06 |
| Device timeout mid-mutation | `outcome_unknown`, read-back reconciliation, never blind retry | 05 H09 |
| Executor restart | reconcile DB intent vs device state before continuing | 05 J03 (core scope) |
| Duplicate request/signal | idempotency returns original result; one incident (04 §10; 04 §4.4) | 05 E03, H06 |
| Config drift after approval | approval superseded/invalidated | 05 H03 (core clause) |
| Partial execution | stop; explicit rollback evaluation | 05 H11 |
| Artifact checksum mismatch | reject run/dataset/report | 05 E05 |
| Telemetry cannot distinguish fault from missing data | project-level STOP condition | Bible §17 |
| Ground-truth reachable from runtime role | security failure + gate failure | 05 E02/I07; 04 §10 |

## 9. Assumptions requiring pilot adjudication

Collected from above for the exit review: §1 (same-host attacker out of scope), §5.5 (dev CA key
custody), §7 PI-7 (human free-text treated as untrusted when re-entering LLM context).
