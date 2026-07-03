# CLOSCALL — THE BUILD BIBLE
### Complete execution plan: every phase, every component, every field, every fallback. No timeline — only ordered work.
*(Written under working title "Fabric Copilot"; project name is ClosCall.)*

> **SUPERSEDED:** Retained as the first planning draft. Do not implement from this file.
> `03-Canonical-Execution-Bible.md`, `04-Data-API-and-State-Contracts.md`, and
> `05-Acceptance-Matrix.md` replace it after the senior engineering inspection.

---

## 0. DOCTRINE (read first, reread when stuck)

1. **Phases are sequential.** Never start a phase before the previous phase's exit criteria are ALL green.
2. **When a step fails, consult its contingency branch.** Universal rule: **simplify, never add.**
3. **Nothing is "done" until it runs from a fresh clone** (`git clone && make <target>`).
4. **Every number in the README comes from the eval harness.** No hand-computed claims, ever.
5. **Every synthetic signal carries `simulated: true`.** No exceptions, including demos.
6. **The single-agent configuration must stay runnable at all times** (ablation row).
7. **Dependency law:** a library enters the repo only with a pinned version + a line in `docs/toolchain.md` linking its primary docs.
8. **You are the pilot.** AI coding tools accelerate implementation; every design decision below is yours to defend in an interview. At each phase exit, explain the phase aloud without notes. Can't? Phase isn't done.

---

## 1. SYSTEM ARCHITECTURE (canonical)

LAB PLANE: containerlab topology (SR Linux x6: 2 spine, 4 leaf) + 4 host containers (traffic generators) + chaos engine (fault injection + ground-truth label emitter)
  -> gNMI subscribe + syslog ->
TELEMETRY PLANE: gnmic -> Prometheus (metrics) | Grafana (dashboards) | syslog-collector -> Postgres (logs)
  -> Prometheus HTTP API, parquet exports ->
ML PLANE: dataset builder -> parquet windows + graph tensors | rules baseline | TS anomaly detector | GNN localizer (all write detections -> Postgres)
  -> incident opened (idempotent) ->
REASONING PLANE: LangGraph phase-gated workflow (FastAPI service): collect -> hypothesize -> test -> commit -> remediate -> [interrupt]. Tools: prometheus, gnn_ranking, logs, topology, runbooks, memory. Deterministic verifier on every committed claim.
  -> remediation draft ->
HUMAN PLANE: HITL approval UI (FastAPI + HTMX) | JWT auth (viewer/approver) | executor (gNMI Set / tc revert) | rollback | audit log
  ->
EVALUATION PLANE: eval harness scores everything vs ground-truth labels | ablations (detection/localization/reasoning/end-to-end) | NIKA adapter | Langfuse + OTel.

---

## 2. TECH STACK (locked; pin exact versions at bootstrap in `docs/toolchain.md`)

| Layer | Choice | Role | Fallback |
|---|---|---|---|
| Host | macOS (Apple Silicon) + **OrbStack** Linux VM | runs everything | Docker Desktop |
| Lab orchestration | **containerlab** (in the OrbStack VM) | deploys topology from YAML | — |
| Network OS | **Nokia SR Linux** (`ghcr.io/nokia/srlinux`, ARM64) | the 6 switches | FRR profile (CI + fallback) |
| Hosts/traffic | Alpine/`network-multitool` containers + Python traffic scripts | pretend GPUs | iperf3 |
| Telemetry collector | **gnmic** (`ghcr.io/openconfig/gnmic`) | gNMI subscribe -> Prometheus output | prometheus_write mode |
| Metrics store | **Prometheus** | time-series | — |
| Dashboards | **Grafana** | human view + demo | — |
| Relational store | **PostgreSQL 16 + pgvector** | incidents/evidence/audit + embeddings | SQLite (dev only) |
| ML | **Python 3.12, PyTorch (MPS), PyTorch Geometric, scikit-learn, pandas, pyarrow** | sensors + datasets | — |
| TS pretrained ablation | **Chronos** (HF) zero-shot | ablation row | skip row |
| Log parsing | **Drain3** + regex | syslog -> events | DistilBERT fine-tune (only if Drain3 fails) |
| LLM (local) | **Ollama**: small tier `llama3.1:8b`-class, big tier `qwen2.5:14b`-class | reasoning | API tier |
| Embeddings | **BAAI/bge-small-en-v1.5** (384-dim) | runbook search | e5-small |
| Agent framework | **LangGraph** + Pydantic structured outputs | phase-gated workflow | plain function pipeline |
| API framework | **FastAPI + uvicorn** | workflow service + HITL | — |
| HITL UI | **FastAPI + Jinja2 + HTMX** (no SPA — scope discipline) | approval console | CLI approval tool |
| Auth | **PyJWT**, bcrypt | viewer/approver roles | — |
| LLM observability | **Langfuse** (self-hosted, MIT) + OpenTelemetry | traces/cost/latency | Arize Phoenix |
| Tests | **pytest**, ruff, mypy | quality | — |
| CI | **GitHub Actions** (FRR profile for integration smoke) | fresh-clone guarantee | — |
| Packaging | **docker compose** (profiles: `core`, `obs`) | one-command stack | K8s/Helm = extension |

