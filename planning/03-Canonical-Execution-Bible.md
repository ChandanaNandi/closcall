# ClosCall — Canonical Execution Bible

Status: authoritative planning contract  
Supersedes: `planning/02-Build-Bible.md`  
Execution model: ordered gates; no calendar or timeline

## 0. Meaning of “bulletproof”

No non-trivial system can be guaranteed correct before it is exercised. This plan is considered
strong because:

- every material assumption has a named verification gate;
- each component has an owner, input, output, failure mode, and acceptance test;
- safety-critical transitions are fail-closed and persisted;
- evaluation data cannot reveal ground truth to the system under test;
- online results use only information available at the decision time;
- every mutation is attributable, versioned, approval-bound, reconcilable, and auditable;
- the project stops or simplifies when a gate fails instead of hiding the failure.

An item is not complete because code exists or a demo looked correct. It is complete only when the
acceptance matrix passes from a clean clone and retains the required evidence.

## 1. Mission and scope

ClosCall is a research-grade, reproducible incident-command system for an emulated BGP/ECMP Clos
fabric. It must:

1. build and verify a real routing topology in containerlab;
2. collect streaming device state and data-plane counters;
3. inject known, honestly named network impairments;
4. detect incidents and rank root-cause links using rules and learned models;
5. produce typed, evidence-backed diagnostic claims;
6. draft a bounded remediation plan;
7. require a human decision on the exact immutable plan;
8. execute only allowlisted actions through an isolated executor;
9. verify recovery or expose failure/ambiguity;
10. compare rules, neural sensors, and reasoning policies under controlled protocols.

### 1.1 Core proofs

- P1: reproducible 2-spine/4-leaf Clos with working eBGP and ECMP.
- P2: trustworthy, quality-scored streaming telemetry and useful dashboards.
- P3: deterministic fault campaigns with isolated ground truth.
- P4: causal detection and link ranking evaluated on frozen leakage-safe splits.
- P5: claim-level evidence verification and honest abstention.
- P6: immutable human approval, guarded execution, recovery verification, and rollback handling.
- P7: reproducible comparisons against strong deterministic and non-neural baselines.

### 1.2 Explicit non-goals

- Production deployment on physical switches.
- Real PFC pause propagation, RoCE/DCQCN dynamics, ASIC queues, FEC, BER, or optical telemetry.
- Kubernetes, Kafka, NATS, service mesh, multi-region HA, or multi-NOS parity in the core.
- Arbitrary configuration generation or unrestricted shell/PromQL/gNMI access by an LLM.
- Fully autonomous remediation.
- Fine-tuning an LLM.
- Claiming a GNN is causal merely because it performs message passing.

## 2. Non-negotiable invariants

1. The diagnostic plane cannot read ground-truth labels, chaos parameters, answer-bearing scenario
   keys, post-clear data, or evaluator-only tables.
2. At decision time `t`, a model or rule may read only observations with event time `<= t`.
3. Chaos cleanup is never counted as remediation.
4. A remediation edit creates a new immutable plan version.
5. Approval binds the plan ID, version, SHA-256 digest, topology hash, and configuration revision.
   Approval expiry/revocation is a post-core hardening item under ADR-001.
6. The public API and workflow never possess device mutation credentials.
7. The executor has no public ingress and accepts only durable approved jobs.
8. Telemetry staleness, audit failure, configuration drift, insufficient alternate capacity, or
   ambiguous device state blocks execution.
9. Device effects are not described as “exactly once.” They are reconciled through read-before,
   guarded mutation, read-after, durable attempts, and outcome-unknown handling.
10. Every result carries code revision, dependency lock hash, image/model digests, dataset manifest,
    configuration hash, seeds, and evaluator version.
11. Test data is frozen before model selection and is not used for tuning.
12. Synthetic data is labeled `simulated: true` in labels, evidence packets, reports, dashboards,
    and exported artifacts.

## 3. Canonical architecture

### 3.1 Planes

