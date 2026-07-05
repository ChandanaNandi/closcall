# ClosCall — Model Card

This document describes the four models/baselines packaged in the ClosCall v3
(under-load) release. It is a Gate 13 handoff deliverable. Every number,
hyperparameter, and metric below is transcribed from a source file in this
repository; the source is listed per claim in the final section. No value is
estimated. Where a value could not be verified from a file it is marked
`(not verified)`.

## Immutable run anchor

All metrics in this card are bound to one immutable run id — the v3 dataset
manifest — and are only meaningful against it.

- **manifest hash (immutable run id):** `dd8def51705710fa4de39cfed1a22d49929c9916ae51114ffd91feb0f2975e98`
- **code revision:** `8dd27542a42426ace439af0c3a9fd1e34fde1c2e`
- dataset kind: `gate12_5-corpus-v3`
- source run id: `gate8-full-corpus-v3`
- split manifest hash: `bd3070efaf4684f766f9e4a5997753bd3072d6f2c3ee1edf0ca6808dabc1860d` (location-inductive)
- feature schema hash: `35f6e540b9928d525c4d3d9266e3a5d0a5c0f4c25a6e448ae1811d0d6caaad7a`
- master seed: `1337`

Source: `artifacts/manifests/gate12_5-dataset-v3.json`.

## The release thesis (stated precisely)

Two studies over the same under-load corpus draw one precise line:

1. **Classical single-interface detection is structurally blind to gray faults,
   even under traffic load.** The detection ensemble (oper-state FSM +
   robust-EWMA/z + CUSUM) run on an interface's *own* counters detects the blunt
   faults (admin_shutdown, carrier_loss, intermittent_link) but detects **0/52**
   of each gray fault (rate_limited_uplink, impaired_link). Traffic load does not
   rescue it: a gray fault does not produce a large enough *absolute
   single-interface* counter anomaly to fire the frozen detector. This is a
   structural property of single-interface absolute-counter detection, not a
   tuning failure.

2. **Learned localization recovers exactly those gray faults the detector
   misses.** Ranking the faulted link among 8 fabric-link candidates, the
   oper-state RULE is provably at chance on gray faults (AUROC 0.500 — under load
   the link never goes oper-down), whereas per-link MLP / GNN models that use
   peer-relative + strictly-causal temporal + topology structure lift gray-fault
   localization AUROC to ~0.91. The recoverable signal lives in throughput
   instability over time and in cross-link comparison — structure a
   single-interface detector cannot use.

Honest weak spots are reported, not hidden: gray exact-link top-1 is lower than
gray AUROC; healthy_control is at chance for every method (no manufactured
localization, no position leakage); and the frozen GNN-impaired result is flat
until more training leaves are available.

## Shared experimental setup (localization models 1-3)

- **Corpus:** `gate8-full-corpus-v3` (collected under traffic load, fabric-wide).
- **Split:** location-inductive (`LOCATION_INDUCTIVE_POLICY`), physical-link-disjoint.
  Models fit on train (leaf1) + validation (leaf2); TEST is leaf3 + leaf4, scored
  once. Fit n = 156 incidents, test n = 156 incidents.
- **Candidates:** 8 fabric-link candidates per incident; root cause = leaf-uplink
  link. Chance top-1 = 0.125.
- **Determinism:** `torch.manual_seed(0)`, `np.random.seed(0)` at run start;
  feature code contains no date/random calls. Localization AUROC 95% CIs are from
  a fixed-seed bootstrap (n = 2000, LCG seed 20260704).
- **Causality guard:** only samples with `event_time <= as_of_at` (= window end)
  enter any feature, for both v1 and v2.

### Feature versions (the ablation axis)

- **v1** (`gate9-causal-features-v1`), iface_feat_dim = **5**: the frozen §9.2
  aggregate contract — `util_ratio`, `error_rate`, `discard_rate`,
  `sample_age_s`, `missingness_mask`. Nothing added.
- **v2** (`gate9-causal-features-v2-temporal`), iface_feat_dim = **24**: v1 plus
  strictly-causal temporal channels. For each of the 6 counters
  (`in_octets`, `out_octets`, `in_error_packets`, `out_error_packets`,
  `in_discarded_packets`, `out_discarded_packets`): per-step rate **std**,
  **slope** (linear fit over the rate series), and **CoV** (`std / (mean + 1.0)`)
  — 6 × 3 = 18 channels — plus **oper-state transition count** over the window.
  That is 19 added channels → 5 + 19 = 24.