---

## 3. REPOSITORY LAYOUT (create exactly this)

```
closcall/
├── README.md                  # pitch, related-work table, fidelity statement, results tables, demo gif
├── Makefile                   # ALL entrypoints (§14 target list)
├── docker-compose.yml         # profiles: core (pg, prometheus, grafana, gnmic), obs (langfuse)
├── pyproject.toml             # single Python project; lockfile
├── .env.example               # every env var documented; real .env gitignored
├── .github/workflows/ci.yml   # lint -> typecheck -> unit -> integration-smoke (FRR)
├── docs/
│   ├── toolchain.md           # pinned versions + primary-doc links (Doctrine #7)
│   ├── fidelity.md            # the honesty statement (verbatim in README too)
│   ├── architecture.md
│   ├── decisions/             # ADR-NNN-*.md — one file per irreversible decision
│   └── article/               # technical article draft
├── lab/
│   ├── topology.clab.yml      # THE lab definition (SR Linux profile)
│   ├── topology-frr.clab.yml  # CI/fallback profile, same shape
│   ├── configs/               # per-node startup configs (leaf1.cfg … spine2.cfg)
│   ├── ipam.md                # the IP/ASN plan (§6.2) — single source of truth
│   └── traffic/
│       ├── collective.py      # all-reduce-shaped traffic generator
│       └── profiles.yaml      # low/med/high load definitions
├── chaos/
│   ├── faults/                # link_down.py, link_flap.py, congestion.py, gray.py
│   ├── labels.py              # ground-truth label writer (schema §8.3)
│   ├── settle.py              # event-driven settle detection
│   ├── scenarios.yaml         # the campaign matrix
│   └── runner.py              # corpus campaign orchestrator
├── telemetry/
│   ├── gnmic.yaml             # subscriptions + prometheus output
│   ├── prometheus.yml
│   ├── grafana/               # provisioned datasource + 2 dashboards
│   └── syslog_collector.py    # UDP syslog -> Postgres `logs`
├── datasets/
│   ├── builder.py             # Prometheus -> parquet windows + graph tensors (§9.1)
│   ├── splits.py              # leakage-safe split logic (§9.2) — REVIEWED TWICE
│   └── schema.md              # parquet/tensor formats documented
├── sensors/
│   ├── rules/baseline.py      # thresholds + correlation (§10.1)
│   ├── ts/                    # features.py, model.py, train.py, infer.py
│   ├── gnn/                   # graph.py, model.py, train.py, infer.py, ablate.py
│   └── logsvc/parser.py       # Drain3 pipeline
├── workflow/
│   ├── state.py               # LangGraph state schema (Pydantic)
│   ├── graph.py               # phase-gated graph + --mode=single variant
│   ├── stages/                # collect.py, hypothesize.py, test.py, commit.py, remediate.py
│   ├── tools/                 # one file per tool (§11.3), typed signatures
│   ├── prompts/               # versioned templates name.vN.md + registry.py (hash-logged)
│   └── verifier.py            # deterministic groundedness checks (§11.4)
├── hitl/
│   ├── app.py                 # FastAPI: approval UI + REST (§12)
│   ├── auth.py                # JWT, roles
│   ├── executor.py            # approved actions -> gNMI Set / tc revert; stores inverse for rollback
│   └── templates/             # Jinja2 + HTMX
├── evals/
│   ├── metrics.py             # every formula from §13.1, unit-tested
│   ├── run_bench.py           # full internal benchmark
│   ├── ablations.py           # 3 controlled experiments + end-to-end
│   ├── nika/                  # external-benchmark adapter
│   └── reports/               # generated tables (md) — committed
├── db/
│   ├── schema.sql             # §9 verbatim
│   └── migrations/            # alembic
├── scripts/
│   ├── bootstrap.sh           # Phase 0 automation
│   └── demo.sh                # one-command end-to-end demo
└── tests/
    ├── unit/                  # metrics, splits, verifier, label schema, tools
    ├── integration/           # one full incident on FRR profile
    └── conftest.py
```

