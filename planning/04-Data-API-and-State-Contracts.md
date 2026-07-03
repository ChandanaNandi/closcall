# ClosCall — Data, API, and State Contracts

Status: authoritative companion to the Canonical Execution Bible  
Purpose: remove implementation ambiguity from persistence, lifecycle, evidence, approval, execution,
and audit behavior

## 1. Storage ownership

| Store | Owns | Does not own |
|---|---|---|
| Prometheus | short-retention raw/derived time series and quality metrics | incidents, labels, approvals |
| PostgreSQL `core` | runtime topology identity, incidents, evidence metadata, diagnoses, plans, jobs | raw counter history |
| PostgreSQL `identity` | users, roles, sessions, service principals | device secrets |
| PostgreSQL `evaluation` | campaigns, injections, labels, split manifests | runtime workflow decisions |
| PostgreSQL `audit` | append-only state-change events with FK integrity | mutable aggregates |
| Artifact store | Parquet, tensors, models, reports, topology snapshots, evidence payloads | secrets |
| Secret store | DB/device/API credentials and signing keys | application state |

The local artifact store is a content-addressed directory for core development. Every artifact is
registered before use. Replacing it with object storage must not change artifact IDs or manifests.

## 2. Database standards

- PostgreSQL 16; integration tests use PostgreSQL, never SQLite.
- `pgcrypto` supplies `gen_random_uuid()`.
- Alembic is the only schema-change mechanism.
- Runtime roles cannot execute DDL.
- UTC sessions; application accepts timezone-aware timestamps only.
- Primary UUID: `id uuid primary key default gen_random_uuid()`.
- Append-only high-volume event IDs may use generated `bigint`.
- Every row: `created_at timestamptz not null default clock_timestamp()`.
- Mutable aggregate: `updated_at` and `version bigint not null default 1`.
- Every text/JSON field has application and database size limits.
- Enumerations use CHECK constraints or reference tables; values are never free-form.
- Foreign keys declare `ON DELETE` explicitly. Operational/audit history normally uses RESTRICT.
- Derivable latency values are calculated in views/reports, not stored as competing truth.
- JSONB crossing a boundary has a versioned Pydantic/JSON Schema and canonical hash.
- All artifact references use FK to `core.artifacts`, never an unchecked path.

## 3. Database roles

- `closcall_owner`: non-login schema owner.
- `closcall_migrator`: temporary DDL role.
- `closcall_api`: case reads and human decision writes.
- `closcall_workflow`: evidence/diagnosis/plan-draft writes.
- `closcall_sensor`: run/detection writes.
- `closcall_trainer`: read-only frozen TRAIN/VALIDATION labels and model-artifact writes.
- `closcall_correlator`: incident/signal/event writes.
- `closcall_executor`: approved-job reads and execution/recovery writes.
- `closcall_telemetry`: normalized log/signal inserts.
- `closcall_evaluator`: evaluation-schema and report access.
- `closcall_audit_reader`: audit SELECT only.

`api`, `workflow`, runtime `sensor`, `correlator`, and `executor` have no privileges on ground-truth
tables. `trainer` receives only frozen TRAIN/VALIDATION label views and cannot read TEST labels.
`evaluator` does not supply runtime tools. Database grants are tested.

## 4. Entity catalog

The following is the required logical schema. Migrations must express all stated constraints.

### 4.1 Identity

`identity.users`

- `id`
- `username citext not null unique`
- `password_hash text not null`
- `status text not null` — `pending_rotation|active|locked|disabled`
- `token_version integer not null default 1`
- `last_login_at timestamptz`
- `created_at`, `updated_at`, `version`

`identity.roles`

- `id`, `name text not null unique`, `created_at`
- fixed names: `viewer`, `approver`, `auditor`, `admin`

`identity.permissions`

- `id`, `name text not null unique`, `created_at`

`identity.user_roles`

- `user_id`, `role_id`, `created_at`
- PK `(user_id, role_id)`

`identity.role_permissions`

- `role_id`, `permission_id`, `created_at`
- PK `(role_id, permission_id)`

`identity.auth_sessions`

- Post-core under ADR-001.
- Adds `id`, `user_id`, `refresh_token_hash`, `jti`, issue/expiry/revocation timestamps,
  user-agent hash, and source IP when refresh-token rotation/session revocation is promoted.
- Core uses a short-lived signed access JWT cookie and stores no refresh token.

`identity.service_principals`