Source for setup and feature versions:
`scripts/gate12_5_localization_ablation.py`.

---

## Model 1 — Oper-state RULE (localization baseline)

### Intended use
A zero-parameter reference baseline for link localization. It answers "which link
looks faulted?" using only the oper-state signal, and exists to quantify how far a
purely oper-state view can go — and where it is provably blind.

### Architecture / config
No fitting, no parameters. For each candidate link, score = 1.0 if either endpoint
interface is oper-down anywhere in the causal window, else 0.0. Ties are broken by
average-rank when computing top-k. See `rule_score_fn`.

### Training data / split
None (unfitted). Evaluated on the same TEST set (leaf3 + leaf4, n = 156) as the
learned models.

### Inputs / features
Oper-state samples within the causal window only. No counters, no temporal
features. Feature version (v1/v2) does not change its behavior — the RULE numbers
are identical across v1 and v2.

### Metrics — per-class AUROC and top-1 (TEST, n = 26 per class)

| class | top1 | AUROC | 95% CI |
|---|---|---|---|
| admin_shutdown | 0.038 | 0.920 | [0.909, 0.931] |
| carrier_loss | 0.000 | 0.918 | [0.907, 0.926] |
| intermittent_link | 0.000 | 0.929 | [0.929, 0.929] |
| rate_limited_uplink | 0.000 | 0.500 | [0.500, 0.500] |
| impaired_link | 0.000 | 0.500 | [0.500, 0.500] |
| healthy_control | 0.000 | 0.500 | [0.500, 0.500] |

Note: the RULE reaches AUROC ~0.92 on blunt faults (the faulted link's endpoint
does go oper-down) but top-1 is near zero on all classes because oper-down is not
unique to the true link — many candidate links share a down endpoint, so the
correct link is rarely ranked strictly first.

Source: `evals/reports/gate12_5-localization-v1.txt` (RULE block; identical in
`-v2.txt` and the frozen headline of `-cv.txt`).

### Limitations
- **Provably at chance on gray faults** (AUROC exactly 0.500): under load a
  rate-limited or impaired link stays oper-up, so the RULE has no signal. This is
  the load-bearing negative result of the ablation.
- top-1 is near zero even on blunt faults it scores well on by AUROC — it cannot
  disambiguate *which* of several down-endpoint links is the root cause.

---

## Model 2 — Per-link MLP (§11.7)

### Intended use
Localization of the faulted fabric link from per-link feature vectors, without any
topology/graph structure. It tests how much a peer-relative + (optionally)
temporal feature representation recovers on its own.

### Architecture / config
`sklearn.neural_network.MLPClassifier` with:
- `hidden_layer_sizes = (64, 32)`
- `alpha = 1e-2`
- `max_iter = 2000`
- `random_state = 0`
- inputs standardized with `StandardScaler` (fit on train+val).

Per-link representation: concatenate the two endpoint interfaces' feature vectors,
then append within-incident **relative** features — a robust z-score computed
per incident across the 8 links using median and MAD
(`(X - median) / (1.4826 * MAD + 1e-9)`). See `fit_mlp` and `link_row`.

### Training data / split
Fit on train (leaf1) + validation (leaf2), n = 156 incidents; TEST leaf3 + leaf4,
n = 156, scored once. Seed `random_state = 0`.

### Inputs / features
Per-interface v1 or v2 features (see shared setup), raw + within-incident relative.
No graph message passing.

### Metrics — per-class AUROC and top-1 (TEST, n = 26 per class)

**v1 features (aggregate only):**

| class | top1 | AUROC | 95% CI |
|---|---|---|---|
| admin_shutdown | 0.846 | 0.937 | [0.893, 0.972] |
| carrier_loss | 0.808 | 0.935 | [0.880, 0.982] |
| intermittent_link | 0.692 | 0.918 | [0.869, 0.959] |
| rate_limited_uplink | 0.385 | 0.683 | [0.540, 0.809] |
| impaired_link | 0.346 | 0.664 | [0.545, 0.771] |
| healthy_control | 0.115 | 0.509 | [0.380, 0.634] |

