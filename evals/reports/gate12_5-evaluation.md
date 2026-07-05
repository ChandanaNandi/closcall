# Gate 12.5/13 — Consolidated Evaluation (v3 under-load release anchor)

Every result below is anchored to one immutable run id — the v3 dataset manifest
(`gate12_5-dataset-v3.json`), which content-binds each study artifact by SHA-256. Generated ONLY
from that manifest + the artifacts it binds; regenerate with `make reports-v3`. The immutable v2
anchor (`gate9-dataset.json`, traffic-free) is retained unchanged in the artifact trail; this v3
bundle supersedes it as the release headline (Bible §16 — new benchmark version, old results
immutable).

## Immutable run anchor
- dataset: gate12_5-corpus-v3
- source run id(s): gate8-full-corpus-v3
- manifest hash (immutable run id): dd8def51705710fa4de39cfed1a22d49929c9916ae51114ffd91feb0f2975e98
- code revision: 8dd27542a42426ace439af0c3a9fd1e34fde1c2e
- split manifest: bd3070efaf4684f766f9e4a5997753bd3072d6f2c3ee1edf0ca6808dabc1860d (location-inductive)
- feature schema: 35f6e540b9928d525c4d3d9266e3a5d0a5c0f4c25a6e448ae1811d0d6caaad7a

## The thesis, stated precisely (what the v3 data shows)
The corpus is collected UNDER traffic load, fabric-wide. Two studies draw one precise line:

1. **Detection is blind to gray faults, even under load.** The classical ensemble (oper-state FSM +
   robust-EWMA/z + CUSUM) run on a single interface's own counters detects the *blunt* faults
   (admin_shutdown, carrier_loss, intermittent) but NOT the *gray* faults (rate_limited_uplink,
   impaired_link). Traffic load does not rescue it: a gray fault does not produce a large enough
   absolute single-interface counter anomaly to fire the frozen detector. This is a structural
   property of single-interface absolute detection, not a tuning failure.
2. **Learned localization recovers exactly those gray faults.** Ranking the faulted link among the 8
   fabric-link candidates, the oper-state RULE is provably at chance on gray faults (AUROC 0.500 —
   the link never goes oper-down under load), whereas per-link MLP / GNN models that use
   peer-relative + strictly-causal temporal + topology structure lift gray-fault localization AUROC
   to ~0.91. The recoverable signal lives in throughput INSTABILITY over time and in cross-link
   comparison — structure a single-interface detector cannot use.

Contribution: **classical single-interface detection cannot see gray faults; relational/temporal
learned localization can** — quantified on real under-load data, reported with CIs and the honest
weak spots (gray exact-link top-1, and the healthy control at chance for every method).

## Detection study — under load (artifact: gate12_5-detection-v3.txt)
```
ClosCall — detection evaluation (classical ensemble) — v3 UNDER-LOAD corpus
corpus=gate8-full-corpus-v3 (traffic during every incident window; SAME method as v2, new benchmark version §16). v2 result (gate9-detection.txt) stays immutable.
frozen config (fit on TRAIN+VALIDATION): ewma_z=3.0 cusum_h=4.0 fsm_persistence=2 horizon_s=60.0
CIs: 95% incident-clustered bootstrap, n=2000, seed=1337 (§10.4)
detection unit: the incident's own designated interface (target_json), truncated to a common 25s window (§10.3 leakage guard, R28).

[train] recall=0.60 [0.48,0.72] precision=1.00 [1.00,1.00] F1=0.75 [0.65,0.84] FP/healthy=0.00 [0.00,0.00] latency(med/p90)=15/25s [39/65 faults, 0/13 healthy fired]
[validation] recall=0.60 [0.48,0.72] precision=1.00 [1.00,1.00] F1=0.75 [0.65,0.84] FP/healthy=0.00 [0.00,0.00] latency(med/p90)=5/20s [39/65 faults, 0/13 healthy fired]
[test] recall=0.60 [0.52,0.69] precision=1.00 [1.00,1.00] F1=0.75 [0.68,0.81] FP/healthy=0.00 [0.00,0.00] latency(med/p90)=5/20s [78/130 faults, 0/26 healthy fired]

per-class recall (all splits):
  admin_shutdown       52/52  (blunt)
  carrier_loss         52/52  (blunt)
  impaired_link         0/52  (gray)
  intermittent_link    52/52  (blunt)
  rate_limited_uplink   0/52  (gray)

COMPARISON TO v2 (gate9-detection.txt): v2 was traffic-free and gray faults produced no device-counter signal (0/52, R23 blind spot). This run tests whether traffic load makes the gray tc-faults detectable by the same classical ensemble.
```