- `id`, `name unique`, `purpose`, `credential_ref`, `disabled_at`, `created_at`
- credentials themselves are not stored here

### 4.2 Topology and artifacts

`core.topologies`

- `id`, `name`, `revision integer`, `spec_json jsonb`, `spec_hash char(64)`, `created_at`
- UNIQUE `(name, revision)` and UNIQUE `spec_hash`
- immutable after use

`core.topology_nodes`

- `id`, `topology_id`, `node_key`, `role`, `asn`, `loopback inet`, `management_address inet`
- UNIQUE `(topology_id, node_key)`, UNIQUE relevant address constraints

`core.topology_links`

- `id`, `topology_id`, `link_key`
- `a_node_id`, `a_interface`, `a_address inet`
- `b_node_id`, `b_interface`, `b_address inet`
- `capacity_bps bigint`, `mtu integer`, `eligible_for_fault boolean`
- UNIQUE `(topology_id, link_key)` and endpoint uniqueness

`core.artifacts`

- `id`, `kind`, `uri`, `sha256 char(64)`, `byte_size bigint`, `media_type`
- `schema_version integer`, `metadata_json jsonb`, `created_at`
- UNIQUE `sha256`; CHECK byte size non-negative

`core.dataset_windows`

- `id`, `incident_id nullable`, `kind`, `start_at`, `end_at`
- `as_of_at`, `artifact_id`, `split`, `quality_json`, `created_at`
- CHECK `start_at < end_at` and `end_at <= as_of_at`

### 4.3 Evaluation-only ground truth

`evaluation.scenarios`

- `id`, `scenario_key`, `topology_id`, `definition_json`, `definition_hash`
- `fault_class`, `simulated boolean not null`, `created_at`
- UNIQUE `(topology_id, scenario_key)`, UNIQUE `definition_hash`

Runtime incidents never expose `scenario_key`.

`evaluation.campaigns`

- `id`, `campaign_key unique`, `manifest_artifact_id`, `code_revision`, `image_manifest_json`
- `master_seed`, `status`, `started_at`, `completed_at`, `created_at`

`evaluation.fault_injections`

- `id`, `campaign_id`, `scenario_id`, `shard_key`, `batch_key`
- `target_json`, `parameters_json`, `traffic_seed`, `fault_seed`
- `status`, `baseline_started_at`, `requested_at`, `mutation_ack_at`, `device_observed_at`
- `clear_requested_at`, `clear_ack_at`, `settled_at`
- `clock_quality_json`, `telemetry_quality_json`, `quarantine_reason`
- `simulated boolean not null default true`, `created_at`
- timestamp-order checks where values are present

`evaluation.ground_truth_labels`

- `id`, `fault_injection_id unique`, `schema_version`, `label_json`, `label_hash`, `created_at`

`evaluation.split_manifests`

- `id`, `protocol_name`, `version`, `artifact_id`, `manifest_hash`, `frozen_at`, `created_at`
- UNIQUE `(protocol_name, version)`

### 4.4 Incidents

`core.incidents`

- `id`, `incident_key text not null unique`
- `topology_id`, `status`, `severity`
- `opened_at`, `detected_at`, `resolved_at`, `closed_at`
- `telemetry_quality`, `created_at`, `updated_at`, `version`
- timestamp ordering checks

`core.incident_signals`

- `id`, `incident_id`, `source`, `source_event_id`
- `observed_at`, `received_at`, `payload_json`, `payload_hash`, `created_at`
- UNIQUE `(source, source_event_id)`

`core.incident_correlations`

- `id`, `incident_id`, `correlation_key`
- `first_seen_at`, `last_seen_at`, `signal_count`, `active`, `created_at`, `updated_at`
- partial UNIQUE active `correlation_key`

`core.incident_events`

- `id bigint generated always as identity`
- `incident_id`, `sequence_no`, `event_type`
- `actor_type`, `actor_id`, `payload_json`, `occurred_at`, `created_at`
- UNIQUE `(incident_id, sequence_no)`
- no UPDATE/DELETE grants

Incident opening accepts an idempotency key and atomically returns the existing row under
concurrent duplicate signals.

### 4.5 Reproducible runs and models

`core.runs`

- `id`, `parent_run_id nullable`
- `kind`, `status`, `code_revision`, `dependency_lock_hash`
- `config_json`, `config_hash`, `dataset_manifest_hash`, `ground_truth_version`
- `model_manifest_json`, `prompt_manifest_json`, `image_manifest_json`
- `hardware_json`, `seed_manifest_json`, `determinism_json`
- `started_at`, `completed_at`, `error_json`, `created_at`

