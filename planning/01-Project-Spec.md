
# Fabric Copilot → ClosCall

> **Authority note:** This file remains the product and research brief. Implementation details,
> data contracts, execution order, and acceptance criteria are governed by
> `03-Canonical-Execution-Bible.md`, `04-Data-API-and-State-Contracts.md`, and
> `05-Acceptance-Matrix.md`.

**Autonomous incident command for AI training-cluster network fabrics — with a human on the trigger.**

> A reproducible leaf-spine fabric lab that deliberately breaks itself, ML sensors (time-series + GNN over topology) that localize the root cause, and an LLM agent loop that produces an evidence-cited incident report and a remediation plan a human must approve. Evaluated against injected ground-truth failures and a rules-based baseline, with scores on the public NIKA benchmark.

*(Project renamed to **ClosCall** at repo creation; this document predates the rename. Everything else here is final.)*

---

## 0. Scope Contract (read this before building anything)

The single biggest risk to this project is **overbuilding**. GNN + NLP + RAG + six agents + multiple NOSes reads as shallow buzzword integration; a smaller system that demonstrably works end-to-end is much stronger. Therefore:

**The core is exactly seven proofs, built in order. Nothing from the Extensions section may be started until all seven are demoed and measured.**

| # | Proof | Definition of done |
|---|---|---|
| 1 | Reproducible leaf-spine lab | `make lab-up` deploys a BGP/ECMP Clos fabric in containerlab from one topology file; `make lab-down` destroys it; documented in README; works from a fresh clone |
| 2 | Streaming telemetry + usable Grafana view | gNMI subscriptions streaming interface/queue counters into Prometheus; one Grafana dashboard where a human can visibly see a failure happen |
| 3 | Three convincing failures with ground truth | Chaos engine injects: (a) link failure/flap, (b) congestion hotspot via traffic steering (simulated-PFC/ECN class), (c) gray failure (packet loss/latency on one link, simulated degraded optic). Each emits a machine-readable ground-truth label (what, where, when) |
| 4 | Root-cause ranking with measured precision & detection time | Time-series anomaly detector + GNN localizer output a ranked suspect list per incident; evaluated **leakage-safe** on a held-out set from a corpus of **hundreds** of deterministic incidents (varied fault locations, traffic loads, severities, seeds, ≥2 topology sizes, plus healthy periods for false-positive measurement); test split by **unseen fault location/topology**, never by random telemetry window |
| 5 | Evidence-backed incident report | LLM agent investigates and emits a structured report: symptom timeline, ranked hypotheses, each claim linked to a specific counter/log/GNN output; ungrounded claims are rejected by a verification pass |
| 6 | Human-approved remediation + demonstrated recovery | Agent drafts remediation (e.g., drain link, revert config); human approves in a minimal UI/CLI; system executes; telemetry visibly recovers; full audit trail |
| 7 | Baseline comparison: does ML beat rules? | A deliberately good rules-based detector (static thresholds + simple correlation) run on the same incidents; published table comparing rules vs. ML on accuracy, detection time, false positives — **whatever the result** |

Proof 7 is the one that signals real engineering judgment: if the GNN doesn't beat well-tuned rules on simple failures, that's a *finding to publish*, not a failure to hide (expected outcome: rules win on blunt failures like link-down, ML wins on gray failures and congestion — showing *where* the crossover sits is the interesting result).

---

## 1. Positioning & Target Roles

**Positioning rule:** this is an *evaluated autonomous incident-command system for AI/GPU network fabrics* — never marketed as a multi-agent project. Multi-agent orchestration is an implementation detail whose value is experimentally tested in the architecture ablation (§7.3), not assumed. In 2026, "I built a LangGraph multi-agent system" is table stakes; "I measured whether orchestration beats a single agent on this problem" is differentiation. Every README line, resume bullet, and interview answer leads with the domain system and its measured results; agents appear only when explaining *how*, with the ablation as justification.

The project demonstrates five capabilities, and every interview answer should land in one of them:
1. **Networking** — BGP/ECMP, Clos topology, congestion behavior, ECN/PFC/RoCE concepts (honestly scoped per §3)
2. **Software engineering** — streaming telemetry pipeline, APIs, state management, testing, one-command deployment
3. **Applied ML** — anomaly detection and topology-aware root-cause localization with measured accuracy
4. **Agent engineering** — structured tools, evidence provenance, bounded decisions, failure handling
5. **Evaluation** — reproducible scenarios, baselines, latency/accuracy/safety metrics, honest ablations

