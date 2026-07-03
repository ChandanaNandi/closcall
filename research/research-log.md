# ClosCall — Research Log
### Every investigation, verdict, and source from the planning phase. Append-only from here on.

## R1. Prior-art landscape (two independent sweeps, merged)
- **NIKA** — public benchmark for LLM network-troubleshooting agents. arXiv 2512.16381; github.com/sands-lab/nika. Repo verified Jul 2026: 54 issues, 640 incidents, 5 scenarios incl. DC-CLOS, microbursts/incast, P4+INT; MCP interface; ReAct agent only. Headline finding: frontier LLM agents still fail at fault localization -> the gap our GNN attacks. Role: external eval harness (post-core).
- **SADE** — arXiv 2605.04530. Structured (phase-gated) diagnostic policy beats free-form ReAct by ~37 F1 points on NIKA. Role: methodological basis for our workflow design.
- **RCACopilot (Microsoft), Flow-of-Action** — LLM RCA for cloud incidents; not fabric-specific.
- **Minder / MegaScale / C4D / FLARE (ByteDance/Alibaba)** — production GPU-cluster fault diagnosis; closed, non-agentic. Role: failure taxonomy source for our chaos scenarios.
- **Meta Llama 3 report** — 419 unexpected interruptions in 54 days on ~16k GPUs. Role: the problem statement.
- **Juniper Marvis / Selector AI** — commercial AIOps; Marvis "driver-assist" mode = the HITL pattern we mirror. Marvis moving toward AI DC (Apstra).
- **NetClaw** (github.com/automateyournetwork/netclaw) — open chat copilot, 100+ skills, gNMI/containerlab MCPs, ITSM gating. No trained ML, no autonomous pipeline, no evals. Closest open neighbor; our differentiation foil.
- **GNN-RCA literature** — REASON, KGroot, cascaded GNNs: state of the art for topology fault localization, but aimed at microservices; fabric application is open.
- **White-space verdict (triple-verified):** no public system combines (1) fabric-failure realism + (2) trained TS+GNN sensors + (3) autonomous evidence-grounded HITL loop + (4) ground-truth evaluation. Each neighbor has ≤2 of 4.

## R2. Feasibility on Apple Silicon (verified against primary docs)
- containerlab officially supports ARM Macs (containerlab.dev/macos); ARM64-native NOS images preferred; OrbStack/Docker Desktop runtime.
- SR Linux: free, ARM64-native (ghcr.io/nokia/srlinux), native gNMI Get/Set/Subscribe -> chosen as PRIMARY NOS. SONiC: no official ARM64 image -> post-core extension (x86 cloud VM or M3+/macOS15 nested-virt experiment). FRR: CI/fallback profile.
- **The week-2 path exists as an official upstream example:** gnmic repo ships a containerlab deployment with SR Linux + gnmic + Prometheus + Grafana (`gnmic/examples/deployments/1.single-instance/4.prometheus-output/containerlab`). Clone and adapt.
- Langfuse: MIT, self-hosted via docker compose, all core features free/unlimited (github.com/langfuse/langfuse; langfuse.com/self-hosting). Footprint ~6 containers / ~1.5 GB idle.

