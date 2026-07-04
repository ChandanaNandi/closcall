# Gate 9 — Detection Status Note

Status: **detection deliverable complete and honest; localization deferred.** This is a partial-gate
status note, not a Gate 9 sign-off (see "Exit-criteria status" below).

Scope decision (pilot): proceed with **detection only** on the existing `gate8-full-corpus-v2`
corpus; **no re-collection.** Localization is deferred, not abandoned.

## What was built

Corpus-independent, pure, unit-tested (`sensors/`, `datasets/`), then wired end-to-end and run over
the real corpus:

| Piece | §ref | Module |
|---|---|---|
| Operational-state FSM | §11.1 | `sensors/rules/fsm.py` |
| Robust EWMA/z-score + CUSUM | §11.2 | `sensors/timeseries/statistical.py` |
| Causal event evaluator (persistence/hysteresis/cooldown, `t_detected`) | §11.3, §10.1 | `sensors/evaluator.py` |
| Window → detector-stream adapter | §11 wiring | `sensors/adapters.py` |
| Detection ensemble + config | §11.1–11.3 | `sensors/detection.py` |
| Evaluation (freeze on TRAIN+VAL → TEST) | §10.2, §10.4 | `scripts/evaluate_sensors.py` (`make evaluate-sensors`) |

Detectors are causal stream transducers (one sample in, at most one alarm out; never read ahead), so
online == offline replay by construction (§10.3). Thresholds are validation-tuned then frozen.

## Result (frozen config: ewma_z=3.0, cusum_h=4.0, fsm_persistence=2, common 25s window)

Metrics with 95% incident-clustered bootstrap CIs (n=2000, seed=1337, reproducible):

| split | recall | precision | F1 | FP/healthy | latency med/p90 |
|---|---|---|---|---|---|
| train | 0.60 [0.48, 0.72] | 1.00 [1.00, 1.00] | 0.75 [0.65, 0.84] | 0.00 [0.00, 0.00] | 5s / 15s |
| validation | 0.60 [0.48, 0.72] | 1.00 [1.00, 1.00] | 0.75 [0.65, 0.84] | 0.00 [0.00, 0.00] | 5s / 15s |
| test | 0.60 [0.52, 0.69] | 1.00 [1.00, 1.00] | 0.75 [0.68, 0.81] | 0.00 [0.00, 0.00] | 5s / 15s |

Per-class recall (all splits):

| fault class | detected | type |
|---|---|---|
| admin_shutdown | 52/52 | blunt |
| carrier_loss | 52/52 | blunt |
| intermittent_link | 52/52 | blunt |
| impaired_link | 0/52 | gray |
| rate_limited_uplink | 0/52 | gray |

**Reading:** the device-telemetry detector localizes link-down faults perfectly (156/156) with **zero
false positives** on healthy controls, and is **blind to congestion (gray) faults** — which produce
no device-counter signal without traffic load (R23). The 0.60 recall is the honest capability: 3 of
5 fault classes are detectable from device telemetry, 2 are not.

## Integrity finding — window-length leak (R28)

The first evaluation scored **F1 = 1.00 with gray faults at 52/52** — impossible given the gray
blind spot. Investigation: gray and healthy octet-rate streams are **identical** (a ~30 B/s BGP
keepalive pulse); the only difference was **window length** — the collector uses `WINDOW_GRAY_S=40`
for gray faults vs `WINDOW_BLUNT_S=25` elsewhere, so window length correlates with fault class.
CUSUM's warmup (5 samples) was only exceeded on the longer gray stream, so it fired on **length**,
not signal — `incident_duration` leakage (§10.3, `FORBIDDEN_FEATURE_COLUMNS`).

- **Caught by:** refusing to trust a too-perfect number and inspecting the raw streams.
- **Fixed by:** truncating every incident to a common 25s window before detection (eval-time).
- **Source note:** the confound lives in the raw corpus (`WINDOW_GRAY_S` ≠ `WINDOW_BLUNT_S`); a
  future collection should use a single window length for all classes. Not fixed now (no re-collect).

## Exit-criteria status (Gate 9)

Gate 9 exit is "frozen test reports include all misses, CIs, strata, and ablations; results reproduce
from manifest/run ID." Against that:

- ✅ **misses** — per-class recall reports every miss (gray 0/52 each).
- ✅ **strata** — metrics reported per location-inductive split (train/val/test).
- ✅ **CIs** — 95% incident-clustered bootstrap intervals (n=2000, seed=1337), reproducible (§10.4).
- ❌ **ablations** — these are the GNN invariance tracks (§11.9), part of the deferred localization.
- ◻️ **reproduce from manifest/run ID** — deterministic + read-only from the verified corpus; a
  formal §9.4 dataset-manifest binding is built (`datasets/manifest.py`) but not yet emitted for
  this run.

**Conclusion:** the detection deliverable is complete, honest, and leak-audited. Gate 9 as a whole is
**not signed off** — localization (§11.6–11.8), ablations, and CIs remain.

## Provenance

- Commits: detectors `61dd0a6`; feature/graph/split builders `b480b43`/`d4f3066`/`606f1a6`; adapter
  + fixes `03bf92a`; detection eval + leak fix `9a4b9b2`.
- Corpus: `gate8-full-corpus-v2`, 312 incidents, `make corpus-verify` → 0 failed (incl. §9.1 windows).
- Tests: 108 unit/property, all pure/offline. `make lint` + `make typecheck` clean.
- Report artifact: `evals/reports/gate9-detection.txt` (regenerate with `make evaluate-sensors`).