`core.model_artifacts`

- `id`, `run_id`, `name`, `model_type`, `artifact_id`, `framework_version`
- `feature_schema_hash`, `training_manifest_hash`, `created_at`
- UNIQUE `(run_id, name)`

`core.detections`

- `id`, `run_id`, `incident_id`, `detector_name`, `detected_at`
- `as_of_at`, `quality_json`, `ranked_suspects_json`, `created_at`
- UNIQUE `(run_id, incident_id, detector_name)`
- CHECK `as_of_at = detected_at` unless protocol explicitly records a fixed oracle cutoff

### 4.6 Evidence and diagnosis

`core.diagnoses`

- `id`, `run_id`, `incident_id`, `status`
- `fault_class`, `target_json`, `confidence`, `report_artifact_id`
- `as_of_at`, `created_at`
- UNIQUE `(run_id, incident_id)`
- status: `draft|committed|undiagnosed|verification_failed`

`core.evidence`

- `id`, `incident_id`, `kind`, `template_id`, `parameters_json`
- `as_of_at`, `observed_start_at`, `observed_end_at`
- `source_ref_json`, `snapshot_artifact_id`, `snapshot_hash`
- `units`, `quality_json`, `created_at`
- CHECK `observed_end_at <= as_of_at`

`core.claims`

- `id`, `diagnosis_id`, `claim_key`, `claim_type`
- `subject_json`, `predicate_json`, `claim_text`, `created_at`
- UNIQUE `(diagnosis_id, claim_key)`

`core.claim_evidence`

- `claim_id`, `evidence_id`, `relationship`, `created_at`
- PK `(claim_id, evidence_id)`
- relationship: `supports|contradicts|context`

`core.verification_results`

- `id`, `claim_id`, `verifier_version`
- `result`, `reason_codes text[]`, `details_json`, `created_at`
- UNIQUE `(claim_id, verifier_version)`
- result: `supported|contradicted|insufficient|invalid`

### 4.7 Remediation versions and decisions

`core.remediations`

- `id`, `diagnosis_id unique`, `status`, `current_plan_version`
- `created_at`, `updated_at`, `version`

`core.remediation_versions`

- `id`, `remediation_id`, `plan_version`
- `plan_json`, `plan_digest char(64)`
- `topology_hash char(64)`, `config_revision`, `risk_class`
- `created_by_type`, `created_by_id`, `superseded_at`, `created_at`
- UNIQUE `(remediation_id, plan_version)`
- UNIQUE `(remediation_id, plan_digest)`
- immutable

`core.remediation_steps`

- `id`, `remediation_version_id`, `step_no`
- `action_type`, `target_json`, `parameters_json`
- `preconditions_json`, `postconditions_json`, `rollback_json`
- `created_at`
- UNIQUE `(remediation_version_id, step_no)`

`core.approval_decisions`

- `id`, `remediation_version_id`, `plan_digest`
- `user_id`, `decision`, `comment`, `decided_at`, `created_at`
- UNIQUE `(remediation_version_id, user_id)`
- decision: `approve|reject`
- immutable

`core.approval_revocations`

- `id`, `approval_decision_id`, `user_id`, `reason`, `created_at`

`expires_at` and `core.approval_revocations` are post-core extensions under ADR-001; they are not
created by core migrations.

Requesting a change creates another remediation version. There is no mutable “edit approval.”

### 4.8 Durable execution and recovery

`core.execution_jobs`

- `id`, `remediation_version_id unique`, `idempotency_key unique`
- `status`, `available_at`
- `attempts`, `deadline_at`, `last_error`, `created_at`, `updated_at`, `version`

Core runs one executor and inserts the job atomically with approval. `core.outbox_events`,
`lease_owner`, `lease_expires_at`, multi-worker claiming, and dead-letter publication are post-core
extensions under ADR-001.

`core.executions`

- `id`, `execution_job_id unique`, `status`
- `started_at`, `completed_at`
- `observed_config_before`, `observed_config_after`
- `topology_hash_before`, `failure_class`, `created_at`

`core.execution_steps`

- `id`, `execution_id`, `remediation_step_id`, `attempt_no`, `status`
- `started_at`, `completed_at`, `request_hash`, `result_json`, `error_json`, `created_at`
- UNIQUE `(execution_id, remediation_step_id, attempt_no)`

`core.recovery_checks`