**v2 features (aggregate + strictly-causal temporal):**

| class | top1 | AUROC | 95% CI |
|---|---|---|---|
| admin_shutdown | 1.000 | 0.996 | [0.989, 1.000] |
| carrier_loss | 0.923 | 0.990 | [0.977, 1.000] |
| intermittent_link | 1.000 | 0.996 | [0.989, 1.000] |
| rate_limited_uplink | 0.885 | 0.910 | [0.798, 0.997] |
| impaired_link | 0.731 | 0.910 | [0.839, 0.967] |
| healthy_control | 0.077 | 0.499 | [0.379, 0.611] |

Source: `evals/reports/gate12_5-localization-v1.txt` and
`gate12_5-localization-v2.txt` (MLP blocks).

### Key finding
The MLP recovers gray-fault localization the RULE cannot even from frozen v1
aggregate features (gray AUROC ~0.66-0.68). Adding strictly-causal temporal
channels (v1→v2) lifts gray AUROC to 0.910 for both gray classes and gray top-1
from ~0.35 to 0.73-0.89. The controlled ablation localizes *which feature class*
carries the gray signal: temporal instability, not aggregate level.

### Limitations
- **Gray exact-link top-1 < gray AUROC:** even at v2, impaired_link top-1 is
  0.731 (vs AUROC 0.910). The model ranks the true link high but not always
  strictly first.
- **healthy_control at chance** (AUROC 0.499 at v2, 0.509 at v1): no manufactured
  localization on healthy incidents, no position/topology leakage. This is a
  control the model is *expected* to fail.

---

## Model 3 — GNN (§11.8)

### Intended use
Localization using per-interface features plus message passing over the fabric
graph, so the model can learn cross-link relational comparison directly rather
than through hand-built relative features.

### Architecture / config
Custom `GNN` (`torch.nn`), 2 mean-aggregation convolution layers:
- `l1 = Linear(in_dim, hid)`, `l2 = Linear(hid, hid)`, `hid = 32`.
- conv: `h = relu(lin(x + agg/deg))` with mean aggregation of neighbor
  embeddings (`index_add_` then divide by in-degree, clamped ≥ 1).
- link head: `head = Linear(2 * hid, 1)` applied to the **concatenation of the two
  endpoint interface embeddings**.
- optimizer: `torch.optim.Adam(lr = 1e-2, weight_decay = 1e-3)`.
- loss: `BCEWithLogitsLoss`; **120** epochs (full-batch over the fit incidents).
- node features standardized with `StandardScaler` (fit on train+val).

`in_dim` = iface_feat_dim (5 for v1, 24 for v2).

**Graph edges** (`load`): fabric-link edges (cross-device, both directions) plus
same-device edges (every pair of co-located interfaces on the same device). 16
interfaces (nodes) total. See `fit_gnn`, class `GNN`, and `load`.

### Training data / split
Fit on train (leaf1) + validation (leaf2), n = 156; TEST leaf3 + leaf4, n = 156,
scored once. Global seeds `torch.manual_seed(0)`, `np.random.seed(0)`.

### Inputs / features
Per-interface v1 or v2 features on graph nodes; the same fabric + same-device edge
set for message passing.

### Metrics — per-class AUROC and top-1 (TEST, n = 26 per class)

**v1 features (aggregate only):**

| class | top1 | AUROC | 95% CI |
|---|---|---|---|
| admin_shutdown | 0.962 | 0.968 | [0.918, 0.998] |
| carrier_loss | 0.885 | 0.961 | [0.908, 0.998] |
| intermittent_link | 0.846 | 0.944 | [0.923, 0.964] |
| rate_limited_uplink | 0.346 | 0.690 | [0.587, 0.798] |
| impaired_link | 0.346 | 0.721 | [0.626, 0.818] |
| healthy_control | 0.154 | 0.511 | [0.392, 0.642] |

**v2 features (aggregate + strictly-causal temporal):**

| class | top1 | AUROC | 95% CI |
|---|---|---|---|
| admin_shutdown | 0.923 | 0.974 | [0.935, 1.000] |
| carrier_loss | 0.962 | 0.979 | [0.956, 0.996] |
| intermittent_link | 0.962 | 0.996 | [0.990, 1.000] |
| rate_limited_uplink | 0.846 | 0.907 | [0.810, 0.981] |
| impaired_link | 0.462 | 0.721 | [0.602, 0.836] |
| healthy_control | 0.154 | 0.575 | [0.469, 0.678] |