```text
LAB DATA PLANE
  hosts <-> leaves <-> spines
  traffic only; no management shortcuts in reachability tests

LAB MANAGEMENT PLANE
  read-only telemetry identity -> SR Linux gNMI
  restricted executor identity -> allowlisted SR Linux gNMI Set
  chaos identity -> lab-only fault controls

OBSERVATION PLANE
  gNMIc -> Prometheus -> recording rules/dashboards
  syslog receiver -> normalized log events
  quality monitor -> freshness, gaps, resets, clock quality

INCIDENT PLANE
  detector signals -> idempotent correlator -> incident state machine
  rules/TS/GNN -> immutable detection and ranking records

REASONING PLANE
  read-only typed tools -> evidence snapshots -> typed claims
  deterministic claim predicates -> diagnosis/report -> remediation draft

HUMAN PLANE
  authenticated case UI -> approve/reject/request new plan version

EXECUTION PLANE
  durable job -> safety prechecks -> guarded device change
  read-back -> recovery predicates -> success/failure/outcome_unknown
  explicit rollback workflow when safe

EVALUATION PLANE
  isolated labels + frozen predictions -> metrics, CIs, ablations, reports
```

### 3.2 Process and credential boundaries

| Process | May read | May write | Forbidden |
|---|---|---|---|
| `telemetry` | device operational state | Prometheus/log signals | device config, ground truth |
| `chaos` | topology + campaign plan | evaluator fault ledger, lab impairments | approval/executor code |
| `correlator` | detector signals | incidents/events | labels, device mutation |
| `sensor` | causal telemetry snapshots | detections/rankings | labels, post-decision data |
| `trainer` | frozen TRAIN labels and TRAIN/VALIDATION artifacts | model artifacts | TEST labels, runtime incidents |
| `workflow` | runtime incidents/evidence | claims, diagnoses, draft plans | labels, approval, execution |
| `api` | cases and identity | decisions/new plan requests | device credentials |
| `executor` | approved jobs + live prechecks | device config, execution records | public requests, labels |
| `evaluator` | predictions + ground truth | metrics/reports | runtime diagnosis decisions |
| `migrator` | migrations | schema DDL | runtime service behavior |

Use separate PostgreSQL roles. `evaluation` schema grants are denied to API, workflow, runtime
sensors, and executor. The offline trainer receives only frozen TRAIN/VALIDATION label views; final
TEST labels remain evaluator-only.

### 3.3 Container networks

- `ingress`: reverse proxy/UI only.
- `app`: API, workflow, correlator.
- `data`: PostgreSQL and internal artifact access; never host-public.
- `observability`: Prometheus, Grafana, OpenTelemetry, optional Langfuse.
- `lab_mgmt`: gNMI/syslog endpoints; only telemetry, chaos, and executor attach.
- `lab_data`: fabric links and traffic hosts; never used to fake management reachability.

Bind browser-facing local services to `127.0.0.1`. Do not expose PostgreSQL, Prometheus, gNMI, the
executor, or Docker API. Do not mount the Docker socket into application containers. Containerlab
privileged operations run only inside the dedicated Linux lab VM.

## 4. Locked technology choices

Exact versions and OCI digests are selected at bootstrap, recorded in `docs/toolchain.md`, and
locked. “Latest” tags are forbidden.

| Area | Primary choice | Reason |
|---|---|---|
| Host | Apple Silicon macOS + isolated ARM64 Linux VM | supported local target |
| Lab | containerlab | topology-as-code and reproducible wiring |
| NOS | Nokia SR Linux ARM64 | real BGP and native gNMI |
| CI/fallback NOS | FRRouting | deterministic lower-resource integration |
| Language | Python 3.12 | common API, data, ML, and automation runtime |
| Dependency manager | `uv` + committed lock | deterministic environments |
| API/domain | FastAPI, Pydantic v2 | typed contracts and OpenAPI |
| Local ingress/TLS | Caddy with a local development CA | HTTPS required for Secure auth cookies |
| Persistence | SQLAlchemy 2, Alembic, asyncpg | PostgreSQL-native transactions/migrations |
| Database | PostgreSQL 16 + pgvector | operational state, audit, optional retrieval |
| Metrics | gNMIc, Prometheus, Grafana | minimal streaming telemetry path |
| Logs | small TCP/UDP syslog receiver + Drain3/regex | raw preservation plus structured events |
| Data artifacts | Parquet + JSON manifests + SHA-256 | immutable portable datasets |
| ML | PyTorch, PyTorch Geometric, scikit-learn, pandas, pyarrow | TS/GNN/baselines |
| Workflow | LangGraph with PostgreSQL-backed checkpoints | explicit stages and HITL pause |
| Local LLM | Ollama candidate bakeoff | local, versionable inference |
| Retrieval | BGE-small embedding + pgvector | bounded runbook lookup |
| UI | Jinja2 + HTMX behind local HTTPS ingress | minimal attack and maintenance surface |
| Auth | Argon2id, short-lived PyJWT in HttpOnly cookie, CSRF middleware | local RBAC; token rotation/revocation is hardening |
| Telemetry tracing | OpenTelemetry; Langfuse optional profile | workflow/tool visibility |
| Quality | ruff, mypy strict, pytest, Hypothesis | lint, types, properties |
| Security | pip-audit, Trivy, secret scan, SBOM | dependency/image controls |

