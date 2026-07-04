# Gate 12 — Consolidated Evaluation

Every result below is anchored to one immutable run id (the §9.4 dataset manifest). This report is
generated ONLY from that manifest + the study artifacts it binds; regenerate with `make reports`.

## Immutable run anchor
- dataset: gate9-corpus
- source run id(s): gate8-full-corpus-v2
- manifest hash (immutable run id): 58d2cf31a55348bdb0af4b066f0a0dd5a5ea20d75b54b4ab6fe787ad5de84771
- code revision: d2dfd2a1f7a86fed164ff71968ecfb45db1c1f20
- split manifest: bd3070efaf4684f766f9e4a5997753bd3072d6f2c3ee1edf0ca6808dabc1860d
- feature schema: 35f6e540b9928d525c4d3d9266e3a5d0a5c0f4c25a6e448ae1811d0d6caaad7a

## Detection study (§10.4; artifact: gate9-detection.txt)
```
ClosCall Gate 9 — detection evaluation (classical ensemble)
frozen config (fit on TRAIN+VALIDATION): ewma_z=3.0 cusum_h=4.0 fsm_persistence=2 horizon_s=60.0
CIs: 95% incident-clustered bootstrap, n=2000, seed=1337 (§10.4)

[train] recall=0.60 [0.48,0.72] precision=1.00 [1.00,1.00] F1=0.75 [0.65,0.84] FP/healthy=0.00 [0.00,0.00] latency(med/p90)=5/15s [39/65 faults, 0/13 healthy fired]
[validation] recall=0.60 [0.48,0.72] precision=1.00 [1.00,1.00] F1=0.75 [0.65,0.84] FP/healthy=0.00 [0.00,0.00] latency(med/p90)=5/15s [39/65 faults, 0/13 healthy fired]
[test] recall=0.60 [0.52,0.69] precision=1.00 [1.00,1.00] F1=0.75 [0.68,0.81] FP/healthy=0.00 [0.00,0.00] latency(med/p90)=5/15s [78/130 faults, 0/26 healthy fired]

per-class recall (all splits):
  admin_shutdown       52/52  (blunt)
  carrier_loss         52/52  (blunt)
  impaired_link         0/52  (gray)
  intermittent_link    52/52  (blunt)
  rate_limited_uplink   0/52  (gray)

METHOD: every incident truncated to a common 25s window — the collector used a longer window for gray faults, and detecting off that length is incident_duration leakage (§10.3, found R28). Without this fix gray faults falsely scored 52/52.
NOTE (R23): gray tc-faults (rate_limited_uplink, impaired_link) produce no device-counter signal without traffic load — a documented detection blind spot, not a false negative bug.
```

## Localization study (§11.6-11.7; artifact: gate9-localization.txt)
```
ClosCall Gate 9 — localization evaluation (oper-state rule baseline)
candidates=12 physical links; root cause is a physical-link candidate (§4.2)

[train] top1=0.60 top3=0.60 MRR=0.66 (n=65)
[validation] top1=0.60 top3=0.60 MRR=0.66 (n=65)
[test] top1=0.60 top3=0.60 MRR=0.66 (n=130)

per-class (all splits):
  admin_shutdown       top1=1.00 top3=1.00 MRR=1.00 (n=52)  (blunt)
  carrier_loss         top1=1.00 top3=1.00 MRR=1.00 (n=52)  (blunt)
  impaired_link        top1=0.00 top3=0.00 MRR=0.15 (n=52)  (gray)
  intermittent_link    top1=1.00 top3=1.00 MRR=1.00 (n=52)  (blunt)
  rate_limited_uplink  top1=0.00 top3=0.00 MRR=0.15 (n=52)  (gray)

FINDING: localization is oper-state-driven — blunt faults trivially localized (the down link), gray faults unsolvable (no device signal without traffic, R23). The oper-state rule is the strong baseline; a neural model (§11.7/11.8) cannot beat it on this corpus, so per §11 it is not built. Fidelity limit: non-target links use a single static healthy baseline (not concurrent), captured identically to the corpus windows to avoid an artifact.
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

## External benchmark — NIKA (agent-only)
STATUS: not yet run (piece 4). When run, this is an AGENT-ONLY external result — our
diagnostic agent against the NIKA harness — reported separately from internal metrics.
- Published benchmark: arXiv:2512.16381 (paper version).
- Repository snapshot (pinned, distinct from the paper): sands-lab/nika @ e6649f45651d711a3ecb8d3f53befdcbcdb8961f.
NOTE: no internal ClosCall metric above is NIKA validation; NIKA is a separate external
harness with its own incidents and scoring.

## Integrity notes (Gate 12 exit)
- Reports are generated only from the immutable manifest run id (refused without it).
- NIKA paper (arXiv:2512.16381) and repo snapshot (sands-lab/nika @ e6649f45651d711a3ecb8d3f53befdcbcdb8961f) are kept distinct.
- No internal ClosCall metric is presented as NIKA validation.
- Honest scope: the corpus is traffic-free, so gray faults are a documented detection blind spot and
  localization is oper-state-driven (R23/R29); neural TS/MLP/GNN were not built as they cannot beat
  the oper-state baseline on this corpus (§11).