- `id`, `execution_id`, `check_type`, `predicate_json`
- `result`, `observed_json`, `checked_at`, `created_at`

`core.rollback_jobs`

- `id`, `execution_id`, `approval_decision_id nullable`, `status`, `reason`, `created_at`, `updated_at`

`core.rollback_steps`

- `id`, `rollback_job_id`, `execution_step_id`, `status`
- `observed_before`, `observed_after`, `error_json`, `created_at`

### 4.9 Append-only audit

`audit.events`

- `id bigint generated always as identity`
- `occurred_at`, `actor_type`, `actor_id`, `action`
- `entity_type`, `entity_id`, `request_id`, `trace_id`, `source_ip`
- `before_json`, `after_json`

Runtime roles may INSERT and SELECT, never UPDATE or DELETE. Triggers are owned by a non-login role.
Audit serialization redacts credentials, tokens, cookies, and authorization headers. Cryptographic
`previous_hash`/`event_hash` chaining and external anchoring are post-core under ADR-001.

## 5. State machines

### 5.1 Incident

Primary:

`new -> correlating -> open -> diagnosing -> awaiting_approval -> remediating ->
verifying_recovery -> resolved -> closed`

Branches:

- `diagnosing -> undiagnosed`
- `awaiting_approval -> rejected`
- `remediating -> execution_failed|outcome_unknown`
- `verifying_recovery -> recovery_failed`
- nonterminal -> `quarantined|cancelled`

One transition service must lock the row, verify current state/version, update the aggregate, append
incident event and audit, and commit atomically.

### 5.2 Remediation

`draft -> pending_approval -> approved -> queued -> executing -> verifying -> succeeded`

Branches:

- pending/approved -> `rejected|superseded`
- executing -> `failed|outcome_unknown`
- verifying -> `recovery_failed`
- failure/unknown -> `rollback_pending -> rolling_back -> rolled_back|rollback_failed`

No direct draft-to-executing transition exists.

### 5.3 Execution job

`pending -> running -> reconciling -> completed`

Branches:

- running -> `retryable_failed|permanent_failed|outcome_unknown`
- outcome unknown -> reconciling, never blind retry

The core has one executor. A unique plan-version/idempotency constraint prevents duplicate jobs.
Multi-worker leasing and `SKIP LOCKED` claiming are post-core under ADR-001.

## 6. API contract

Base: `/api/v1`. Checked-in OpenAPI is contract-tested. Errors use RFC 9457 problem details.
Unknown JSON fields are rejected. Requests have size/time limits. Lists use cursor pagination.

### 6.1 Read endpoints

- `GET /incidents`
- `GET /incidents/{incident_id}`
- `GET /incidents/{incident_id}/events`
- `GET /incidents/{incident_id}/evidence`
- `GET /diagnoses/{diagnosis_id}`
- `GET /remediations/{remediation_id}`
- `GET /remediation-versions/{version_id}`
- `GET /executions/{execution_id}`
- `GET /audit-events`
- `GET /health/live`
- `GET /health/ready`

### 6.2 Mutation endpoints

- `POST /auth/login`
- `POST /auth/logout`
- `POST /remediations/{id}/versions` — creates a new immutable version
- `POST /remediation-versions/{id}/decisions`
- `POST /executions/{id}/rollback-requests`

`POST /auth/refresh` and `POST /approval-decisions/{id}/revoke` are post-core endpoints under
ADR-001.

Every mutation requires:

- `Idempotency-Key`;
- authenticated actor and permission;
- CSRF token for cookie-authenticated browser calls;
- `If-Match`/expected aggregate version where state can race;
- audit availability;
- trace/request ID.

Decision body includes `decision`, `plan_digest`, `expected_version`, and `comment`. The server
rejects digest mismatch, superseded plan, topology/config drift, or stale aggregate version.

No endpoint accepts raw shell, arbitrary URL, arbitrary PromQL, arbitrary gNMI path, or arbitrary
executor JSON.

## 7. Authentication and authorization

- Argon2id password hashes.
- One-time bootstrap credentials force rotation.
- Short-lived access JWT stored only in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
- Browser access uses `https://closcall.local` through loopback-only Caddy with a trusted local
  development certificate; core does not weaken the cookie to support plain HTTP.
- Pin JWT algorithm; validate `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`, key ID, and token version.
- CSRF protection on every mutation: the server emits a signed token bound to the authenticated
  JWT `jti`; Jinja places it in the rendered page, HTMX sends it in a dedicated header, and the
  server verifies signature, `jti`, origin, and same-site request metadata.