### 4.1 Model qualification

Do not hard-code a fashionable LLM family in the architecture. `configs/models.yaml` lists exact
candidate revisions/digests. Qualify at least one laptop-sized and one stronger tier on the same
frozen structured-output set. Candidate families may include current tool-capable Qwen or Gemma
revisions available through Ollama. Selection criteria:

- strict schema success without repair;
- diagnosis accuracy on validation only;
- abstention quality;
- tool-call validity;
- token count, latency, and memory;
- prompt-injection resistance fixtures.

The winning exact digest becomes the primary. The runner must still support a second frozen tier for
reasoning ablation. Embedding model revisions are also pinned.

### 4.2 ML model contract

- Classical: operational-state rules, robust EWMA/z-score, and CUSUM/change-point.
- Neural TS primary: one compact causal forecasting/reconstruction model selected before TEST.
- Transformer TS is optional only after a precise causal forecasting objective is defined.
- Localization baseline: per-link feature MLP with no graph messages.
- Topology model: edge-ranking GraphSAGE/GAT variant over a typed interface/device graph.
- Root cause is a physical-link candidate. The GNN uses an edge head; it does not average two
  independently labeled endpoint probabilities.
- Raw node/link identifiers are forbidden as features.

## 5. Repository layout

```text
closcall/
├── README.md
├── Makefile
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── compose.yaml
├── configs/
│   ├── application.yaml
│   ├── models.yaml
│   ├── metrics.yaml
│   ├── safety-policy.yaml
│   └── traffic-profiles.yaml
├── lab/
│   ├── fabric.yaml             # only hand-authored fabric/IPAM source of truth
│   ├── topology-srl.clab.yml
│   ├── topology-frr.clab.yml
│   ├── topology-2s6l.clab.yml
│   ├── generated/              # rendered topology/config/inventory/IPAM artifacts
│   ├── configs/
│   ├── pki/
│   └── traffic/
├── src/closcall/
│   ├── config/
│   ├── domain/
│   ├── db/
│   ├── telemetry/
│   ├── incidents/
│   ├── chaos/
│   ├── datasets/
│   ├── sensors/rules/
│   ├── sensors/timeseries/
│   ├── sensors/graph/
│   ├── evidence/
│   ├── workflow/
│   ├── api/
│   ├── executor/
│   ├── evaluation/
│   └── observability/
├── migrations/
├── schemas/
│   ├── json/
│   └── openapi/
├── prompts/
├── runbooks/
├── dashboards/
├── deployments/
│   ├── compose/
│   └── prometheus/
├── scripts/
├── tests/
│   ├── unit/
│   ├── property/
│   ├── contract/
│   ├── integration/
│   ├── security/
│   ├── failure/
│   └── e2e/
├── artifacts/                 # generated, gitignored except manifests/reports
├── evals/
│   ├── manifests/
│   ├── reports/
│   └── protocols/
└── docs/
    ├── toolchain.md
    ├── architecture.md
    ├── threat-model.md
    ├── fidelity.md
    ├── operations.md
    ├── data-card.md
    ├── model-cards/
    └── decisions/
```

All importable Python is under `src/closcall`. Tests mirror package paths. Generated data never
enters source folders.

## 6. Naming and configuration standards

- Python: `snake_case` functions/modules, `PascalCase` types, strict typing at every boundary.
- Environment: `CLOSCALL_` prefix; nested settings use `__`.
- PostgreSQL: plural `snake_case` tables; UUID `id`; `<entity>_id` foreign keys; `_at` UTC
  timestamps; `_hash`/`_digest` SHA-256 hex; mutable aggregates include `version`.
- Metrics: `closcall_` namespace, base units, `_total` counters, `_seconds`, `_bytes`, `_ratio`.
- Metric labels are bounded: `node`, `interface`, `role`, `direction`, `queue`, `topology`.
  Incident IDs, user IDs, free text, and arbitrary paths are forbidden labels.
