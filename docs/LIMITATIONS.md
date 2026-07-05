# ClosCall — Limitations and Negative Findings (release, acceptance row J08)

This document is the mandatory J08 deliverable: *fidelity limitations and negative findings are
published*. It consolidates (a) the scientific limits of the results, (b) the negative and
corrected findings we chose to keep visible rather than bury, and (c) the scope waived to the
hardening backlog under Amendment A1. Nothing here is hidden in a footnote elsewhere; this is the
single honest ledger.

Release anchor for every metric named below: v3 dataset manifest
`gate12_5-dataset-v3.json` (immutable run id
`dd8def51705710fa4de39cfed1a22d49929c9916ae51114ffd91feb0f2975e98`, source run
`gate8-full-corpus-v3`). Regenerate the numbers with `make reports-v3` / `make readme-tables`.

---

## 1. Scientific limitations of the results

### 1.1 Detection is structurally blind to gray faults — even under load
The classical single-interface detection ensemble (oper-state FSM + robust-EWMA/z + CUSUM, frozen
on train+validation) detects the **blunt** faults (admin_shutdown, carrier_loss, intermittent_link:
52/52 each) and does **not** detect the **gray** faults (rate_limited_uplink 0/52, impaired_link
0/52). Test-split recall is therefore **0.60** — blunt faults only.

This is **not** a tuning miss and **not** fixed by traffic. The v3 corpus is collected *under load*,
and the gray faults still do not produce a large enough absolute single-interface counter anomaly to
fire the frozen detector within the causal window. It is a structural property of single-interface
absolute-threshold detection. We report it as a finding, not an embarrassment: it is precisely the
gap the learned localization models close (§1.2). (Artifact: `gate12_5-detection-v3.txt`.)

### 1.2 Learned localization recovers gray faults, but exact-link top-1 is the weak spot
Localizing the faulted link among 8 fabric-link candidates, the oper-state rule is provably at
chance on gray faults (AUROC **0.500** — the link never goes oper-down under load). Learned models
recover them: with strictly-causal temporal features (v2), gray-fault AUROC reaches ~**0.91**
(rate_limited MLP 0.910 / GNN 0.907; impaired MLP 0.910 / GNN 0.721).

Honest weak spot: **exact-link top-1** is materially lower than AUROC. Best gray top-1 (MLP v2):
rate_limited_uplink 0.885, impaired_link 0.731 — i.e. the model reliably ranks the faulted link high
but does not always place it first. The blunt faults are near-solved (top-1 0.96–1.00); the gray
faults are recovered-but-not-solved. (Artifacts: `localization-v3.txt`, `gate12_5-localization-v2.txt`.)

### 1.3 Healthy control sits at chance for every method — by design, reported as such
`healthy_control` localization AUROC is ~0.50 for rule, MLP, and GNN alike. This is the **correct**
result — there is no faulted link to find, so any above-chance score would indicate manufactured
localization or position leakage. We publish it precisely because a suspiciously high control number
would be the tell of a broken evaluation.

### 1.4 The GNN's flat impaired result was a confound, resolved as data-scarcity (not a ceiling)
On the frozen leaf3/leaf4 test split the GNN under-performs the MLP on impaired_link (AUROC 0.721 vs
0.910). We did not leave this ambiguous. A supplementary leave-one-leaf-out 4-fold CV (3 training
leaves per fold) lifts the GNN's impaired AUROC 0.721 → 0.802 and narrows the GNN–MLP gap from 0.19
to 0.07 (CIs overlap) — i.e. the flat result reflects the impaired-class training count (26), not a
model ceiling. The pre-registered leaf3/leaf4 numbers remain THE headline; the CV is a labeled
supplement, not a replacement. (Artifact: `gate12_5-localization-cv.txt`.)

### 1.5 Lab corpus, not production traffic
The corpus is collected on a containerlab SR Linux 2-spine/4-leaf fabric under *synthetic* traffic
load. It is a controlled research corpus with injected, ground-truthed faults — not captured
production incidents. Absolute detection/localization numbers are properties of this fabric and load
profile; they are not a claim about any specific production network. See `docs/DATA_CARD.md`.

---

## 2. Negative and corrected findings we kept visible

### 2.1 The traffic-free (v2) corpus produced a wrong conclusion — preserved, not erased
The original v2 corpus was collected **without** traffic load. On it, gray faults produced no device
signal, localization was oper-state-only, and we concluded "a neural model cannot beat the rule, so
it is not built." **That conclusion was an artifact of a hollow corpus, not a property of the
problem.** The v3 under-load corpus overturns it quantitatively. We did not rewrite history: the v2
manifest (`gate9-dataset.json`) and its report remain immutable in the artifact trail, the wrong
conclusion is preserved in git history and in `gate12_5-preregistration.txt`, and the correction is
the visible integrity record. (Bible §16: a new benchmark version supersedes; old results stay
immutable.)