Source: `evals/reports/gate12_5-localization-v1.txt` and
`gate12_5-localization-v2.txt` (GNN blocks).

### Model comparison (reported, not hidden)
The GNN's message-passing **leads under impoverished v1 features**
(impaired_link 0.721 vs MLP 0.664; rate_limited_uplink 0.690 vs 0.683). Once
temporal features are added, a simpler MLP matches or beats it: at v2 the MLP
reaches impaired AUROC 0.910 while the **GNN impaired stays flat at 0.721**.

### The GNN-impaired confound and its resolution
The flat v2 GNN-impaired result was tested for cause with a supplementary
leave-one-leaf-out 4-fold CV (rotate held-out leaf; 3 training leaves per fold,
leakage-safe per fold), pooled over the 4 held-out leaves (n = 52 per class):

- **Frozen headline:** GNN impaired AUROC **0.721** (MLP 0.910).
- **4-fold CV:** GNN impaired AUROC **0.802** [CI-lo 0.740] (MLP 0.872).

Verdict: **RESOLVED as data-scarcity**, not a model ceiling. With 3 training
leaves the GNN recovers impaired localization (0.721 → 0.802, closing on the MLP's
0.872, CIs overlap). The frozen flat result reflects the impaired-class training
count (26 incidents), not a ceiling. The pre-registered leaf3/leaf4 numbers remain
THE headline; the CV is a labeled supplement that resolves the confound — no
headline number is replaced or upgraded.

Source: `evals/reports/gate12_5-localization-cv.txt`.

### Limitations
- **Frozen impaired result is flat** at v2 (0.721) until more training leaves are
  available — a data-scarcity limit, documented above.
- **Gray exact-link top-1 < AUROC** (impaired top-1 0.462 at v2).
- **healthy_control near chance** (AUROC 0.511 v1 / 0.575 v2) — expected control,
  no localization on healthy incidents.

---

## Model 4 — Classical detection ensemble