- Events: `schema_version`, `event_id`, `event_type`, `event_time`, `observed_at`, `source`,
  `trace_id`, payload.
- Artifacts: content-addressed manifest entry with URI, SHA-256, bytes, media type, schema version.
- Prompts: immutable `name.vN.md`; registry stores SHA-256 and model compatibility.
- Secrets never appear in YAML, `.env.example`, logs, traces, reports, or artifacts.

## 7. Fabric design

### 7.1 Base topology

- `spine1`, `spine2`.
- `leaf1` through `leaf4`.
- `host1` through `host4`, one host per leaf.
- Every leaf has one point-to-point link to every spine and one host-facing link.
- Base MTU is 1500 everywhere. Jumbo frames are a separately tested extension.
- Every topology node, interface, link, role, management address, ASN, and prefix is generated from
  `lab/fabric.yaml`; topology files, configs, target inventory, topology JSON, and human IPAM
  documentation are generated artifacts and must pass a consistency/determinism test.
- Link mapping is deterministic:
  `leafN:ethernet-1/1 <-> spine1:ethernet-1/N`,
  `leafN:ethernet-1/2 <-> spine2:ethernet-1/N`,
  `hostN:eth1 <-> leafN:ethernet-1/3`.
- Every virtual fabric link has a fixed nominal capacity declared in `fabric.yaml`; the base profile
  uses one value consistently so traffic percentages have a reproducible denominator.

### 7.2 Routing

- Unique private ASN per fabric switch:
  - spine1 `65101`, spine2 `65102`;
  - leaves `65001` through `65004`.
- Point-to-point links use deterministic `/31` assignments from `10.0.0.0/24`.
- For leaf `N` and spine `S`, allocate link index `2*(N-1)+(S-1)`; the leaf receives the even
  address and the spine the odd address within that `/31`.
- Loopbacks use `/32` from `10.255.0.0/24`.
- Host subnets use `172.16.<leaf>.0/24`; leaf gateway `.1`, host `.10`.
- eBGP on every leaf-spine link; no peer group may hide a wrong remote ASN.
- Leaves advertise only their loopback and directly attached host prefix.
- Spines advertise only their own loopback and accepted leaf routes.
- Import/export policies reject unexpected prefixes, default routes, private prefixes outside the
  declared sets, excessive prefix length, and over-limit prefix counts.
- ECMP requires two valid equal-cost next hops for remote host prefixes at each leaf.
- BFD is not assumed. It is enabled only after the exact SR Linux release proves supported timers
  and a separate convergence comparison is recorded.

### 7.3 Network acceptance

- All expected BGP sessions are established and no unexpected session exists.
- Advertised/accepted prefix sets exactly match the IPAM manifest.
- RIB and FIB contain two next hops for every eligible remote leaf prefix.
- Host reachability succeeds using only the data plane.
- MTU boundary and fragmentation behavior are verified.
- ECMP is tested with a deterministic set of at least hundreds of distinct five-tuples; both
  next hops must be used and distribution tolerance is declared before the test.
- Link-down convergence measures route withdrawal, packet-loss count, and restoration.
- Management-plane failure cannot be mistaken for data-plane failure.
- Teardown leaves no namespaces, veths, containers, routes, or traffic processes.

## 8. Traffic and fault contracts

### 8.1 Traffic

Traffic profiles define aggregate offered load at each expected bottleneck, not a vague percentage
per process. Each run records requested and observed bitrate, packet rate, flow count, five-tuple
seed, direction, burst/gap parameters, loss, RTT, and completion.

The base generator produces reproducible many-flow bursts resembling collective communication
rhythm. It is not called NCCL or all-reduce validation. Healthy hard-negative profiles include high
utilization without impairment and normal routing convergence.

### 8.2 Core fault classes

| Fault | Injector mechanism | Honest meaning | Allowed operational response |
|---|---|---|---|
| `admin_shutdown` | gNMI changes admin state | configuration-caused shutdown | restore prior state only when provenance/preconditions permit |
| `carrier_loss` | outer veth/link state down | physical connectivity loss abstraction | isolate/drain; operator repair, not “enable” |
| `intermittent_link` | controlled carrier transitions | link flap abstraction | drain/isolate |
| `rate_limited_uplink` | `tc tbf` with measured offered load | bandwidth bottleneck/congestion | capacity-safe drain or route preference change |
| `impaired_link` | `tc netem` loss/delay | lossy/latent link | capacity-safe drain |
| `healthy_control` | no fault | paired negative | no action |
| `telemetry_gap` | collector/subscription interruption | observation failure | block automation, restore telemetry |

