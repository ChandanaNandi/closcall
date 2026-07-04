# Gate 10 — Diagnostic Workflow Status Note

Status: **complete and signed off.** All §12 work items built and adversarially tested; all three
exit criteria enforced in code. Unlike Gate 9 (partial, capped by the traffic-free corpus), Gate 10
is a clean pass.

Blocker check: none. Two tool-capable models were already local (Ollama 0.30.7) — no download.

## What was built

Deterministic core first (LLM-independent), then the LLM plugged in as a propose-only hypothesizer.

| item | §ref | module | tests |
|---|---|---|---|
| Typed claims + deterministic verifier | §12.2 | `evidence/claims.py` | 9 |
| Evidence tools (9) with enforced envelope | §12.3 | `evidence/tools.py` | 8 |
| Workflow state machine + abstention | §12.1 | `workflow/diagnose.py` | 9 |
| Report generator (narrative after verification) | §12.2 | `workflow/report.py` | 3 |
| LLM hypothesizer (propose-only) | §4.1/§12.1 | `workflow/llm.py` | 6 |
| Local LLM qualification | §4.1 | `scripts/qualify_llm.py` (`make qualify-llm`) | — |

Design invariant: the LLM only *proposes* hypotheses; every claim is checked by the deterministic
verifier before any commit. A fooled or adversarial model cannot fabricate a committed diagnosis —
the worst case is claims that fail verification, yielding honest `undiagnosed`.

## Exit criteria — all met

1. **Unsupported/contradictory claims cannot be committed.** `verify(claim, snapshot) →
   supported/contradicted/insufficient` with no model in the loop; `committable()` gates on
   `supported` only. Adversarially strict: evidence must match subject + metric/event + unit + causal
   interval, else `insufficient`; cherry-picking defeated by `sustained` semantics. **Plus** a
   relevance gate: a class commits only if a supported claim ENTAILS it (see finding below).
2. **Ground truth remains inaccessible.** Every tool runs through one envelope (incident scope,
   as-of upper bound, result limit, call+row budget). `EvidenceSource` has no evaluation-schema
   method — a structural test guards against ground-truth/label/campaign/fault_injection accessors —
   and the Gate 7 DB-role isolation backs it. Retrieved logs/runbooks are `trusted=False` and never
   populate executor params; `get_metric_window` accepts only allow-listed template IDs.
3. **Failure yields honest `undiagnosed`, never fabricated certainty.** `commit_or_abstain` commits
   only a recognized, entailed, fully-supported diagnosis; otherwise `undiagnosed` with no plan. The
   report generator renders only verified facts (a test proves an injected untrusted log never
   appears in the narrative). Budget exhaustion abstains rather than fabricating.

## Integrity finding — diagnosis-relevance hole (R30)

The real `qwen2.5:7b-instruct` run exposed a genuine hole: the workflow committed a diagnosis
whenever a hypothesis's claims were *supported*, but never checked that the claims were *relevant*
to the diagnosis class. 7b emitted a made-up class ("Operational State") with a claim that was
genuinely supported (the link IS up) → a false diagnosis committed. "Unsupported claims can't
commit" is necessary but not sufficient — a supported-but-irrelevant claim is another fabrication
path.

Fix: `DIAGNOSIS_DEFINITIONS` bind each recognized class to a required claim signature
(metric + operator + polarity); a hypothesis commits only if its class is recognized AND a supported
claim entails it. Unrecognized classes and supported-irrelevant claims now abstain. After the fix
both models resist the injection fixture. Caught by running the mandated adversarial LLM fixtures and
distrusting `injection_held=False`.

## §4.1 qualification result (`make qualify-llm`)

7 validation cases (2/category + 1 injection fixture); the verifier gates every claim, so accuracy
cannot be inflated by fabrication.

| model | accuracy | injection_held | schema_repairs | latency (med) |
|---|---|---|---|---|
| **qwen2.5:14b-instruct** (PRIMARY, `7cdf5a0187d5`) | 0.71 | true | 0 | ~2.7s |
| qwen2.5:7b-instruct (ablation, `845dbda0ea48`) | 0.71 | true | 0 | ~6.0s |

Digests pinned in `docs/toolchain.md`. The 14b model is the frozen primary; the 7b is the §4.1
second frozen tier for reasoning ablation.

## Honest loose end (does not affect the exit criteria)

The evidence tools are built and proven over the `EvidenceSource` interface with a fake source; a
**DB-backed adapter** wiring them to the live `core.*` tables is not implemented (the qualification
built snapshots from the corpus §9.1 windows directly). The integrity properties hold regardless of
the source; this thin adapter naturally belongs with Gate 11's full-pipeline integration.

## Provenance

- Commits: claims `62baf47`; tools `d4df0fc`; workflow `ce1655e`; llm `189f0c5`; qualification +
  relevance fix `17461ac`; toolchain/R30 `33b514e`; report generator `fb36e20`.
- Tests: 142 unit/property, all pure/offline (no live model needed — Ollama isolated behind `Chat`).
  `make lint` + `make typecheck` clean.
- Report artifacts: `evals/reports/gate10-llm.txt` (regenerate with `make qualify-llm`).
- Research: R30. Toolchain: qualified LLM digests pinned.
