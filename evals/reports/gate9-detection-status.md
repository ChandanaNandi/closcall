# Gate 9 — Detection + Localization Status Note

Status: **detection and localization deliverables complete and honest; no neural model built (by
design, §11).** This is a status note, not a full Gate 9 sign-off (see "Exit-criteria status").

Scope decisions (pilot): (1) proceed on the existing `gate8-full-corpus-v2` corpus with **no
re-collection**; (2) for localization, **capture a healthy fabric-wide baseline** (not re-collect)
to populate non-target links. Both classical detection and rule-based localization are delivered;
the neural TS/MLP/GNN models are deliberately not built — see the localization finding.

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

## Localization (rule baseline, §11.6–11.7)

Per the pilot's baseline decision (`make capture-baseline`), each incident's graph uses the target
interface's real §9.1 window and the healthy fabric-wide baseline for all other links. The
root-cause link is scored by **operational state only** (the one real signal here) — deliberately
NOT "differs from baseline," which would let the capture artifact leak the answer for gray faults.
Ranked with average-rank tie handling (`make evaluate-localization`):

| | top-1 | top-3 | MRR |
|---|---|---|---|
| Blunt faults | **1.00** | 1.00 | 1.00 |
| Gray faults | 0.00 | 0.00 | 0.15 (expected-random) |
| Overall (test) | 0.60 | 0.60 | 0.66 |

**Finding:** localization is oper-state-driven — blunt faults are trivially localized (the down
link), gray faults are unsolvable (no device signal without traffic, R23). The oper-state rule is
the strong baseline and **a neural TS/MLP/GNN cannot beat it on this traffic-free corpus**, so per
§11 ("publish the result and keep the simpler system") the neural models are **not built**. Fidelity
limit: non-target links use a single static healthy baseline (not concurrent), captured identically
to the corpus windows to avoid a capture artifact (R29).

## Exit-criteria status (Gate 9)

Gate 9 exit is "frozen test reports include all misses, CIs, strata, and ablations; results reproduce
from manifest/run ID." Against that:

- ✅ **misses** — per-class recall + localization rank report every miss (gray 0/52 each).
- ✅ **strata** — metrics reported per location-inductive split (train/val/test).
- ✅ **CIs** — detection: 95% incident-clustered bootstrap (n=2000, seed=1337), reproducible (§10.4).
- ⚠️ **ablations** — the §11.9 invariance tracks presuppose a neural model; none is built (the rule
  baseline is unbeatable on this corpus, §11), so the ablations are N/A here — documented, not skipped.
- ◻️ **reproduce from manifest/run ID** — deterministic + read-only from the verified corpus; a
  formal §9.4 dataset-manifest binding is built (`datasets/manifest.py`) but not yet emitted.

**Conclusion:** detection and localization are complete, honest, and leak-audited. Gate 9 is **not
formally signed off** — it lacks a neural-model track (deliberately, per §11) and a bound dataset
manifest; and the corpus is traffic-free, which caps gray-fault observability. These are documented
limitations, not hidden gaps.

## Provenance

- Commits: detectors `61dd0a6`; feature/graph/split builders `b480b43`/`d4f3066`/`606f1a6`; adapter
  + fixes `03bf92a`; detection eval + leak fix `9a4b9b2`; CIs `e8e7431`.
- Corpus: `gate8-full-corpus-v2`, 312 incidents, `make corpus-verify` → 0 failed (incl. §9.1 windows).
  Healthy baseline: 20 SR-Linux endpoints (`make capture-baseline`).
- Tests: 108 unit/property, all pure/offline. `make lint` + `make typecheck` clean.
- Report artifacts: `gate9-detection.txt` (`make evaluate-sensors`), `gate9-localization.txt`
  (`make evaluate-localization`).