Do not call `rate_limited_uplink` PFC/ECN. Do not call `impaired_link` degraded optics. Optional
synthetic ECN/optic-like features must be explicitly generated, isolated from raw observations, and
labeled synthetic.

### 8.3 Chaos lifecycle

`planned -> baselining -> injecting -> active -> clearing -> settling -> completed`

Any state may become `failed`; invalid baseline, missing telemetry, dirty pre-state, failed cleanup,
or unsettled recovery becomes `quarantined`.

Before injection, write a durable planned record and exact cleanup payload. After applying, verify
observed onset rather than trusting command completion. Use monotonic time for duration and UTC event
time for joins. A startup reconciler clears orphaned impairments or quarantines the lab. Cleanup
runs in `finally` and again during lab teardown.

The evaluator clears impairments after measurement. The executor never calls chaos cleanup.

## 9. Telemetry and time integrity

### 9.1 Required streams

- Interface admin/oper state: ON_CHANGE plus heartbeat where supported.
- BGP neighbor session state: ON_CHANGE plus heartbeat.
- Interface octets, packets, errors, discards: SAMPLE at verified interval.
- Queue counters only when the selected image/path proves available.
- Traffic-generator offered/received load and completion.
- gNMIc stream status, reconnect count, last-update age, parse errors.
- Syslog raw message plus normalized node, severity, facility, event time, receive time.

Exact YANG paths are release-specific and are locked only after `Capabilities`, sample `Get`, and
subscription fixtures pass. Static target configuration is preferred; do not grant gNMIc Docker
socket access merely for discovery.

### 9.2 Time contract

Store device event time, collector receive time, ingestion time, and query snapshot time. Validate
clock offset before every campaign. gNMI notifications may arrive out of order; ingestion sorts by
event time within a bounded watermark and records late data.

Counter transforms must handle:

- counter reset and wrap;
- missing samples and reconnect gaps;
- duplicate/out-of-order samples;
- interface disappearance/rename;
- cold start and stale values;
- zero-variance baselines.

Never forward-fill across an unbounded gap. Add missingness mask and sample-age features. A
telemetry-quality score accompanies every detection and blocks execution below policy.

### 9.3 Evidence snapshots

An evidence item stores the bounded query template ID, parameters, as-of time, returned samples,
units, source timestamps, quality flags, topology/config hash, and content hash. User/LLM-provided
raw PromQL is forbidden.

## 10. Dataset and evaluation protocol

### 10.1 Pre-registration

Before the full corpus:

- freeze the fault ontology and eligible link candidates;
- define the balanced scenario matrix and paired healthy/hard-negative controls;
- define minimum independent incidents per stratum from desired confidence-interval width;
- freeze split manifests and exclusion/quarantine rules;
- define alarm matching, persistence, hysteresis, cooldown, and missed-detection handling;
- define every metric, averaging method, confidence interval, and tie rule.

`>=300 incidents` may be an operational target, but it is not a statistical design by itself.

### 10.2 Split tracks

1. Location-inductive: disjoint physical-link groups for train/validation/test within 2s4l.
2. Topology-size transfer: train/validation on 2s4l; frozen 2s6l test.
3. Operating-condition shift: optional held-out traffic/severity combinations.

Split before windowing or preprocessing. All repeats sharing incident, seed family, campaign batch,
or overlapping time range stay in one split. Purge adjacent blocks by at least lookback,
persistence, and cooldown. Fit scalers, imputers, normal baselines, calibrators, and thresholds on
TRAIN/VALIDATION only. TEST is evaluated only after selection freezes.

### 10.3 Causal windows

For decision time `t`, every feature reads only `[t-W, t]`. No backward interpolation, future
aggregation, `t_clear`, `t_settled`, incident duration, split, scenario key, or ground truth may
enter a feature.

- Detection runs continuously before injection.
- `t_detected` is the first persisted threshold crossing after observed injection onset.
- End-to-end localization uses the snapshot ending at `t_detected`.
- A separate fixed-cutoff oracle localization study isolates localization quality from detector
  latency.
- Multiple windows from one incident are weighted/grouped as one independent incident.
- Online and offline feature implementations must pass golden parity tests.

### 10.4 Metrics

- Detection: event precision/recall/F1, FP per healthy hour, coverage, PR-AUC, secondary ROC-AUC,
  latency median/p90/p95 with misses explicitly counted.
