# ClosCall — Acceptance and Traceability Matrix

Status: authoritative completion checklist — **AMENDED (A1): scope waivers applied per Master release rule; see Waivers section + docs/decisions/ADR-001-scope-waivers.md**
Rule: a row is green only when the command passes from a clean state and the evidence artifact is
retained.

## A. Planning and reproducibility

| ID | Acceptance | Evidence |
|---|---|---|
| A01 | Canonical documents have no unresolved P0 contradiction | inspection report + ADRs |
| A02 | Every dependency/image/model has exact version or digest | toolchain manifest |
| A03 | Every public source claim records version/commit and access date — **[A1] NIKA and all fast-moving repos MUST be pinned to an exact commit SHA; reported stats are stats of that SHA, never of "main"** | source register |
| A04 | Clean clone creates identical generated configs | artifact hashes |
| A05 | Every result identifies code, lock, image, model, dataset, prompt, config, seeds | run manifest |

## B. Network fabric

| ID | Acceptance | Evidence |
|---|---|---|
| B01 | Machine-readable fabric validates unique endpoints/IPs/prefixes/ASNs | validator report |
| B02 | Expected interfaces are operational | state snapshot |
| B03 | Expected BGP sessions only are established | neighbor snapshot |
| B04 | Import/export prefix sets exactly match policy | Adj-RIB/RIB report |
| B05 | No default, P2P, martian, or unexpected aggregate leaks | negative route tests |
| B06 | Remote host prefixes have exactly two FIB next hops | FIB snapshot |
| B07 | Full host reachability uses only data plane | matrix report |
| B08 | MTU boundary test passes | packet test |
| B09 | Deterministic multi-flow ECMP meets declared distribution test | counter/statistical report |
| B10 | Path failure converges within measured loss/goodput bounds | timeline artifact |
| B11 | Spine failure and restoration are measured | timeline artifact |
| B12 | Teardown removes containers/veth/qdisc/network/firewall residue | teardown report |

## C. Telemetry integrity

| ID | Acceptance | Evidence |
|---|---|---|
| C01 | Exact release-specific YANG paths pass capability/Get/Subscribe fixtures | fixture report |
| C02 | Every expected node/interface series is present with bounded cardinality | inventory report |
| C03 | Event, receive, ingest, and snapshot timestamps are preserved | sample artifact |
| C04 | Clock offset/uncertainty stays within declared policy | clock report |
| C05 | Counter reset/wrap, out-of-order, duplicates, and gaps pass tests | golden tests |
| C06 | Collector/subscription failure creates stale-data signal | failure test |
| C07 | Stale or low-quality telemetry blocks execution | security test |
| C08 | Evidence snapshot hash and replay are stable | replay report |

## D. Fault framework

| ID | Acceptance | Evidence |
|---|---|---|
| D01 | Fault write-ahead record exists before mutation | DB trace |
| D02 | Requested and observed onset are distinct and recorded | label trace |
| D03 | Direction/capacity/load/qdisc effect is verified | impairment report |
| D04 | Healthy controls and hard negatives are represented | campaign manifest |
| D05 | Fault remains active while mitigation recovery is measured | timeline |
| D06 | Harness cleanup is never reported as remediation | evaluation assertion |
| D07 | Crash/restart reconciliation leaves no orphan impairment | failure test |
| D08 | Dirty baseline/cleanup/telemetry causes quarantine | negative tests |

## E. Incidents and data

| ID | Acceptance | Evidence |
|---|---|---|
| E01 | Fresh migrations succeed against PostgreSQL | CI report |
| E02 | Runtime roles cannot access ground truth or DDL | grant tests |
| E03 | Concurrent duplicate signals create one incident | concurrency test |
| E04 | Incident transitions are versioned, atomic, and evented | state tests |
| E05 | Artifacts are content-addressed and checksum-verified | manifest |
| E06 | Split tests prove no incident/link/seed/batch/time overlap | leakage report |
| E07 | Test manifests freeze before selection | signed/hash manifest |
| E08 | Online/offline causal features match | parity fixtures |

## F. Sensors and evaluation

| ID | Acceptance | Evidence |
|---|---|---|
| F01 | Rules/EWMA/CUSUM use identical causal inputs and event matching | protocol report |
| F02 | Thresholds/calibration use validation, never test | lineage assertion |
| F03 | Detection reports misses, FP/hour, coverage, latency quantiles, PR-AUC | test report |
| F04 | GNN training uses out-of-fold TRAIN anomaly scores | lineage report |
| F05 | Link-ranking MLP and no-message baseline exist | ablation report |
| F06 | IDs are excluded and permutation/topology tests pass | invariance report |
| F07 | Topology-transfer and location-inductive results remain separate | result tables |
| F08 | Results include strata, seeds, and incident-clustered 95% CIs | generated report |