---

## 4. CONVENTIONS (locked)

- **Python:** ruff + mypy strict on `sensors/`, `evals/`, `workflow/`; Pydantic/dataclasses wherever data crosses a boundary.
- **Naming:** snake_case files/functions; PascalCase classes; env vars prefixed `FC_` (`FC_PG_DSN`, `FC_OLLAMA_URL`, `FC_LLM_TIER`).
- **DB:** plural tables, snake_case columns, UUID v4 PKs named `id`, FKs `<singular>_id`, every table `created_at timestamptz default now()`, all times UTC.
- **Events/labels:** JSON, Pydantic-validated before write; every schema has `schema_version`.
- **Commits:** conventional commits; one phase = one PR to `main` even solo (forces self-review).
- **Config:** pydantic-settings reads `.env`; zero secrets in code/YAML.
- **Logging:** structlog JSON to stdout; incident_id as a bound field everywhere.
- **Decisions:** any interview-defensible choice -> 10-line ADR in `docs/decisions/`.

---

## 5. PHASE 0 — ENVIRONMENT BOOTSTRAP

**Steps:** (1) Install OrbStack; Ubuntu ARM VM `clab`, ≥6 CPU, ≥16 GB. (2) In VM: Docker, containerlab, git, make, Python 3.12, uv. (3) Pull images: srlinux, gnmic, prometheus, grafana, postgres16+pgvector. Ollama natively on macOS (Metal); pull both model tiers. (4) `git init closcall` with §3 tree stubbed. (5) Write `docs/toolchain.md` with EXACT versions + doc links. 
**Exit:** `make doctor` (write it: checks docker, clab, images, python deps, ollama, pg) exits 0.
**Contingency:** SR Linux ARM issues -> verify tag/platform; if blocked, proceed on FRR profile, file the issue — do not stall.

---

## 6. PHASE 1 — THE LAB

**6.1 Topology:** spine1, spine2, leaf1..4 (kind nokia_srlinux), host1..4 (linux). Links: every leaf<->every spine (leafN:e1-1<->spine1, leafN:e1-2<->spine2); hostN:eth1<->leafN:e1-3.
**6.2 IPAM/ASN (write `lab/ipam.md`):** RFC 7938 style — spines share AS 65100; leaves 65001–65004; eBGP everywhere. P2P /31s from 10.0.0.0/24 (assign sequentially, document each). Loopbacks 10.255.0.0/24: spine1=.1, spine2=.2, leaf1..4=.11..14. Server subnets 172.16.N.0/24 per leafN (host=.10, gw=.1), advertised into BGP. ECMP: BGP multipath max-paths ≥2 on leaves.
**6.3 Node configs:** interfaces + /31s, loopback, BGP neighbors per ipam.md, multipath, export policy, gNMI server enabled (insecure OK inside lab — note in fidelity.md), syslog -> collector.
**6.4 Traffic gen:** rounds of all-to-all bursts (every host -> every other, T_burst=5s, gap=2s), approximating all-reduce rhythm; profiles low/med/high (20/50/80% of link cap); all parameters flags; `simulated: true` in docstring.
**6.5 Verification (exit criteria, all green twice consecutively):** (1) fresh-clone `make lab-up` healthy; (2) all BGP sessions Established (`make lab-check` via gNMI Get); (3) host1<->host4 ping <5ms 0 loss; (4) ECMP proof: 20 parallel flows host1->host3, both leaf1 uplinks carry ≥25/75 split; (5) `make lab-down` leaves no orphans.
**Contingency:** BGP flaps -> pin image version; shrink to 2 leaves to isolate; check VM resources. ECMP not splitting -> multipath config + vary src ports in generator.

---

## 7. PHASE 2 — TELEMETRY