- Object authorization checks prevent IDOR.
- Human roles never receive executor/device credentials.

Refresh-token rotation, session revocation infrastructure, signing-key rotation workflows, and rate
limiting are post-core hardening items under ADR-001. CSRF is core because cookie authentication is
used by the HTMX browser UI.

## 8. Executor safety policy

Before a job can mutate a device:

1. plan digest and approval match;
2. approval is valid for the exact immutable plan version;
3. topology/config revision equals approved snapshot;
4. telemetry and management reachability are fresh;
5. action, target, and bounded parameters are allowlisted;
6. target is not management/console;
7. no conflicting active execution exists;
8. alternate route/path is healthy;
9. post-change remaining capacity exceeds policy headroom;
10. the action cannot remove the final usable path;
11. pre-state and rollback payload are captured;
12. recovery predicates exist;
13. database and audit are writable.

The executor performs read/compare/set/read. Safe retry requires known actual state. Timeout after an
uncertain mutation is `outcome_unknown` and triggers reconciliation. Rollback uses captured state
and reverse completed-step order; it stops when its own preconditions are unsafe.

## 9. Artifact and dataset contracts

### 9.1 Raw telemetry Parquet

Columns:

- `event_time`, `received_at`, `ingested_at`
- `topology_hash`, `node`, `interface`, `direction`, `metric`
- `value`, `unit`, `is_counter`
- `quality_flags`, `source_sequence`, `schema_version`

Partition by bounded campaign/topology/date identifiers, never by high-cardinality incident ID
alone.

### 9.2 Causal feature Parquet

- `example_id`, `split`, `incident_runtime_id`
- `window_start`, `window_end`, `as_of_at`
- `node`, `interface`, feature columns
- explicit missingness/age columns
- `feature_schema_hash`, `preprocessor_hash`

Ground truth is stored in evaluator-only artifacts and joined only during scoring.

### 9.3 Graph artifact

- device/interface node tables;
- typed directed relation tables;
- eligible physical-link candidate table;
- causal node/edge features and masks;
- no raw identity feature;
- graph/topology/feature schema hashes;
- evaluator-only label sidecar.

### 9.4 Manifest

Every dataset/model/report manifest includes content hashes, source run IDs, split protocol,
topology/config hashes, code/dependency/image revisions, seeds, exclusions, and creation command.

## 10. Failure behavior

- Prometheus unavailable/stale: diagnosis may abstain; execution blocked.
- LLM unavailable: deterministic path or `undiagnosed`; verification never bypassed.
- PostgreSQL unavailable: no approval/execution.
- Audit unavailable: no state mutation.
- Device timeout: outcome unknown and read-back reconciliation.
- Executor restart: reconcile the single running job against device state before continuing.
- Duplicate request: return original result from idempotency record.
- Config drift after approval: supersede/invalidate approval.
- Partial execution: stop; evaluate explicit rollback.
- Artifact checksum mismatch: reject run/dataset/report.
- Ground-truth access attempt by runtime role: security failure and gate failure.

## 11. Retention and post-core backup/restore

- Classify retention independently for Postgres runtime state, audit, Prometheus, raw corpus,
  derived datasets, models, prompts, and reports.
- Core documents retention classes and keeps content-addressed artifacts with checksum manifests.
- Backup encryption, WAL/PITR, secret-backup procedure, isolated restore verification, RPO/RTO, and
  restore drills are post-core hardening requirements under ADR-001.

## 12. Required contract tests

- Empty-database migration and upgrade tests.
- Role/grant negative tests including ground-truth isolation.
- 100 concurrent duplicate signals create one incident.
- Duplicate decisions create one immutable result.
- Approval for version N cannot execute N+1.
- Edit or config drift invalidates execution.
- Duplicate requests cannot create or execute more than one job for a plan version.
- Restart at each execution step does not repeat unsafe effects.
- Ambiguous timeout stays outcome unknown.
- Last-path, stale-data, management-target, and inadequate-capacity changes fail closed.
- Partial execution and reverse rollback are recorded.
- Audit rows cannot update/delete.
- CSRF, RBAC, IDOR, JWT-claim, and stale-version negative tests.
- Secret redaction across logs, traces, reports, audit, and exported artifacts.
- PostgreSQL and executor restart tests; broader service-failure and restore matrices are post-core.
- Full trace joins incident through final recovery/evaluation without using ground truth at runtime.