Built for the exact intersection currently hired for in AI-infrastructure networking (e.g., NVIDIA Santa Clara new-grad AI Networking: HPC networking, GNNs, time-series data, distributed AI workloads, Python/C++, NCCL, RoCE, RDMA; plus ML Systems—Networking, AI Factory Observability, and Agentic Networks roles; same vocabulary applies at Upscale AI, Arista, Nexthop, Juniper, and hyperscaler infra teams).

Every keyword earns its presence honestly:
- **GNN, time-series, anomaly detection** — trained models with measured results (Proof 4)
- **Clos, BGP, ECMP, gNMI, streaming telemetry** — a real emulated fabric (Proofs 1–2)
- **NCCL/RoCE/RDMA/PFC/ECN** — the *failure-mode vocabulary and traffic shapes* the scenarios model, explicitly labeled as simulated abstractions (see §3 Fidelity)
- **Agentic networking, incident command, HITL** — the investigation loop (Proofs 5–6)

---

## 2. Elevator Pitch (≤100 words)

Large training clusters fail constantly — Meta reported 419 unexpected interruptions in the 54-day Llama 3 run — and the hardest on-call question is "is it the model, the GPU, or the fabric?" This project is an open, reproducible answer: an emulated leaf-spine fabric that injects known failures, ML sensors (time-series anomaly + a GNN over the topology) that localize root cause, and an LLM agent that assembles an evidence-cited incident report and drafts remediation for mandatory human approval. Every claim is measured: localization accuracy, detection time, false positives — against ground truth and against a rules baseline.

---

## 3. Fidelity & Realism Statement (non-negotiable honesty)

**What this lab validates faithfully:** topology and routing behavior (BGP/ECMP on a real routing stack), control-plane failure modes, streaming telemetry pipelines (real gNMI/YANG), log semantics, automation and remediation workflows, and the *diagnostic reasoning layer* end to end.

**What it cannot reproduce:** ASIC-level PFC pause propagation, real RoCE congestion-control dynamics, DCQCN behavior, or physical optical degradation. These occur in hardware data planes; no container emulator reproduces them.

**Policy:** signals in the simulated-PFC/ECN and degraded-optic classes are *synthesized* (traffic-shaped congestion, injected loss/latency) and are labeled `simulated: true` in every event schema, dashboard, and report. The README carries this section verbatim. The claim is: "the diagnostic architecture is validated on an emulated fabric with synthesized failure signatures shaped by published failure taxonomies (Minder, MegaScale, Meta reliability reports); the system has a telemetry-adapter boundary, but deployment on hardware requires feature remapping, model recalibration, and independent validation — real hardware introduces different schemas, noise, timing, missing counters, actual PFC behavior, and distribution shift." Never present synthetic signals as hardware measurements — the target audience will know, and honesty here is itself a differentiator.

---

## 4. Related Work & Differentiation (the table the README leads with)

| System | Fabric-specific failures | Trained ML sensors (TS + GNN) | Autonomous agent loop + HITL | Ground-truth evaluation | Open |
|---|---|---|---|---|---|
| **NIKA** (arXiv 2512.16381 paper: 54 issues/640 incidents/5 scenarios; repository snapshot checked Jul 2026: 56 issues/685 incidents/14 scenarios and multiple agent runners) | partial (Clos + congestion classes; no ClosCall gNMI sensor pipeline) | ✗ (no ClosCall-trained TS/GNN sensors) | partial (diagnostic agents, no ClosCall HITL execution/recovery) | ✓ | ✓ |
| **SADE** (arXiv 2605.04530) | ✗ | ✗ | partial | ✓ (on NIKA) | ✓ |
| **Minder / MegaScale / FLARE** (ByteDance/Alibaba) | ✓ | partial (ML detection) | ✗ | internal | ✗ |
| **Juniper Marvis / Selector** | partial (moving to AI DC) | ✓ (proprietary) | ✓ (driver-assist = HITL) | proprietary | ✗ |
| **NetClaw** | ✗ | ✗ (no trained models) | partial (chat copilot, ITSM gate) | ✗ | ✓ |
| **ClosCall (this project)** | ✓ (simulated, labeled) | ✓ | ✓ | ✓ (+ NIKA scores) | ✓ |