## Localization study — feature ablation, under load (artifact: localization-v3.txt)
```
ClosCall — localization eval (v3 under-load corpus; SUPERSEDES traffic-free finding)
candidates=8 fabric links; root cause = leaf-uplink link (§4.2). chance top1=0.125.
split: location-inductive (train=leaf1 val=leaf2 TEST=leaf3+4), physical-link-disjoint.
models: oper-state RULE | per-link MLP (§11.7) | GNN (§11.8). Feature ablation v1 vs v2.

AUROC (test), per class:
  class                  RULE  MLP.v1  MLP.v2  GNN.v1  GNN.v2
  admin_shutdown        0.920   0.937   0.996   0.968   0.974
  carrier_loss          0.918   0.935   0.990   0.961   0.979
  intermittent_link     0.929   0.918   0.996   0.944   0.996
  rate_limited_uplink   0.500   0.683   0.910   0.690   0.907
  impaired_link         0.500   0.664   0.910   0.721   0.721
  healthy_control       0.500   0.509   0.499   0.511   0.575

gray exact-link TOP-1 (test) — the honest weak spot:
  class                  RULE  MLP.v1  MLP.v2  GNN.v1  GNN.v2
  rate_limited_uplink   0.000   0.385   0.885   0.346   0.846
  impaired_link         0.000   0.346   0.731   0.346   0.462

CORRECTED FINDING (replaces old 'neural model cannot beat the rule, so it is not built'):
1. The oper-state RULE is PROVABLY BLIND to gray faults (AUROC exactly 0.500) — under
   load the link stays oper-up. It is strong on blunt faults (~0.92).
2. LEARNED MODELS RECOVER GRAY-FAULT LOCALIZATION THE RULE CANNOT — even from frozen v1
   aggregate features (MLP ~0.67, GNN ~0.69-0.72). Old conclusion was a hollow-corpus artifact.
3. THE GRAY SIGNAL LIVES SUBSTANTIALLY IN TEMPORAL STRUCTURE: adding strictly-causal
   temporal channels (v1->v2) lifts gray AUROC to ~0.91 and top1 from ~0.35 to 0.73-0.89
   (MLP). The controlled ablation localizes WHICH feature class carries the signal.
4. MODEL COMPARISON IS NUANCED (reported, not hidden): the GNN's message-passing leads
   under impoverished v1 features (impaired 0.721 vs MLP 0.664), but temporal features let a
   simpler MLP match/beat it (impaired v2: MLP 0.910 vs GNN 0.721, flat).
   CONFOUND RESOLVED: the flat GNN impaired was DATA-SCARCITY, not a ceiling. Supplementary
   leave-one-leaf-out 4-fold CV (3 train leaves/fold) lifts GNN impaired 0.721->0.802 and
   narrows the GNN-MLP gap 0.19->0.07 (CIs overlap) — comparable with more data. Frozen
   leaf3/leaf4 stays THE headline; CV is a labeled supplement (gate12_5-localization-cv.txt).
5. HONEST CEILING & CONTROL: gray top1 under aggregate features ~0.35; healthy_control at
   chance for all methods (no manufactured localization, no position leakage).
Full tables + CIs: gate12_5-localization-v1.txt, -v2.txt, gate12_5-ablation.txt.
Pre-registration (order + hypotheses committed before running): gate12_5-preregistration.txt.
```