- Localization: top-1, top-3, MRR, macro per class, conditional-on-detection and end-to-end.
- Calibration: Brier/ECE when confidence is shown.
- Claims: supported/contradicted/insufficient, coverage, blinded human entailment agreement.
- Diagnosis: target-and-class accuracy, abstention coverage/accuracy.
- Remediation: policy-safe rate, correct action conditional and unconditional, forbidden-action
  rate, recovery success, execution-to-recovery time, rollback success.
- Operations: tool calls, input/output tokens, wall time, inference latency, cost, retries.
- Statistics: per-class/load/severity/topology results and paired 95% bootstrap intervals clustered
  by incident/campaign; multiple model seeds reported.

## 11. Sensor execution sequence

1. Implement operational-state finite-state rules.
2. Implement robust EWMA/z-score and CUSUM.
3. Freeze causal event evaluator and validation-tuned thresholds.
4. Implement one primary compact TS model with exact channels, masks, context, objective, and
   checkpoint rule.
5. Generate out-of-fold TRAIN anomaly scores before using them as GNN inputs.
6. Build canonical typed graph retaining down links as candidates.
7. Train per-link MLP baseline.
8. Train edge-ranking GNN with incident-level weighting.
9. Run permutation invariance, ID removal, degree/role-only, no-message-passing, and
   topology-shuffled tests.
10. Freeze selection, then run each test track once.

If the neural model does not outperform a strong baseline, publish the result and keep the simpler
system. Do not tune on TEST or add architectures until a separability/label/split audit completes.

## 12. Evidence-grounded workflow

### 12.1 Stages

`collect -> hypothesize -> test -> commit_or_abstain -> draft_plan -> interrupt`

- Collect creates immutable evidence snapshots using typed read-only tools.
- Hypothesize emits at most three structured hypotheses.
- Test requests targeted evidence and records confirming, contradicting, or insufficient outcomes.
- Commit emits typed atomic claims or `undiagnosed`.
- Draft plan maps only verified diagnosis classes to allowlisted templates.
- Interrupt persists state and waits. No side effect may occur before or during the interrupt.

### 12.2 Typed claims

Each claim includes:

`claim_id, predicate_type, subject, metric_or_event, operator, comparison, interval, polarity,
evidence_ids`.

Deterministic predicates execute against immutable snapshots and return `supported`,
`contradicted`, or `insufficient`. Narrative prose is generated only after verification. Adversarial
fixtures include wrong polarity, unit, interface, time, nearby-but-irrelevant value, and
cherry-picked samples.

### 12.3 Tools

- `get_incident_summary`
- `get_ranked_links`
- `get_interface_state`
- `get_bgp_state`
- `get_metric_window` using approved template IDs
- `get_log_events`
- `get_topology_neighbors`
- `search_runbooks`
- `get_similar_resolved_incidents`

Every tool enforces incident scope, as-of bounds, result limits, timeout, schema validation, and
trace/budget accounting. Retrieved logs/runbooks are untrusted text and cannot directly populate
executor parameters.

### 12.4 Reasoning experiments

Policy-only comparison uses identical frozen evidence packets, model revision, decoding settings,
prompts, and token/cost budget. Interactive-tool comparison is separate because evidence
acquisition becomes part of the treatment. Run repeated seeded trials and report schema retries,
tool failures, abstentions, tokens, latency, and cost.

## 13. Approval, execution, and rollback

Detailed fields and transitions are in `04-Data-API-and-State-Contracts.md`.

### 13.1 Plan requirements

Every immutable plan version includes:

- exact ordered actions and bounded parameters;
- target topology hash/config revision;
- preconditions and safety invariants;
- expected postconditions and recovery predicates;
- captured rollback procedure;
- risk/blast-radius class;
- provenance and SHA-256 digest.

An edit supersedes the old version and invalidates its decisions.
Approval expiry and revocation are post-core hardening items under ADR-001.

### 13.2 Mandatory prechecks

- valid approval for the exact digest and plan version;
- no topology/config drift;
- fresh, complete telemetry;
- target/action/parameters on allowlists;
- target is not a management interface;
- no competing execution on the target;
- alternate path healthy;
- remaining capacity above configured headroom;
- change cannot remove the final usable path;
- audit and database writable;
- recovery and rollback predicates defined.

### 13.3 Execution semantics