**7.1 gnmic subscriptions** (verify exact YANG paths on your SR Linux release; record finals in toolchain.md):
- interface-counters: `/interface[name=ethernet-1/*]/statistics` — SAMPLE 2s (1s hot paths if CPU allows)
- interface-oper: `/interface[name=ethernet-1/*]/oper-state` — ON_CHANGE
- bgp-sessions: `/network-instance[name=default]/protocols/bgp/neighbor[peer-address=*]/session-state` — ON_CHANGE
- queue-stats: SR Linux QoS output-queue statistics — SAMPLE 2s (**if unavailable on ARM image: proxy congestion via out-drops + utilization; ADR it**)
- Output: prometheus scrape :9804, metric-prefix `fc`, export-timestamps true.
**7.2** Prometheus scrape 2s, retention 15d; Grafana provisioned dashboards: **fabric-overview**, **incident-drilldown**.
**7.3** Syslog: all nodes -> asyncio UDP collector -> Postgres `logs`.
**7.4 Verification — THE FEASIBILITY GATE:** (1) `make telemetry-up` -> live counters from all 6 switches in Grafana within 60s. (2) Manually admin-disable one leaf-spine interface via gNMI Set: oper-state flip <5s, BGP drop, dead-link counters flatline, ECMP shift to sibling — all visible. (3) Syslog rows for the same event in Postgres.
**Contingency:** counters missing -> wrong YANG path (browse SR Linux tree); empty Prometheus -> diff configs against the official gnmic containerlab example.

---

## 8. PHASE 3 — CHAOS ENGINE + CORPUS