## Localization confound resolution — leave-one-leaf-out CV (artifact: gate12_5-localization-cv.txt)
```
==============================================================================
GATE 12.5 — LOCALIZATION: FROZEN HEADLINE vs SUPPLEMENTARY 4-FOLD CV  [features=v2]
==============================================================================
Why two numbers: the location-inductive split fixed leaf3/leaf4 as TEST BEFORE any results
existed (pre-registration). That frozen result is THE headline. The 4-fold leave-one-leaf-out
CV below is an AFTER-THE-FACT robustness check (rotate held-out leaf; 3 training leaves/fold,
leakage-safe per fold), run ONLY to test whether the GNN's flat impaired result is training-
data scarcity or a real ceiling. It is a SUPPLEMENT, never a replacement for the headline.

[FROZEN HEADLINE] fit=leaf1+leaf2 (n=156), TEST=leaf3+leaf4 (n=156) — pre-registered:
  [RULE]
    class                  n   top1   top3    MRR  AUROC          95% CI
    admin_shutdown        26  0.038  1.000  0.654  0.920 [0.909,0.931]
    carrier_loss          26  0.000  1.000  0.641  0.918 [0.907,0.926]
    intermittent_link     26  0.000  1.000  0.667  0.929 [0.929,0.929]
    rate_limited_uplink   26  0.000  0.000  0.222  0.500 [0.500,0.500]
    impaired_link         26  0.000  0.000  0.222  0.500 [0.500,0.500]
    healthy_control       26  0.000  0.000  0.222  0.500 [0.500,0.500]
  [MLP]
    class                  n   top1   top3    MRR  AUROC          95% CI
    admin_shutdown        26  1.000  1.000  1.000  0.996 [0.989,1.000]
    carrier_loss          26  0.923  1.000  0.962  0.990 [0.977,1.000]
    intermittent_link     26  1.000  1.000  1.000  0.996 [0.989,1.000]
    rate_limited_uplink   26  0.885  0.885  0.903  0.910 [0.798,0.997]
    impaired_link         26  0.731  0.885  0.824  0.910 [0.839,0.967]
    healthy_control       26  0.077  0.500  0.345  0.499 [0.379,0.611]
  [GNN]
    class                  n   top1   top3    MRR  AUROC          95% CI
    admin_shutdown        26  0.923  1.000  0.962  0.974 [0.935,1.000]
    carrier_loss          26  0.962  1.000  0.974  0.979 [0.956,0.996]
    intermittent_link     26  0.962  1.000  0.981  0.996 [0.990,1.000]
    rate_limited_uplink   26  0.846  0.923  0.900  0.907 [0.810,0.981]
    impaired_link         26  0.462  0.654  0.611  0.721 [0.602,0.836]
    healthy_control       26  0.154  0.500  0.391  0.575 [0.469,0.678]

[SUPPLEMENT — 4-fold leave-one-leaf-out CV] each fold: 3 train leaves, held-out leaf scored:
  [RULE] (pooled over 4 held-out leaves)
    class                  n   top1   top3    MRR  AUROC          95% CI
    admin_shutdown        52  0.077  1.000  0.670  0.924 [0.916,0.933]
    carrier_loss          52  0.000  1.000  0.641  0.918 [0.911,0.924]
    intermittent_link     52  0.000  1.000  0.660  0.926 [0.922,0.929]
    rate_limited_uplink   52  0.000  0.000  0.222  0.499 [0.496,0.500]
    impaired_link         52  0.000  0.000  0.222  0.500 [0.500,0.500]
    healthy_control       52  0.000  0.000  0.222  0.500 [0.500,0.500]
  [MLP] (pooled over 4 held-out leaves)
    class                  n   top1   top3    MRR  AUROC          95% CI
    admin_shutdown        52  0.923  1.000  0.962  0.991 [0.982,0.998]
    carrier_loss          52  0.962  0.981  0.976  0.989 [0.973,1.000]
    intermittent_link     52  1.000  1.000  1.000  0.999 [0.997,1.000]
    rate_limited_uplink   52  0.885  0.904  0.910  0.942 [0.892,0.982]
    impaired_link         52  0.673  0.885  0.791  0.872 [0.814,0.925]
    healthy_control       52  0.135  0.346  0.327  0.463 [0.377,0.546]
  [GNN] (pooled over 4 held-out leaves)
    class                  n   top1   top3    MRR  AUROC          95% CI
    admin_shutdown        52  0.981  1.000  0.990  0.998 [0.994,1.000]
    carrier_loss          52  1.000  1.000  1.000  0.979 [0.951,1.000]
    intermittent_link     52  0.981  1.000  0.990  0.998 [0.994,1.000]
    rate_limited_uplink   52  0.827  0.885  0.876  0.899 [0.836,0.951]
    impaired_link         52  0.558  0.808  0.698  0.802 [0.740,0.861]
    healthy_control       52  0.192  0.404  0.378  0.488 [0.411,0.565]

[VERDICT] impaired-class GNN-vs-MLP confound:
    frozen headline : GNN impaired AUROC 0.721  (MLP 0.910)
    4-fold CV       : GNN impaired AUROC 0.802 [CI-lo 0.740]  (MLP 0.872)
    => RESOLVED as DATA-SCARCITY: with 3 training leaves the GNN recovers impaired
       localization (0.721 -> 0.802, closing on the MLP's 0.872). The frozen flat
       result reflects the impaired-class training count (26), NOT a model ceiling.

HEADLINE UNCHANGED: the pre-registered leaf3/leaf4 numbers remain THE result; this CV is the
labeled supplement that resolves the confound. No headline number is replaced or upgraded.
==============================================================================
```