### Intended use
Per-incident fault **detection** (fire / don't fire) on a single interface's own
counter and oper-state streams within the incident window. It answers "did
anything anomalous happen on this interface?" — not "which link is at fault."

### Architecture / config
`DetectorConfig` drives three detectors reduced to one per-incident outcome by the
causal event evaluator (an incident is DETECTED if any detector raises within the
horizon after onset; any alarm on a healthy incident is a false positive):

- **Oper-state FSM** (`OperStateDetector`) on the oper stream.
- **Robust-EWMA/z** (`RobustEwmaZScore`) on each counter-rate stream.
- **CUSUM** (`Cusum`) on each counter-rate stream.

**Frozen config** (fit on train + validation, then frozen):
`ewma_z = 3.0`, `cusum_h = 4.0`, `fsm_persistence = 2`, `horizon_s = 60.0`.

`DetectorConfig` code **defaults are placeholders** (per the module docstring) and
differ from the frozen config: `fsm_persistence = 2`, `fsm_cooldown_s = 30.0`,
`ewma_z = 4.0`, `ewma_persistence = 2`, `ewma_warmup = 4`, `cusum_k = 0.5`,
`cusum_h = 5.0`, `cusum_persistence = 1`, `horizon_s = 60.0`. The frozen `ewma_z`
and `cusum_h` above supersede the defaults for the release run. The frozen values
for `ewma_persistence`, `ewma_warmup`, `cusum_k`, `cusum_persistence`, and
`fsm_cooldown_s` are not restated in the report `(not verified whether the report
run used the code defaults or other values for these)`.

Source: `src/closcall/sensors/detection.py` (config + wiring);
`evals/reports/gate12_5-detection-v3.txt` (frozen values).

### Training data / split
Fit on train + validation, evaluated on train / validation / test. Detection unit:
the incident's own designated interface (`target_json`), truncated to a common 25s
window (leakage guard, R28). CIs: 95% incident-clustered bootstrap, n = 2000, seed
1337.

### Inputs / features
The window's adapted per-interface streams: oper-state stream + counter-rate
streams (via `detector_streams`). Single-interface only — no cross-link comparison.

### Metrics (overall, TEST split)

| metric | value | 95% CI |
|---|---|---|
| recall | 0.60 | [0.52, 0.69] |
| precision | 1.00 | [1.00, 1.00] |
| F1 | 0.75 | [0.68, 0.81] |
| FP/healthy | 0.00 | [0.00, 0.00] |
| latency med/p90 | 5 / 20 s | — |

Test counts: 78/130 faults detected, 0/26 healthy fired. Train and validation both
report recall 0.60, precision 1.00, F1 0.75, FP/healthy 0.00.

### Metrics — per-class recall (all splits pooled)

| class | recall | kind |
|---|---|---|
| admin_shutdown | 52/52 | blunt |
| carrier_loss | 52/52 | blunt |
| intermittent_link | 52/52 | blunt |
| rate_limited_uplink | 0/52 | gray |
| impaired_link | 0/52 | gray |

Source: `evals/reports/gate12_5-detection-v3.txt`.

### Key finding / limitations
- **Structurally blind to gray faults, even under load:** 0/52 detected for both
  rate_limited_uplink and impaired_link. A gray fault does not produce a large
  enough *absolute single-interface* counter anomaly to fire the frozen detector.
  This is a structural property of single-interface absolute-counter detection,
  not a tuning failure — and is the negative result that motivates learned
  localization. (In the v2 traffic-free corpus the same classes were also 0/52;
  adding traffic load did not make them detectable by this ensemble.)
- **Perfect precision, zero false positives** (0/26 healthy fired on test) — the
  0.60 overall recall is driven entirely by the two undetectable gray classes; all
  three blunt classes are detected perfectly.

---

## Source attribution (per numeric / hyperparameter claim)

| Claim | Source file |
|---|---|
| manifest hash, code revision, split/feature schema hashes, master seed 1337 | `artifacts/manifests/gate12_5-dataset-v3.json` |
| Split policy, fit/test n=156, causality guard, seeds `manual_seed(0)`/`np.random.seed(0)`, bootstrap seed 20260704 | `scripts/gate12_5_localization_ablation.py` |
| v1 keys (util_ratio/error_rate/discard_rate/sample_age_s/missingness_mask); v2 temporal channels (6 counters × std/slope/CoV + oper transitions); iface_feat_dim 5 / 24 | `scripts/gate12_5_localization_ablation.py`; dims confirmed in `evals/reports/gate12_5-localization-v1.txt` / `-v2.txt` headers |
| RULE definition (either endpoint oper-down) | `rule_score_fn`, `scripts/gate12_5_localization_ablation.py` |
| MLP hyperparams (64,32 / alpha 1e-2 / max_iter 2000 / random_state 0 / StandardScaler / robust-z relative features) | `fit_mlp`, `link_row`, `scripts/gate12_5_localization_ablation.py` |
| GNN hyperparams (hid 32, 2 conv, head Linear(2*hid,1), Adam lr 1e-2 wd 1e-3, 120 epochs, BCEWithLogits, mean agg, fabric + same-device edges, 16 nodes) | `GNN`, `fit_gnn`, `load`, `scripts/gate12_5_localization_ablation.py` |
| RULE per-class AUROC/top-1 + CIs | `evals/reports/gate12_5-localization-v1.txt` |
| MLP v1 / v2 per-class AUROC/top-1 + CIs | `evals/reports/gate12_5-localization-v1.txt`, `gate12_5-localization-v2.txt` |
| GNN v1 / v2 per-class AUROC/top-1 + CIs | `evals/reports/gate12_5-localization-v1.txt`, `gate12_5-localization-v2.txt` |
| Cross-model summary AUROC table (v3) | `evals/reports/localization-v3.txt` |
| GNN-impaired CV resolution (0.721 → 0.802; MLP 0.872) | `evals/reports/gate12_5-localization-cv.txt` |
| Detector ensemble structure + `DetectorConfig` defaults | `src/closcall/sensors/detection.py` |
| Detection frozen config (ewma_z 3.0 / cusum_h 4.0 / fsm_persistence 2 / horizon_s 60.0), recall/precision/F1/latency, per-class recall, CI method | `evals/reports/gate12_5-detection-v3.txt` |