### 2.2 A refuted sub-hypothesis (octet asymmetry)
While diagnosing the impaired-link blind spot we hypothesized the loss would show up as an octet
asymmetry between endpoints. We tested it and it was **refuted** (AUROC 0.42 — worse than chance).
The recoverable signal turned out to live in throughput *instability over time*, not directional
asymmetry. The refuted hypothesis is recorded, not quietly dropped.

### 2.3 Detection window-length leakage (found and closed)
An early detection result falsely scored gray faults 52/52. The cause was **incident-duration
leakage** (§10.3, R28): the collector used a longer window for gray faults, so window *length*
correlated with fault class and the detector was scoring off length, not signal. Fixed by truncating
every incident to a common 25 s window before detection. The corrected (honest) result is the 0/52
gray detection of §1.1.

---

## 3. Scope waived to the hardening backlog (Amendment A1 / ADR-001)

These are **deferred, not done**. They are fully specified in planning docs 03/04 and tracked in
`docs/backlog.md`; promotion back to core requires a superseding ADR. Justification: single-operator
lab deployment with no untrusted callers (see `docs/decisions/ADR-001-scope-waivers.md`). No release
claim implies these properties.

| Waived (backlog) | What core DOES keep |
|---|---|
| Approval expiry + revocation binding/blocking (H02/H03) | Immutable SHA-256 plan digest bound to approval; edit/drift blocks execution |
| Multi-worker executor leasing + transactional outbox (H06) | Single executor with DB unique-constraint idempotency + `outcome_unknown` reconciliation |
| JWT rotation/revocation infrastructure + API rate limits (I02) | Short-lived JWT in HttpOnly/Secure/SameSite cookie, JWT claims, RBAC, IDOR protection, **CSRF (core)** |
| Cryptographic tamper-evident audit hash chain (I05) | Append-only audit with FK integrity; audit failure blocks state mutation |
| Full multi-service restart matrix (J03) | Executor + PostgreSQL restart determinism |
| Backup / point-in-time-recovery + restore drills (J04) | (none — pure hardening item) |
| **H07 full precheck suite wired to live execution (A2, ADR-004)** | Live `execute_job` enforces approval-digest + allowlist + mgmt-interface |

### 3.1 H07 — live remediation enforces a narrower safety subset than the full suite (Amendment A2)
The live device-mutation path (`executor.execute_job`) enforces **approval-binding to the exact plan
digest/version, the action/value allowlist, and the management-interface guard**. The fuller
fail-closed suite — **last-usable-path, capacity headroom, stale/incomplete telemetry, and topology
drift** — is built and unit-tested to fail closed (`run_prechecks`, `tests/unit/test_prechecks.py`)
but is **not yet wired into live execution**. The blockers (a `Plan` deserializer and five real fact
providers) and the deliberate rejection of a stubbed-context "quick wire" (safety theater) are
documented in `docs/decisions/ADR-004-h07-precheck-wiring-waiver.md`. The clean-clone demo therefore
simulates the executor step offline; no live device mutation is exercised.

---

## 4. Runtime, trust-boundary, and external-benchmark limitations

- **Runtime isolation boundary (ADR-002).** Runtime isolation relies on the Docker Desktop VM
  boundary plus emptied host file-sharing, **not** a dedicated hypervisor VM. Documented residual
  risk; see `docs/decisions/ADR-002-lab-runtime-boundary.md`.
- **Same-host trust assumption (threat model A1).** Core does not defend against a same-host,
  human/privileged attacker. Loopback binding is the only claimed network control; the browser UI is
  reachable only over loopback HTTPS and never issues Secure cookies over plain HTTP. See
  `docs/threat-model.md`.
- **NIKA external benchmark — not run here.** The NIKA agent-only external benchmark is a documented
  known limitation, not executed in this release. The published paper (arXiv:2512.16381) and the
  pinned repository snapshot (`sands-lab/nika @ e6649f45…`) are kept strictly distinct, and no
  internal ClosCall metric is presented as NIKA validation. (Artifact: `gate12-nika.txt`.)

---

## 5. Where to verify each claim

- Detection numbers: `evals/reports/gate12_5-detection-v3.txt`
- Localization AUROC / top-1 + CIs: `evals/reports/localization-v3.txt`,
  `gate12_5-localization-v1.txt`, `gate12_5-localization-v2.txt`, `gate12_5-localization-cv.txt`
- Consolidated bundle: `evals/reports/gate12_5-evaluation.md` (`make reports-v3`)
- Immutable anchor + content hashes: `artifacts/manifests/gate12_5-dataset-v3.json`
- Waivers: `docs/decisions/ADR-001-scope-waivers.md`, `docs/backlog.md`
- Runtime / trust: `docs/decisions/ADR-002-lab-runtime-boundary.md`, `docs/threat-model.md`