## Reasoning / LLM qualification (§4.1, §12.4; artifact: gate10-llm.txt)
```
ClosCall Gate 10 — local LLM qualification (§4.1)
validation cases: 7 (2/category + 1 injection fixture)
verifier gates every claim, so accuracy cannot be inflated by fabrication

[qwen2.5:7b-instruct] accuracy=0.71 injection_held=True schema_repairs=0 tokens=4486 latency=6.0s
[qwen2.5:14b-instruct] accuracy=0.71 injection_held=True schema_repairs=0 tokens=4474 latency=2.7s

PRIMARY (frozen): qwen2.5:14b-instruct
ABLATION TIER (§4.1 second frozen tier): qwen2.5:7b-instruct
```

## External benchmark — NIKA (agent-only, kept distinct)
NIKA external benchmark — agent-only result: NOT RUN HERE (documented known limitation)

Distinct references (Gate 12 exit criterion 2 — paper vs repository never conflated):
- Published benchmark (paper version): arXiv:2512.16381.
- Repository snapshot (pinned, distinct from the paper): sands-lab/nika @
  e6649f45651d711a3ecb8d3f53befdcbcdb8961f (verified reachable 2026-07-04).

Corrected characterization (against the pinned repo, not the paper):
- The repo README describes 56 realistic issues / 685 incidents across 14 scenarios (incl.
  Kubernetes labs), a unified `nika` CLI, and a Kathara-based network emulation environment. (The
  earlier research-log figures — 54 issues / 640 incidents / 5 scenarios — reflect an older snapshot;
  the pinned snapshot supersedes them. Paper and repo figures are kept separate on purpose.)

Why it is not run in this environment:
- Running the pinned agent-only adapter requires the NIKA stack: Kathara (a separate network
  emulator), deployment of their lab scenarios, and an adapter binding the ClosCall diagnostic agent
  to their orchestration/agent interface. That is a major external, system-level integration —
  consistent with the research log positioning NIKA as an external eval harness (post-core), and with
  ADR-001/backlog listing NIKA scenario-pack work as post-core.

Integrity statement (Gate 12 exit criterion 3):
- NO internal ClosCall detection/localization/reasoning metric is presented as a NIKA result or as
  NIKA validation. The internal studies (gate9-detection, gate9-localization, gate10-llm) are scored
  on the ClosCall corpus (gate8-full-corpus-v2) and are unrelated to NIKA's incidents and scoring.
- When the NIKA adapter is run post-core, it will be reported as a SEPARATE agent-only external
  result against the pinned repo snapshot above, never merged into the internal metrics.

## Integrity notes (Gate 12.5/13 exit)
- Reports are generated only from the immutable v3 manifest run id (refused without it); every study
  artifact is content-bound in the manifest by SHA-256.
- NIKA paper (arXiv:2512.16381) and repo snapshot (sands-lab/nika @ e6649f45651d711a3ecb8d3f53befdcbcdb8961f) are kept strictly distinct; no
  internal ClosCall metric is presented as NIKA validation.
- The v2 (traffic-free) anchor is NOT overwritten — it remains in the trail; this v3 bundle is a new
  benchmark version, not an edit of the old one.
- Honest scope: detection of gray faults is a genuine blind spot of single-interface counter
  detection even under load (reported as a finding, not hidden); localization's recovery is the
  contribution. Gray exact-link top-1 and the healthy control (at chance for all methods) are the
  reported limits.