Design decisions are anchored to sources of truth: problem scale (Meta Llama 3 report), simulation-first rationale (AI4NETS ground-truth scarcity literature), failure taxonomy (Minder/MegaScale published categories), GNN approach (topology-propagation RCA literature: REASON/KGroot lineage), agent methodology (SADE's finding that structured diagnostic policy beats free-form ReAct by 37 F1 points), HITL pattern (Marvis driver-assist mode), evaluation harness (NIKA + its published baseline).

---

## 5. System Architecture (lean core)

```
LAB (containerlab):
  SR Linux Clos (PRIMARY, ARM64-native, native gNMI Get/Set/Subscribe)
  FRR = CI/fallback profile; SONiC = post-core extension
  Traffic gen: collective-shaped flows (all-reduce bursts)
  Chaos engine: link flap | congestion hotspot | gray failure
    -> emits ground-truth labels (JSON) per injection
        |  gNMI subscribe + syslog
        v
TELEMETRY (deliberately minimal):
  SR Linux gNMI -> gnmic -> Prometheus -> Grafana
  Postgres for incidents/evidence/approvals/audit
  NO event bus in core (added only with measured justification)
        v
SENSORS (Python, PyTorch/MPS):
  1. Time-series anomaly scorer (per interface/queue)
  2. GNN localizer (topology graph + anomaly features -> ranked suspects)
  3. Rules baseline (thresholds + correlation) — Proof 7
  4. Log parser (Drain3/regex; NOT a big NLP subsystem)
        |  anomaly events -> incident opened (idempotent)
        v
DIAGNOSTIC WORKFLOW (LangGraph, phase-gated per SADE):
  collect evidence -> form hypotheses -> test hypotheses ->
  commit diagnosis -> draft remediation -> HUMAN APPROVAL
  Tools (shared): query telemetry, GNN ranking, logs, topology,
  runbook search (RAG as a TOOL), past incidents (memory as a TOOL)
  Every committed claim cites an evidence ID + passes verification
        v
HITL + REPORTING:
  Approval UI (case file -> approve/edit/reject); executor applies fix;
  recovery captured; Postgres audit; markdown incident report
```

**Note on the agent layer:** the phase-gated workflow is the *starting hypothesis*, not the identity of the project. The single-agent configuration (one LLM with the same tools and token budget) must remain runnable at all times, because it's a row in the reasoning ablation (§7.3). If the ablation shows the structured workflow doesn't pay for itself, simplify and publish the finding.

**Deliberate exclusions from core** (cut per scope contract): audio/vision modalities, agent headcount for its own sake, any event bus (Kafka/NATS/Redpanda — add only if measured throughput or decoupling requirements justify it), TimescaleDB (Prometheus + Postgres suffice), Kubernetes (docker compose; K8s manifests are an extension), multi-NOS parity, RAG beyond a simple doc-search tool, fine-tuning. LLM serving: Ollama locally or a budget API; vLLM documented as the production deployment mode only.

---

## 6. AI Components (each earns its place)

| Component | HF task lineage | Model class | Why it's necessary | Measured by |
|---|---|---|---|---|
| Telemetry anomaly scorer | Time Series Forecasting | Lightweight forecaster/AE (PatchTST-class or statistical hybrid) | Turns raw counters into per-entity anomaly scores; feeds the GNN | AUC vs. labels; detection latency |
| **GNN root-cause localizer** | Graph Machine Learning | GraphSAGE/GAT over Clos graph (nodes=interfaces, edges=links; features=anomaly scores, counters) | Anomalies propagate along topology; one bad link makes neighbors look sick. The GNN separates source from victims — directly attacking NIKA's published finding that LLM agents fail at localization | Top-1/top-3 localization accuracy vs. ground truth |
| Log parser | Text Classification (light) | Drain3 + regex; small classifier only if needed | Extracts device/interface/error-class from syslog for evidence | Extraction precision |
| Agent brain | Text Generation | Ollama-served open model (two tiers) or API | Investigation planning, hypothesis writing, report generation — SADE-style structured diagnostic policy, not free-form ReAct | Groundedness; end-to-end RCA accuracy; NIKA F1 |
| Runbook retrieval | Embeddings / sentence similarity | BGE-small (384-dim) | RAG *tool* over NOS docs + runbooks so remediation cites procedure | Retrieval hit rate in reports |

---

## 7. Evaluation Plan (the credibility engine)

1. **Internal benchmark (leakage-safe):** hundreds of deterministic incidents across fault locations, traffic loads/severities, seeds, ≥2 topology sizes, plus healthy periods for false-positive measurement. Split by **unseen fault location or topology** — never randomly by telemetry window (device memorization = leakage). Metrics:
   - Detection latency; top-1/top-3 localization accuracy; false positives per hour
   - **Evidence citation coverage** AND **evidence correctness** (does the cited observation actually support the claim — judged against the injected-fault answer key)
   - Diagnosis accuracy; **unsafe remediation rate**; **correct-action rate**; recovery success rate; time to recovery
   - (Dropped: "human acceptance rate" — meaningless when the builder is the only approving human)
2. **Rules baseline (Proof 7):** identical incident set through the rules detector; published comparison; honest narrative about where ML does and doesn't help.
3. **Controlled ablations (the headline experiments):** three controlled studies, then end-to-end:
   - **Detection:** rules vs. time-series model (vs. Chronos zero-shot) — same inputs
   - **Localization:** features-only MLP vs. features + GNN — same detector upstream
   - **Reasoning:** single agent vs. phase-gated workflow — same model, tools, evidence, token budget
   - **End-to-end:** rules / single / phased / sensors+phased × {RCA accuracy, diagnosis time, false-or-ungrounded claims, cost per incident}. Publish whatever the tables say.
4. **NIKA (external, post-core, never a dependency):** pin an exact NIKA commit and report it separately as an agent-adapter evaluation. Distinguish the published paper benchmark (54 issues/640 incidents/5 scenarios) from the evolving repository snapshot (56 issues/685 incidents/14 scenarios when checked Jul 2026). Compare against the agent runners and evaluator present at that pinned commit. NIKA does not validate ClosCall's internal TS/GNN sensors unless an equivalent telemetry adapter genuinely supplies their inputs.

---

## 8. Deliverables Checklist (hiring-value hard requirements)

- [ ] **One-command setup:** `make demo` = lab up → inject failure → watch diagnosis → approval prompt → recovery. Fresh-clone tested.
- [ ] **Clean architecture + tests:** typed Python, unit tests on sensors/schemas, one integration test that runs a full incident in CI (GitHub Actions, FRR profile).
- [ ] **Five-minute demo video:** Grafana goes red → agent investigates → evidence-cited report → human approves → graphs recover.
- [ ] **Before/after incident timeline** artifact (auto-generated per incident).
- [ ] **Evaluation tables** in README from the eval harness.
- [ ] **One technical article** — candidates: "When a GNN beats threshold rules on network RCA (and when it doesn't)" or "Emulating gray failures honestly: what containerlab can and cannot tell you."
- [ ] **Resume bullets with measured numbers.**
- [ ] Related-work table (§4) at the top of the README.
- [ ] Fidelity statement (§3) verbatim in the README.

---

## 9. Build Order (no calendar — locked sequence with a feasibility gate)

1. SR Linux Clos (2 spines × 4 leaves) in containerlab; BGP/ECMP verified; traffic gen v0; repo hygiene from the first commit (secrets, JSON logging, prompt registry with hashes).
2. gNMI → gnmic → Prometheus → Grafana (start from the official gnmic containerlab example); syslog; **inject one link failure and see it on the dashboard. ← FEASIBILITY GATE. Nothing new gets added until this passes.**
3. Rules-based diagnosis + automated recovery for link failure — full loop with rules first.
4. Rate-limited-uplink + impaired-link scenarios; corpus generator with pre-registered stratum counts, event-driven settle, causal 1–2s sampling, and parallelism enabled only from measured resource headroom. Rejected alternatives documented: time dilation, generative telemetry, control-plane-only emulation for data-plane faults, and discrete-event simulation as a core substitute.
5. Time-series detector + GNN localizer with leakage-safe evaluation; detection + localization ablations.
6. Phase-gated workflow with evidence citation + correctness verification; Langfuse + OTel observability; pgvector runbook tool.
7. HITL approval UI + executor + rollback + audit; JWT auth (viewer/approver); demonstrated recovery on all classes.
8. Reasoning ablation + end-to-end tables.
9. NIKA external evaluation (post-core); docs; incident timeline artifact.
10. Demo video, technical article, README polish, CI.
Post-core: K8s manifests on kind; event bus only with measured throughput justification; SONiC profile; sim-to-real pretraining experiment.

**Universal rule:** any checkpoint fails → simplify the architecture, never add tools. Slippage cuts NIKA, never Proofs 1–7.

---

## 9b. Verified Toolchain (confirmed against primary sources — no guessed dependencies)

| Component | Role | Verified |
|---|---|---|
| containerlab on ARM Mac | Lab orchestration | containerlab.dev/macos: official guidance; ARM64-native images; OrbStack/Docker Desktop runtime |
| Nokia SR Linux | Primary NOS | Free ghcr.io/nokia/srlinux, ARM64-native; native gNMI Get/Set/Subscribe |
| gNMIc | Telemetry collector | gnmic.openconfig.net: Prometheus outputs documented; **official containerlab example ships SR Linux + gnmic + Prometheus + Grafana** — build order step 2 starts by cloning it |
| Prometheus + Grafana | Metrics + dashboards | Multi-arch official images; wired in the example above |
| Postgres + pgvector | State + embeddings | Official multi-arch images; standard extension |
| PyTorch (MPS) + PyG | TS detector + GNN | Apple-Silicon MPS backend; tiny graphs — laptop-scale training |
| LangGraph + Ollama | Workflow + local LLM | Ollama ARM-native; API tier fallback |
| Langfuse (self-hosted) | LLM observability | MIT; all core features free/unlimited self-hosted; docker compose; ~6 containers/~1.5 GB — run during agent-dev, not benchmark sweeps |
| NIKA | External benchmark | Pin exact github.com/sands-lab/nika commit; Jul 2026 repository snapshot reports 56 issues, 685 incidents, 14 scenarios, MCP tools, and multiple agent runners |

Rule: any new dependency enters only with a pinned version + primary-doc link in `docs/toolchain.md`.

---

## 10. Resume Bullets (fill X from eval runs)

**Headline:** Built an evidence-grounded incident-command platform for AI datacenter fabrics, combining streaming gNMI telemetry, topology-aware ML, fault injection, and human-approved agentic remediation; evaluated root-cause accuracy across reproducible network failures and across four system architectures (rules, single-agent, multi-agent, ML+agents).

**Supporting:**
- Emulated BGP/ECMP Clos fabric (containerlab), streaming gNMI telemetry, injected ground-truth failures: **top-1 root-cause localization X%**, **median detection latency X s** across X incidents.
- Trained a **GNN over live network topology** for fault localization: **+X points over a tuned rules baseline**, **+X points over an LLM-only agent** (ablation) — directly addressing the localization gap documented in the public NIKA benchmark.
- LangGraph investigation loop with structured diagnostic policy, per-claim evidence citation (**X% verified-correct**), **mandatory human-in-the-loop approval**, demonstrated fault recovery, full audit trail.
- Evaluated on the **public NIKA benchmark** (root-cause F1 X vs. published ReAct baseline Y); contributed a fabric failure scenario pack.

---

## 11. Interview Prep Seeds

**They will ask:** Why multi-agent at all — isn't that overkill? (Point at the reasoning-ablation row; no other candidate answers this with data.) Why doesn't emulation invalidate the results? (§3: architecture vs. physics; adapter boundary.) Why a GNN instead of better thresholds? (Proof 7 crossover table.) How do you prevent hallucinated diagnoses? (Evidence-ID citation + deterministic verifier; measured correctness.) What breaks at 10,000 switches? (Partitioned telemetry, GNN inference sharding, incident dedup — have a sketch.) Why must the human stay in the loop? (Blast radius; Marvis ships the same pattern.)

**Best stories come from the seams:** gNMI paths per NOS, making injected failures produce *learnable* signatures, GNN label engineering, the ablation surprise (whatever it turns out to be).

---

## 12. Extensions (forbidden until Proofs 1–7 ship)

1. SONiC cloud profile
2. NIKA scenario-pack upstream contribution + short technical report (arXiv-able)
3. eBPF host telemetry exporter
4. NCCL-in-the-loop: real collective benchmarks on cheap cloud GPUs correlated with fabric events
5. Kubernetes/Helm on kind (+ event bus with measured justification)
6. Sim-to-real pretraining on discrete-event sim (htsim — UEC-adjacent)

---

*Sources of truth: Meta Llama 3 reliability report; ByteDance Minder & MegaScale; Alibaba FLARE/C4D; NIKA (arXiv 2512.16381, github.com/sands-lab/nika); SADE (arXiv 2605.04530); AI4NETS ground-truth-scarcity literature; GNN-RCA lineage (REASON, KGroot); Juniper Marvis driver-assist HITL pattern; containerlab macOS/ARM guidance; gnmic official containerlab example; Langfuse self-hosting docs; REAL (NSDI '26) — verified inapplicable, cited as related work.*