## G. Evidence and reasoning

| ID | Acceptance | Evidence |
|---|---|---|
| G01 | Every committed narrative claim maps to typed atomic claims | report trace |
| G02 | Wrong polarity/unit/interface/time/relevance fixtures are rejected | adversarial tests |
| G03 | Contradicted/insufficient evidence cannot become committed certainty | negative tests |
| G04 | Tool queries enforce incident and as-of bounds | contract tests |
| G05 | Logs/runbooks cannot inject executable parameters | security tests |
| G06 | LLM/schema/tool failure produces abstention or deterministic fallback | failure tests |
| G07 | Policy-only ablation uses identical frozen evidence | experiment manifest |
| G08 | Interactive and policy-only experiments are not conflated | reports |

## H. Approval and execution

| ID | Acceptance | Evidence |
|---|---|---|
| H01 | Plan versions are immutable and SHA-256 addressed | DB tests |
| H02 | Decision binds exact version/digest/topology/config — **[A1] expiry binding WAIVED to backlog** | decision trace |
| H03 | Edit or drift blocks execution — **[A1] expiry/revocation blocking WAIVED to backlog** | negative tests |
| H04 | API/workflow cannot obtain device mutation credentials | trust-boundary tests |
| H05 | Executor has no public ingress | network scan/config test |
| H06 | Duplicate execution prevented by DB unique constraint + idempotency key (single-executor core) — **[A1] multi-worker leasing / transactional outbox WAIVED to backlog** | concurrency test |
| H07 | Last path, management interface, stale telemetry, and low headroom fail closed | safety tests |
| H08 | Pre-state and rollback payload are captured before mutation | execution trace |
| H09 | Timeout ambiguity becomes outcome unknown and reconciles | failure test |
| H10 | Recovery uses service predicates while fault remains active | recovery report |
| H11 | Rollback reverses completed steps or exposes rollback failure | rollback report |

## I. Security and audit

| ID | Acceptance | Evidence |
|---|---|---|
| I01 | TLS/separate read and write identities protect device management | connection tests |
| I02 | JWT claims, RBAC, IDOR, secure-cookie, and CSRF protections pass — **[A1] token rotation/revocation infrastructure and rate limits WAIVED to backlog** | security suite |
| I02a | Browser UI is reachable only through loopback HTTPS; Secure cookies are never issued over plain HTTP | ingress/security test |
| I03 | No secret appears in source, logs, traces, reports, audit, or exported artifacts | scan report |
| I04 | Containers use least privilege and pinned digests | configuration/SBOM |
| I05 | Audit log is append-only with enforced FK integrity — **[A1] cryptographic tamper-evidence (hash chain) WAIVED to backlog** | audit tests |
| I06 | Audit failure blocks state mutation | failure test |
| I07 | Ground-truth access attempt by runtime identity fails | grant test |

## J. Operations and final proof

| ID | Acceptance | Evidence |
|---|---|---|
| J01 | Full-stack resource use has measured headroom | resource report |
| J02 | Sharding activates only from measured capacity/isolation | scheduler report |
| J03 | Executor and PostgreSQL restarts have deterministic outcomes — **[A1] full multi-service restart matrix (Prometheus/LLM/device permutations) WAIVED to backlog** | failure suite |
| J04 | **[A1] ROW WAIVED to backlog** — backup/restore program is a hardening item, not a core gate | (backlog) |
| J05 | FRR CI and separate SR Linux acceptance both pass | CI reports |
| J06 | Clean-clone demo completes deploy-to-teardown without hidden manual repair | demo run |
| J07 | Every README number is generated from an immutable run ID | traceability check |
| J08 | Fidelity limitations and negative findings are published | final docs |

## Waivers under Amendment A1

Per the Master release rule (waived rows must be marked, ADR-justified, and README-reflected):
- WAIVED rows/clauses: H02 (expiry), H03 (expiry/revocation), H06 (leasing/outbox), I02 (token rotation/revocation infrastructure and rate limits; CSRF remains core), I05 (hash chain), J03 (full restart matrix), J04 (backup/restore).
- Justification: docs/decisions/ADR-001-scope-waivers.md. Backlog home: docs/backlog.md.
- These waivers apply to CORE completion only. Backlog items remain fully specified in documents 03/04 for later hardening; nothing is deleted.

## Master release rule

No "complete," "autonomous," "safe," "validated," or measured resume claim may be made until all
applicable rows are green. Any waived row must be explicitly marked, justified by ADR, and reflected
as a limitation in the README and report. **[A1] The waivers above satisfy this clause; the README
limitation entry is mandatory at release.**