Core uses one executor. Approval inserts one execution job in the same database transaction,
protected by unique plan-version and idempotency-key constraints. The executor captures pre-state,
compares desired/actual state, performs the smallest mutation, reads state back, and evaluates
recovery. Ambiguous timeout becomes `outcome_unknown`, never success. Executor restart reconciles
database intent with device state before retry. Multi-worker leasing and a transactional outbox are
post-core hardening items under ADR-001.

Rollback is a separate state machine. It runs completed steps in reverse only when rollback
preconditions still hold. Unsafe or failed rollback stops and requires operator intervention.

## 14. Ordered implementation gates

### Gate 0 — authority and threat model

Work:

- accept canonical documents;
- write trust-boundary/data-flow diagram;
- enumerate assets, actors, credentials, prompt-injection paths, and failure modes;
- create ADR template and source register;
- pin the exact external benchmark commit used for claims.

Exit:

- no unresolved P0 contradiction;
- ground-truth isolation and credential ownership are explicit;
- every core proof maps to acceptance tests.

### Gate 1 — repository and environment

Work:

- create repository layout, package, lock, CI, Makefile, config loader, structured logging;
- pin image digests and dependencies;
- provision the local development CA, trusted `closcall.local` certificate, and loopback-only Caddy
  ingress used by the browser UI;
- implement `make doctor`;
- benchmark one SR Linux node and one full 2s4l topology for CPU/RAM/disk/start time.

Exit:

- clean clone passes lint/types/unit/secret/dependency checks;
- doctor reports exact capabilities;
- shard count is derived from measured peak resources with at least 30% memory headroom, never
  assumed; the default is one lab.

### Gate 2 — topology/IPAM/config rendering

Work:

- implement IPAM schema and deterministic rendering;
- configure interfaces, policies, BGP, host routes, management PKI;
- add static topology validation.

Exit:

- rendered config matches IPAM exactly;
- malformed ASN/prefix/interface fixtures fail before deployment.

### Gate 3 — network feasibility

Work:

- deploy base topology;
- run routing, reachability, MTU, ECMP, convergence, and teardown tests.

Exit:

- all network acceptance criteria in §7.3 pass twice from clean deployment;
- packet-loss/convergence evidence retained.

### Gate 4 — trustworthy telemetry

Work:

- validate exact YANG paths;
- configure subscriptions, Prometheus, logs, dashboards, quality monitors;
- implement timestamp, reset, gap, and staleness handling.

Exit:

- every node/eligible interface appears;
- known state changes meet measured visibility bounds;
- collector interruption is detected and automation blocks;
- evidence snapshot hashes reproduce.

### Gate 5 — fault framework

Work:

- implement typed fault plugins, write-ahead ledger, onset verification, cleanup/reconciliation;
- implement healthy controls and hard negatives;
- verify each fault changes the intended data-plane condition.

Exit:

- smoke campaign leaves no dirty state;
- labels align to observed onset;
- fault names and evidence do not overclaim physical fidelity.

### Gate 6 — deterministic vertical slice

Work:

- rules detect one fault;
- idempotent correlator opens one incident;
- evidence and typed claims produce one diagnosis;
- a prebuilt safe plan is approved and executed through isolated executor;
- recovery/audit chain completes.

Exit:

- no LLM or neural model is required;
- duplicate signals/requests do not duplicate incident or execution;
- injector cleanup is not the remediation.

### Gate 7 — data contracts and corpus pilot

Work:

- migrate full PostgreSQL schema;
- freeze event/artifact/parquet schemas;
- freeze evaluation protocol/splits;
- collect randomized pilot with healthy/hard-negative controls;
- run causal-window parity/leakage tests.

Exit:

- split invariants pass;
- labels/features visibly align;
- exclusions are predeclared;
- DB concurrency and role tests pass.

### Gate 8 — full corpus

Work:

- run checkpointed campaigns at measured safe parallelism;
- verify lab state between incidents;
- hash all artifacts and manifests;
- quarantine automatically on quality/recovery failure.

Exit:

- pre-registered stratum counts are met;
- artifacts verify;
- no split/provenance/quality violation exists.

### Gate 9 — sensor baselines and neural models

Work:

- execute §11 in order;
- retain model cards, configs, seeds, checkpoints, and validation decisions.

Exit:

- frozen test reports include all misses, CIs, strata, and ablations;
- results reproduce from manifest/run ID.

### Gate 10 — diagnostic workflow

Work:

- implement evidence tools, typed claims, verifier, report generator, and abstention;
- qualify local LLM candidates;
- test prompt injection and budget exhaustion.

Exit:

- unsupported/contradictory claims cannot be committed;
- ground truth remains inaccessible;
- failure yields honest `undiagnosed`, never fabricated certainty.

### Gate 11 — secured HITL and executor

Work:

- implement Argon2id login, short-lived JWT in an HttpOnly/Secure/SameSite cookie, RBAC, IDOR
  protection, and CSRF tokens on every state-changing browser request;
- immutable plan decisions;
- single-executor durable jobs with DB uniqueness/idempotency, reconciliation, and rollback;
- append-only audit that blocks state changes when audit persistence fails.

Exit:

- every security/execution acceptance row passes;
- stale/edited/drifted plans fail closed;
- ambiguous and rollback-failed states remain visible.

Post-core under ADR-001: approval expiry/revocation, token rotation/revocation, rate limiting,
multi-worker leases/outbox, and cryptographic audit chaining.

### Gate 12 — controlled evaluation

Work:

- run causal detection/localization studies;
- run policy-only and interactive reasoning studies;
- run end-to-end factorial combinations;
- evaluate safety offline, then controlled execution;
- run pinned NIKA adapter as an agent-only external result.

Exit:

- reports are generated only from immutable run IDs;
- NIKA paper version and repository snapshot are distinguished;
- no internal sensor metric is misrepresented as NIKA validation.

### Gate 13 — packaging and handoff

Work:

- complete demo, operator guide, threat/fidelity docs, and data/model cards;
- execute the clean-clone demo;
- generate README tables from reports.

Exit:

- master acceptance matrix is green;
- every public claim traces to an artifact;
- known limitations and failed experiments are published.

## 15. Required Make targets

`doctor`, `bootstrap`, `lint`, `typecheck`, `test-unit`, `test-contract`, `test-integration`,
`test-security`, `test-failure`, `test-e2e`, `db-up`, `db-migrate`, `db-reset-test`, `lab-up`,
`lab-check`, `lab-down`, `traffic-smoke`, `telemetry-up`, `telemetry-check`, `fault-smoke`,
`corpus-pilot`, `corpus`, `dataset-build`, `dataset-verify`, `train-rules`, `train-ts`,
`train-gnn`, `evaluate-sensors`, `workflow-run`, `api-up`, `executor-up`, `evaluate-agent`,
`evaluate-e2e`, `nika`, `demo`, `reports`.

Post-core hardening targets `backup` and `restore-test` are added only when ADR-001 backlog work is
promoted.

Every target is non-interactive unless interaction is its purpose, returns non-zero on failure, and
prints the artifact/run IDs it created.

## 16. Change control

- Architecture, schema, ontology, split, metric, safety policy, or dependency changes require ADRs.
- An ADR states context, decision, alternatives, consequences, migration, and affected tests.
- A failed gate may simplify the design. It may not silently weaken the acceptance criterion.
- Changes after TEST freeze create a new benchmark version; old results remain immutable.
- Primary-source claims include URL, access date, version/commit, and the exact supported statement.
- Current repository facts and paper-version facts are never conflated.

## 17. Stop conditions

Stop and correct before proceeding when:

- one full SR Linux topology exceeds safe host resources;
- telemetry cannot distinguish the intended fault from missing data;
- fault cleanup is unreliable;
- split leakage or causal parity tests fail;
- ground truth is reachable from runtime roles;
- a safety precondition cannot be evaluated;
- audit writes are not durable;
- an approved digest can execute a different plan;
- an executor timeout cannot be reconciled;
- a result cannot be reproduced from immutable inputs.

## 18. Master definition of done

The project is complete only when every row in `05-Acceptance-Matrix.md` is green and:

- a clean clone builds the verified fabric and tears it down cleanly;
- causal telemetry produces reproducible rules and ML results on frozen splits;
- a report contains only supported typed claims or explicit insufficiency;
- the human approves the exact immutable plan that executes;
- execution fails closed under stale data, drift, inadequate capacity, duplicate requests, and
  ambiguous device outcomes;
- recovery or rollback is measured and fully traceable;
- ground truth remains isolated throughout;
- public results include confidence intervals, misses, abstentions, quarantines, and limitations;
- the entire chain is traceable:
  incident -> signals -> detection -> evidence -> claims -> diagnosis -> plan digest -> decision ->
  execution steps -> recovery checks -> audit events -> evaluation run.