## R3. Corpus-generation alternatives (4 independent sweeps + 1 primary-source arbitration)
- **Adopted:** per-class fault windows (blunt 60–90s; congestion/gray 150–180s — floor is ML signal, not convergence), event-driven settle detection, 1–2s gNMI sampling (sample_interval is nanosecond-granular per Nokia docs), 3–4 parallel lab shards (~2 GB RAM/node planning figure). Result: ~300 incidents ~= one evening/overnight (down from ~25h).
- **Rejected — time dilation (VT-Mininet, TimeKeeper, DieCast, SliceTime):** research-grade kernel mods, Mininet-era, and TDF primarily trades MORE wall-clock for fidelity/scale, not less. Cite in article.
- **Rejected — generative synthetic telemetry (GAN/diffusion):** circular (detector learns the generator); scope creep.
- **Rejected — REAL (NSDI '26, verified by reading the paper):** control-plane emulator for config verification; data plane deleted (Unix sockets, no traffic/queues/drops/counters) -> congestion & gray failures don't exist in it; the "telemetry export" claim in one AI research summary was NOT in the paper (hallucination-by-extension, caught by fetching the primary source). Excellent related-work citation.
- **Kept as extension — discrete-event sim (ns-3/OMNeT++/htsim):** faster than real time but no real NOS/gNMI; role = sim-to-real pretraining experiment. htsim is UEC-adjacent (Ultra Ethernet vocabulary bonus).
- **Public datasets:** no labeled fabric-fault + multivariate device-telemetry corpus exists anywhere (re-verified). LogHub = logs only; TeleLogs = synthetic 5G logs; CICIDS = traffic.
- **Method lesson (keep):** parallel AI research is valuable for discovery, unreliable for verification — every consequential claim gets its primary source fetched before entering the plan.

## R4. Key design corrections adopted from external review
1. SR Linux locked as primary NOS (gNMI surface).
2. Telemetry simplified: gNMI -> gnmic -> Prometheus -> Grafana; Postgres for state; NO event bus in core.
3. Hundreds of incidents + leakage-safe splits (leave-locations-out, leave-topology-out; random splits forbidden).
4. Ablations made causal: detection / localization / reasoning controlled separately, then end-to-end.
5. Phase-gated workflow (SADE), not "N agents"; single-agent config always runnable (ablation row).
6. NIKA characterization corrected against live repo; positioned post-core.
7. Metrics upgraded: evidence CORRECTNESS (not just citation coverage), unsafe-remediation rate, correct-action rate, recovery success/time. "Human acceptance rate" dropped.
8. Hardware claim softened: telemetry-adapter boundary exists, but hardware deployment needs feature remapping, recalibration, independent validation.

## R5. Positioning decisions
- Never marketed as a multi-agent project: "an evaluated autonomous incident-command system for AI/GPU network fabrics." Orchestration = tested hypothesis.
- Role fit (honest): ~9/10 for AI-infra / network operations / observability / ML-systems roles (e.g., NVIDIA Santa Clara AI Networking new-grad: GNNs, time-series, HPC networking, NCCL/RoCE/RDMA); ~5/10 for ASIC/RTL/kernel-datapath roles.
- Compute reality: training = minutes on M4 Pro (models 50K–1M params); corpus = simulation wall-clock, GPU-irrelevant; total mandatory spend $0.
- Name: **ClosCall** (Clos topology + "close call"); tagline "evidence-grounded incident command for AI datacenter fabrics." Check GitHub/PyPI collision at repo creation. Renamed from working title "Fabric Copilot" (collides with Microsoft's Copilot in Fabric).

## R6. Open items to verify at build time (flagged, not guessed)
- Exact SR Linux YANG path for output-queue statistics on the ARM image (fallback: drops+utilization proxy, ADR'd).
- SR Linux BFD/BGP timer floors for our release (one review conflated SR OS docs with SR Linux).
- Per-node RAM on our exact image version (shard count depends on it).
- ClosCall name collision check (GitHub/PyPI).

## R7. Senior inspection and canonical-plan correction

- The first Build Bible was judged directionally strong but not safe to implement unchanged.
- The repository is intentionally a planning repository; absence of implementation is not itself a
  defect.
- Canonical planning moved to `03-Canonical-Execution-Bible.md`,
  `04-Data-API-and-State-Contracts.md`, and `05-Acceptance-Matrix.md`.
- Mandatory corrections: causal as-of feature windows; isolated evaluator-only ground truth;
  typed semantic claims; immutable remediation versions; approval bound to digest/topology/config;
  isolated fail-closed executor; explicit outcome-unknown reconciliation; tamper-evident audit;
  machine-readable network source of truth; exact routing policy; stronger ECMP acceptance;
  telemetry quality/time semantics; and measured rather than assumed lab parallelism.
- Fault names were corrected to match what container/qdisc mechanisms actually emulate. Harness
  cleanup is not remediation.
- NIKA claims now distinguish the published paper benchmark from the evolving repository. The
  external run must pin a commit and is reported as agent-adapter evaluation, not validation of
  internal ClosCall sensors.
- “Bulletproof” is defined operationally: uncertainties must have feasibility gates, fallbacks,
  retained evidence, and stop conditions. It is not a promise that implementation will encounter no
  new facts.

## R8. Gate 0 acceptance record (2026-07-03)

- The canonical document set is ACCEPTED for execution as frozen in git commit `5a1758a`
  (`chore: planning canon v1 (frozen)`): `README.md`, `planning/01`–`05`,
  `docs/decisions/ADR-001-scope-waivers.md`, `docs/backlog.md`, `research/research-log.md`,
  `research/source-register.md`.
- Precedence on conflict, per README: 05 > 04 > 03 > 02 > 01; ADRs record corrections; planning is
  CLOSED and this log is append-only.
- Amendment A1 status accepted as propagated: waivers marked in document 05, justified by ADR-001,
  deferred items in `docs/backlog.md`. Deferred means deferred; backlog items are not implemented.
- Source-pinning policy A1 accepted: fast-moving repositories (NIKA first) cited by exact commit
  SHA + access date only; reported statistics are statistics of that SHA.
- Execution model accepted: ordered gates of document 03, worked strictly sequentially; gate
  sections beyond the current gate remain unread until reached.
- **Open item (for Gate 1/3, not Gate 0):** verify whether OrbStack's shared-VM model satisfies the
  Bible §3.3/§4 requirement that containerlab privileged operations run only inside a dedicated,
  isolated ARM64 Linux lab VM.

## R9 (errata)

R1's repo characterization (54/640/5, ReAct-only) reflected a stale/cached fetch of the paper-era
README. Superseded by the source-register pin at e6649f45 (56 issues / 685 incidents /
14 scenarios, multiple agent runners), 2026-07-03. The A1 SHA-pinning policy exists because of
exactly this incident.

## R10. Corrected environment facts and open items (Gate 1, 2026-07-03)

- **Environment correction (pilot ruling):** the "OrbStack" in the Gate 0 brief was an unverified
  planning-phase assumption. Observed: OrbStack not installed; Docker Desktop installed with
  docker CLI 28.3.3 (`desktop-linux` context). Ruling: Docker Desktop is the runtime (canon R2
  blesses both; "simplify, never add" decides). OrbStack will not be installed. The R8 open item
  retargets to Docker Desktop under the same intent standard: own kernel, own root boundary, host
  filesystem not implicitly writable by lab containers — with specific attention to default
  file-sharing mounts.
- **Host facts (observed 2026-07-03):** Apple Silicon, macOS 26.5.2 (arm64), 24 GB RAM, 12 CPU
  cores, git 2.50.1 (Apple Git-155), Python 3.12.12, uv 0.7.21, gh 2.92.0.
- **Open item — disk pressure (pilot ruling attached):** 40 GiB free at 91% used. Before any
  corpus-generation gate begins, free space must be **>= 60 GiB** or the corpus is blocked;
  SR Linux images, Prometheus retention, parquet windows, and Langfuse volumes all land on this
  disk. Pilot performs the cleanup; the gate check verifies it.
- Planning-era expectation for the Gate 1 benchmark on 24 GB (~12 GB per 2s4l lab): shard count 1.
  The measured number governs either way.

## R11. ADR-002 mitigation applied and verified (Gate 1, 2026-07-03)

- Docker Desktop file sharing set to **repo-only** (`/Users/nandichandana/Downloads/ClosCall`);
  broad host trees (`/Users`, `/Volumes`, `/private`, `/tmp`, `/var/folders`) removed. Verified in
  VM init namespace: sibling home folders (`Documents`, `Desktop`) are `No such file or directory`;
  the bare `/host_mnt` is an empty in-VM tmpfs (not host root). `make doctor` file-sharing probe
  PASS with only the repo reachable.
- **Finding — transient cross-project reachability.** Host paths reachable inside the DD VM =
  declared file shares (ClosCall) + bind mounts of *currently-running* containers. While the
  pilot's unrelated lab containers run (e.g. `neuronoc` bind-mounting `Downloads/NeuroNOC`), that
  project dir becomes reachable by any privileged container in the VM. It is NOT a ClosCall
  file-sharing misconfiguration; it disappears when those containers stop. The doctor probe
  fails closed on any non-repo host path by design, so ClosCall lab operations require a clean
  Docker (no other bind-mounted lab containers) — the probe enforces this at gate-check time.

## R12. SR Linux version binding for R6.1/R6.2 (Gate 1, 2026-07-03)

(Appended rather than edited into R6 to preserve append-only discipline; binds the same items.)

- **Verified-against version = SR Linux 25.3.3 @ `sha256:f711ddadbca870996793ac9bb3fccb950aa2c6a906da64a304c5274a2c2dceee` (arm64), forever.**
- This is the single version that the R6.1 (output-queue YANG path) and R6.2 (BFD/BGP timer floor)
  open items are verified against when those verifications occur in later gates. Any change of
  NOS version re-opens R6.1/R6.2 against the new version and is an ADR + new benchmark, never a
  silent substitution.
- Digest is the forever-referent; the `25.3.3` tag is a convenience label (see docs/toolchain.md).
  Fallback 24.10.4 @ `sha256:4c7af354…` would likewise re-bind R6.1/R6.2 if ever promoted.
- R6.4 (ClosCall name collision) resolved 2026-07-03: PyPI 404 (free), GitHub 0 repos named
  closcall, general web search found only unrelated products (a cold-call SaaS, CLOS logistics
  software, Common Lisp Object System) — no software-project collision. Private repo created at
  github.com/ChandanaNandi/closcall.