**8.1 Fault classes** (one module each; every injection emits §8.3 label):
| Class | Mechanism | Active window |
|---|---|---|
| link_down | gNMI Set admin-disable one side | 60–90s |
| link_flap | disable/enable xN, period 5–10s | 60–90s |
| congestion | `tc tbf` rate-limit one leaf-spine veth (host side in VM) to 30–50% + raise traffic profile | 150–180s |
| gray_failure | `tc netem loss 1–3% delay 2–8ms` on one veth | 150–180s |
Impairments act on host-side veth (clab link-name mapping documented). These classes are `simulated: true` by definition.
**8.2 Settle detection:** after clearing, poll Prometheus every 5s; settled when all watched series within k*sigma of pre-incident baseline (60s window before inject) for 15 consecutive seconds; hard timeout 120s -> quarantine incident, continue.
**8.3 Ground-truth label (Pydantic; file per incident + Postgres row):**
```json
{"schema_version":1,"incident_id":"uuid","scenario_id":"cong-l2s1-med-s42",
 "fault_class":"congestion","target":{"kind":"link",
  "a":{"node":"leaf2","if":"ethernet-1/1"},"b":{"node":"spine1","if":"ethernet-1/1"}},
 "params":{"rate_limit_pct":40},"traffic_profile":"med","seed":42,
 "topology_id":"clos-2s4l-v1","t_baseline_start":"...","t_inject":"...",
 "t_clear":"...","t_settled":"...","simulated":true}
```
**8.4 Corpus runner:** scenarios.yaml matrix = {4 classes} x {every eligible link} x {low,med,high} x {severity variants} x {seeds} + healthy-only blocks (≥20% of runtime). Target ≥300 fault incidents across two topology sizes (2s4l + 2s6l variant). Deterministic from master seed; checkpointed/resumable; per incident: baseline -> inject -> hold -> clear -> settle -> label -> next. Parallel: `make corpus SHARDS=3` (namespaced labs, RAM-gated: add shards while free RAM >4 GB).
**Smoke protocol (mandatory):** `make corpus-smoke` = 10 incidents -> inspection notebook: labels time-aligned? gray failure visibly != noise? settles clean? Findings -> ADR. Only then full campaign.
**Exit:** ≥300 labeled incidents + healthy blocks; quarantine <5%; smoke ADR committed.
**Contingency (project risk #1):** gray failure invisible -> raise loss % -> lengthen window -> 1s sampling — in that order; still invisible -> honestly redefine the class (e.g. 5% loss) and document.

---

## 9. PHASE 4 — DATA LAYER

**Postgres schema (`db/schema.sql`):**
```sql
users(id uuid pk, username text unique, pw_hash text,
      role text check (role in ('viewer','approver')), created_at timestamptz)
audit_log(id uuid pk, actor text, action text, entity_type text, entity_id uuid,
      before jsonb, after jsonb, created_at timestamptz)
topologies(id text pk, name text, spec_hash text, nodes jsonb, links jsonb, created_at timestamptz)
scenarios(id text pk, fault_class text, target jsonb, params jsonb,
      traffic_profile text, topology_id text references topologies, created_at timestamptz)
incidents(id uuid pk, scenario_id text references scenarios, topology_id text references topologies,
      seed int, t_baseline_start timestamptz, t_inject timestamptz, t_clear timestamptz,
      t_settled timestamptz, corpus_split text check (corpus_split in ('train','val','test','quarantine')),
      simulated bool not null default true, created_at timestamptz)
dataset_windows(id uuid pk, incident_id uuid references incidents null,
      kind text check (kind in ('fault','healthy')), t_start timestamptz, t_end timestamptz,
      parquet_path text, created_at timestamptz)
logs(id bigserial pk, node text, severity text, ts timestamptz, body text,
      incident_id uuid references incidents null)
runs(id uuid pk, kind text check (kind in ('rules','ts','gnn','agent_single','agent_phased','e2e')),
      config jsonb, git_sha text, prompt_hashes jsonb, model_ids jsonb, metrics jsonb, created_at timestamptz)
detections(id uuid pk, run_id uuid references runs, incident_id uuid references incidents,
      detector text, t_detected timestamptz, latency_s numeric, ranked_suspects jsonb, created_at timestamptz)
diagnoses(id uuid pk, run_id uuid references runs, incident_id uuid references incidents,
      hypotheses jsonb, committed jsonb, report_md text,
      evidence_coverage numeric, evidence_correct numeric, created_at timestamptz)
evidence(id uuid pk, diagnosis_id uuid references diagnoses,
      kind text check (kind in ('metric','log','gnn','topology','doc','memory')),
      ref jsonb, snapshot jsonb, created_at timestamptz)
remediations(id uuid pk, diagnosis_id uuid references diagnoses,
      action text check (action in ('enable_link','drain_link','clear_impairment','revert_config','no_action')),
      params jsonb, status text check (status in ('draft','approved','rejected','executed','rolled_back','failed')),
      t_executed timestamptz, t_recovered timestamptz, created_at timestamptz)
approvals(id uuid pk, remediation_id uuid references remediations, user_id uuid references users,
      decision text check (decision in ('approve','edit','reject')),
      edited_params jsonb, comment text, created_at timestamptz)
runbook_chunks(id uuid pk, doc text, section text, body text, embedding vector(384), created_at timestamptz)
prompts(id uuid pk, name text, version int, hash text unique, template text, created_at timestamptz)
```
Indexes: incidents(t_inject); detections(incident_id); evidence(diagnosis_id); logs(ts); logs(incident_id); ivfflat on runbook_chunks.embedding.
Relationships: scenario 1->N incidents; incident 1->N detections/diagnoses (one per run); diagnosis 1->N evidence, 1->1 active remediation; remediation 1->N approvals. Raw counters NEVER enter Postgres — Prometheus + parquet only; Postgres stores references and outcomes.

**9.1 ML dataset formats:** Windows = parquet long format (`ts, node, interface, metric, value`), one file per dataset_window. Graph tensors = one .pt per incident window: nodes = interfaces (~24 in 2s4l); edges = physical links + intra-device edges; X in [N,F], F ~40 = {mean,std,last,max,slope} x {in/out octet-rate, in/out pps, errors, drops, queue-proxy} + TS anomaly score + role one-hot(3); edge_index [2,E]; y in [N] = 1 on both endpoints of faulty link else 0; metadata {incident_id, split, fault_class}.

**9.2 Split policy (reviewed twice, unit-tested):** PRIMARY leave-locations-out (hold out 25% of physical links -> ALL their incidents = test; disjoint 15% = val). SECONDARY leave-topology-out (all 2s6l incidents = test only). Healthy windows split by time blocks, no overlap. FORBIDDEN: random split over incidents/windows. A unit test asserts no fault location appears in two splits.

**Exit:** schema migrated; builder converts smoke corpus -> parquet + tensors; splits test green; one notebook renders a fault window and the signature is VISIBLE.

---

## 10. PHASE 5 — SENSORS

**10.1 Rules baseline (built FIRST, tuned honestly on TRAIN only):** per-interface static thresholds (drops/s, error rate, sustained utilization, oper-down) + 30s-window alarm correlation; suspect ranking by counts per link. Ablation row 1; the bar ML must clear.
**10.2 TS detector:** v1 EWMA/seasonal z-score (also feeds rules). v2 trained: LSTM-autoencoder (2x64) OR PatchTST-small, per-interface multichannel windows (60 samples @2s), trained on TRAIN healthy only; anomaly = reconstruction-error percentile vs healthy VAL; threshold picked on VAL for target FP. Ablation row: Chronos zero-shot, same protocol. Metrics: detection latency, FP/hour on healthy TEST, AUC.
**10.3 GNN localizer (centerpiece):** GraphSAGE 2–3 layers hidden 64 dropout 0.2 (PyG); GAT as variant. Per-node sigmoid head. Loss: focal (or BCE pos_weight ~ N_neg/N_pos — imbalance is ~2 positive vs ~22 negative nodes). Link score = mean of endpoint scores; rank links; top-1/top-3 vs label. Within-ablation baseline: same features through MLP (no message passing) — isolates topology's value. Training: Adam 1e-3, early stop on VAL top-1, minutes on MPS; every run logged to `runs` with config + git_sha. Done requires: per-class confusion, per-location error analysis, shuffled-ID test (model must not key on node identity).
**10.4 Log parser:** Drain3 + regex -> structured events; precision spot-check ≥0.9 on 100 sampled lines; DistilBERT ONLY if this fails (ADR).
**Exit:** committed metrics table: rules vs TS(v2) vs Chronos (detection); MLP vs GNN (localization); all on leakage-safe TEST.
**Contingency:** GNN ≤ rules everywhere -> (1) plot feature separability, (2) audit labels/splits, (3) model tweaks; if it honestly loses — publish the finding; integrity survives, story changes.

---

## 11. PHASE 6 — DIAGNOSTIC WORKFLOW (LangGraph)

**11.1 State (Pydantic):** IncidentState { incident_id, budget{max_tool_calls:20, max_tokens, max_seconds}, evidence: list[EvidenceRef], hypotheses: list[Hypothesis], committed: Diagnosis|None, remediation: RemediationDraft|None, stage_log }. Hypothesis { target: LinkRef|NodeRef, fault_class, confidence, evidence_ids, rationale }.
**11.2 Stages (each has a contract; may not pass without meeting it):**
1. collect — pull GNN ranking, TS anomalies, oper/BGP changes, top-K log events; write evidence rows. Contract: ≥3 items or explicit "insufficient telemetry".
2. hypothesize — LLM emits ≤3 structured Hypotheses; each must reference ≥1 evidence_id (schema-enforced).
3. test — per hypothesis, targeted follow-up queries (e.g., sibling-link utilization check for congestion) -> confirming/refuting evidence; drop refuted.
4. commit — select winner; run verifier; fail -> back to collect (max 2 loops) -> else emit "undiagnosed" honestly.
5. remediate — map fault_class -> whitelisted action (link_down->enable_link; congestion/gray->drain_link|clear_impairment; unknown->no_action) + params + blast-radius note -> status draft -> **STOP (interrupt). Nothing executes here. Ever.**
Single-agent variant: `graph.py --mode=single` = one ReAct loop, same tools, same budget — kept green always (ablation row).
**11.3 Tools (typed, budget-metered, OTel-spanned):** query_prometheus(promql,start,end); get_gnn_ranking(incident_id); get_ts_anomalies(incident_id); get_logs(node?,window,pattern?); get_topology(); search_runbooks(query,k=4); similar_incidents(incident_id,k=3).
**11.4 Verifier (deterministic; runs on every commit):** every claimed evidence_id exists; snapshot timestamps within incident window; referenced node/interface matches hypothesis target or topology neighbors; numeric claims in rationale within 10% of snapshot values (regex-extracted). Outputs evidence_coverage + evidence_correct -> stored on diagnoses. LLM-as-judge is EVAL-ONLY, never in the loop.
**11.5 Prompts:** `workflow/prompts/name.vN.md`; registry computes sha256 -> prompts table; every run records prompt_hashes. Editing = new version file, never in place.
**Exit:** 10 held-out incidents -> 10 reports; every claim manually checkable against Grafana; verifier metrics computed.

---

## 12. PHASE 7 — HITL + REMEDIATION

- API (/api/v1): GET /incidents; GET /incidents/{id} (case file); POST /remediations/{id}/approve|reject (approver role); POST /remediations/{id}/edit; GET /audit.
- UI: Jinja2+HTMX: incident list -> case file -> approve/edit/reject. Deliberately plain.
- Auth: JWT + bcrypt; seed users viewer/approver; approvals bound to user_id; every state change -> audit_log.
- Executor: whitelist-only actions; each stores its inverse for one-click rollback; after execute, watch settle -> t_recovered or status failed.
- Recovery metric: time_to_recovery = t_recovered − approval time.
**Exit:** full loop demo per fault class: inject -> detect -> diagnose -> approve in UI -> execute -> Grafana recovers -> audit complete. Screen-record it — demo video spine.

---

## 13. PHASE 8 — EVALUATION (the product)

**13.1 Formulas (evals/metrics.py, unit-tested):** detection_latency = t_detected − t_inject; FP/hour on healthy blocks; top-k localization = true link in top-k; evidence_coverage = cited/claims; evidence_correct = verifier-passed/cited; diagnosis_accuracy = committed(target AND class)==label; correct_action_rate; unsafe_remediation_rate = drafted actions touching non-faulty targets / drafts; recovery success + median time_to_recovery; cost/incident from Langfuse.
**13.2 Four studies (publish whatever they say):** (1) Detection: rules vs TS-trained vs Chronos-zero-shot. (2) Localization: MLP vs GNN. (3) Reasoning: agent_single vs agent_phased — same model/tools/evidence/budget. (4) End-to-end: rules-only / single / phased / sensors+phased x {accuracy, time, false-claims, cost}; two LLM tiers as a column.
**13.3 NIKA adapter (post-core, never a dependency):** run agent on NIKA MCP; report root-cause F1 vs its ReAct baseline; contribute fabric scenario pack as PR/fork.
**Exit:** evals/reports/*.md committed; README results generated from them; every number reproducible via `make bench && make ablate`.

---

## 14. PACKAGING, CI, MAKEFILE

- Targets: doctor, lab-up, lab-down, lab-check, lab-traffic-smoke, telemetry-up, corpus-smoke, corpus [SHARDS=n], dataset, train-ts, train-gnn, ablate-gnn, workflow-run INC=<id>, hitl-up, bench, ablate, nika, demo, test, lint, fmt.
- `make demo`: lab-up -> telemetry-up -> inject one gray failure -> sensors fire -> workflow report -> open HITL URL -> on approve, execute -> print before/after timeline. Fresh-clone tested.
- CI: ruff -> mypy -> pytest unit -> integration smoke: FRR mini-lab, one link_down end-to-end with rules detector (deterministic, no LLM).
- compose profiles: core always; obs (Langfuse) only during workflow-dev + eval sweeps.
- Deployment posture: docker compose IS the deployment; K8s/Helm on kind = post-core; event bus = post-core with measured justification.

---

## 15. RISK REGISTER (pre-decided responses)

| # | Risk | Response |
|---|---|---|
| 1 | Gray-failure signatures unlearnable | escalate severity -> 1s sampling -> longer window -> honest class redefinition (ADR) |
| 2 | SR Linux ARM instability / missing queue paths | pin version; proxy congestion via drops+util; FRR fallback for CI only |
| 3 | GNN ≤ rules everywhere | separability check -> split/label audit -> publish the finding; reframe around the honest ablation |
| 4 | Local LLM too weak for structured stages | schema-retry x2 -> bigger tier -> API tier (cost logged); NEVER loosen the verifier |
| 5 | Scope creep (the real killer) | Doctrine #2; anything not in this document -> docs/backlog.md, not the repo |

---

## 16. MASTER DEFINITION-OF-DONE (all boxes or it isn't finished)

- [ ] Fresh clone -> `make demo` works on a clean machine
- [ ] ≥300-incident corpus, two topologies, healthy blocks; leakage-safe splits enforced by tests
- [ ] Results tables: detection, localization, reasoning, end-to-end — committed and README-linked
- [ ] Evidence correctness + unsafe-remediation + recovery metrics reported
- [ ] Verifier + tests + CI green; JWT roles live; audit trail complete
- [ ] Fidelity statement + related-work table + prompt-coverage appendix in README
- [ ] Langfuse traces demonstrably capturing cost/latency per incident
- [ ] 5-minute demo video; technical article published; resume bullets filled with real numbers
- [ ] You can whiteboard: the topology, the label schema, the split design, the GNN forward pass, the verifier logic, and every ablation result — without notes

*End of Bible. Anything not in this document is, by definition, out of scope until the master checklist is green.*
