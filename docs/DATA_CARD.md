# ClosCall v3 Evaluation Corpus — Data Card

> Gate 13 (packaging/handoff) release deliverable. Every number and hash in this card is sourced
> from the immutable manifest, a study artifact it content-binds, or a live DB query — none are
> hand-estimated. Sources for each numeric claim are listed at the end. Do not edit the sourced
> values by hand; regenerate from the manifest.

## Immutable run anchor

- **Dataset kind:** `gate12_5-corpus-v3`
- **Immutable run id (manifest hash):** `dd8def51705710fa4de39cfed1a22d49929c9916ae51114ffd91feb0f2975e98`
- **Source run id:** `gate8-full-corpus-v3` (collected under traffic load, fabric-wide capture)
- **Manifest file:** `artifacts/manifests/gate12_5-dataset-v3.json`
- **Code revision:** `8dd27542a42426ace439af0c3a9fd1e34fde1c2e`
- **Split manifest hash:** `bd3070efaf4684f766f9e4a5997753bd3072d6f2c3ee1edf0ca6808dabc1860d` (location-inductive)
- **Master seed:** `1337`

This card describes ONE immutable benchmark version. The prior v2 anchor (`gate9-dataset.json`,
traffic-free) is retained unchanged in the artifact trail; v3 is a new benchmark version, not an
edit of the old one (Bible §16: old results remain immutable).

## 1. Summary

ClosCall v3 is a lab corpus of **312 settled network-fault incidents** collected on a containerlab
2-spine / 4-leaf SR Linux Clos fabric, each incident captured **under synthetic traffic load** with
**fabric-wide telemetry** (all 16 fabric-link endpoints observed per incident, not just the faulted
link). It supports two studies: single-interface **detection** (classical ensemble) and 8-candidate
link **localization** (rule vs MLP vs GNN, with a v1→v2 feature ablation).

The corpus exists to draw one precise line: classical single-interface counter detection is blind to
"gray" (sub-oper-down) faults even under load, while relational/temporal learned localization
recovers exactly those faults. See §6 and `docs/RESULTS.md`.

## 2. Provenance

- **Testbed:** containerlab topology `closcall-2s4l` — 2 spines (`spine1`, `spine2`), 4 leaves
  (`leaf1`–`leaf4`), 4 hosts. Fixed nominal per-link capacity 10 Gbps; base MTU 1500. The fabric
  (`lab/fabric.yaml`) is the only hand-authored source of truth; all addressing/interfaces are
  generated from it deterministically.
- **NOS image (srlinux):** `sha256:f711ddadbca870996793ac9bb3fccb950aa2c6a906da64a304c5274a2c2dceee`
- **Telemetry (gnmic):** `sha256:9538f93a9a85e996d0ad5f7c523835e874557be84b8d279c2a51d2f092b24c7e`
- **Metrics (prometheus):** `sha256:76947e7ef22f8a698fc638f706685909be425dbe09bd7a2cd7aca849f79b5f64`
- **Store (postgres):** `sha256:ad2e18408bf447f62092a8a5259e7df10505c5a0360bd1a1853ac8b8b0763da2`
- **Topology hash:** `1f9ea4a7da6f6e9a2faf690356fa5cabc761237a0a6c06f716831885362d34c2`
- **Config hash (fabric.yaml):** `866969f36c7c465ea7bb8b349a061c2a97605457f49ce4d96edbbe348668c4dc`
- **Feature schema hash:** `35f6e540b9928d525c4d3d9266e3a5d0a5c0f4c25a6e448ae1811d0d6caaad7a`
- **Graph schema hash:** `5f3c24c11b58b8f59bfd0e01b511fa4f7f6cee1bb38904799eb2679593f65b66`
- **Dependency lock hash (uv.lock):** `db2d2508ed4fbfa56edf9a3972eaffe2cde51c1d326ad90e46d3d54a7a4185f8`
- **Master seed:** `1337` (traffic seed and fault seed both derive from it, per incident).

**Collection loop (per incident, `scripts/corpus_run_v3.py`):** write ground truth → start
background all-to-all traffic (`TrafficProfile` collective_base, 4 streams/flow, 30 Mbps target,
seed 1337) → inject the fault after a 3 s ramp → hold the causal window → capture the target-link
window (the label) plus every fabric-link endpoint (for the GNN) → clear the fault → stop traffic →
verify the lab is clean (target iface oper-up, no leftover `netem`/`tbf` qdisc) → commit. If fault
onset was not verified or the lab did not return clean, the incident is **quarantined** (§3).

**Windows:** blunt-fault capture window = 25 s; gray-fault capture window = 40 s (longer to let the
subtle signal accrue). This class-correlated length is exactly what the §10.3 detection guard
truncates away (§5). Provenance is bound by a content-hash roll-up over the sorted window files:
`corpus_windows_rollup = fdf73abef8697ecce9b51d07541d98eaf513006ccf82a30e7403084ee2242fdd (4992 windows)`.
4992 = 312 incidents × 16 fabric-link endpoints (verified: 4992 parquet files on disk).

## 3. Composition

**Corpus = 312 settled incidents.** Per fault class (all settled; verified by DB query):

| fault class | kind | settled |
|---|---|---|
| `admin_shutdown` | blunt | 52 |
| `carrier_loss` | blunt | 52 |
| `intermittent_link` | blunt | 52 |
| `rate_limited_uplink` | gray | 52 |
| `impaired_link` | gray | 52 |
| `healthy_control` | control | 52 |
| **total** | | **312** |

- **Fault taxonomy:** 5 fault classes + 1 healthy control. "Blunt" faults
  (`admin_shutdown`, `carrier_loss`, `intermittent_link`) drive the link oper-down and leave large
  device-counter signatures. "Gray" faults (`rate_limited_uplink`, `impaired_link`) are `tc`-based
  rate/impairment faults that keep the link oper-up and only perturb throughput/loss under load.
  `healthy_control` is a no-fault window used to measure false positives and to prove no
  position/localization leakage.
- **Strata:** each incident is stratified by (fault class × leaf/`shard_key`) = 6 × 4 = 24 cells,
  filled to 13 per cell (312 / 24 = 13). Per-leaf: 78 settled on each of leaf1–leaf4.
- **Healthy controls:** 52 (13 per leaf), one of the 6 classes above.

**Quarantine (exclusions).** Quarantine happens when fault onset could not be verified OR the lab
did not return to a verified-clean state after the incident — such incidents are never admitted to
the corpus and their captured windows are deleted. The manifest excludes exactly 2 quarantined
incidents (both `admin_shutdown`):
- `07b5f13b-badf-4e78-ac71-e20a55b343e7` (leaf1)
- `2b2c18de-77c2-429e-af6a-ab6293e4a252` (leaf2)

**DB row accounting (verified):** the `gate8-full-corpus-v3` campaign holds 315 fault-injection
rows total = 312 settled (the corpus) + 2 quarantined (excluded above) + 1 stale `injecting` row
(`6cac8258-d211-47cc-8388-b3ccb9a5f8c2`, admin_shutdown/leaf3) that is an incomplete record, NOT
part of the corpus and NOT a manifest exclusion. Only the 312 settled incidents constitute the
dataset.

## 4. Splits — location-inductive

Protocol: **`location-inductive`** (`src/closcall/datasets/splits.py`, version 1). Incidents are
assigned to disjoint train/validation/test groups by fault **location** (the target physical link's
leaf):

| leaf | split |
|---|---|
| leaf1 | train |
| leaf2 | validation |
| leaf3 | test |
| leaf4 | test |

- **train = leaf1**, **validation = leaf2**, **test = leaf3 + leaf4** (156 fit incidents,
  156 test incidents). Scalers/baselines/thresholds are fit on train+validation only; test is
  scored only after selection freezes.
- **What disjointness it guarantees:** each physical link belongs to exactly one leaf, so the
  splits are **physical-link-disjoint by construction** (invariant E06, enforced with a raise). The
  assembler additionally enforces **repeats-together** — incidents sharing a seed-family or
  campaign-batch may not straddle splits. Because different splits use different physical links, they
  observe **disjoint telemetry series**, so no capture window can straddle a split boundary: for a
  location-inductive split, link-disjointness IS the purge guarantee. A purge gap
  (lookback+persistence+cooldown) is recorded for provenance but is not needed to separate these
  groups.
- **Guaranteed disjoint across splits:** physical link, leaf/location, incident, and (via
  repeats-together) seed-family and campaign-batch. Telemetry series are disjoint as a consequence.
- **Why:** to prevent **location leakage** — a model must localize faults on **leaves it never saw
  in training**. Test leaves (leaf3, leaf4) never appear in train/validation, so a test score
  reflects generalization to unseen locations, not memorization of a leaf's fingerprint. Test
  membership was fixed (pre-registered) before any results existed.

## 5. Leakage protections

- **§10.3 window-truncation guard (R28).** The collector uses a longer window for gray faults (40 s)
  than for blunt faults (25 s), so raw window *length* is fault-class-correlated. Detecting off that
  length would be incident-duration leakage. The detection eval therefore truncates **every** incident
  to a common `EVAL_WINDOW_S = 25.0 s` window before scoring
  (`scripts/evaluate_sensors_v3.py`, `scripts/evaluate_sensors.py`). Without this fix gray faults
  falsely scored 52/52; with it, detection must use signal, not duration.
- **Strictly-causal features (§10.3).** For a decision time `as_of_at`, the §9.2 feature builder
  reads only samples with `event_time ∈ [as_of_at − W, as_of_at]` — nothing after `as_of_at`. A
  fixed `FORBIDDEN_FEATURE_COLUMNS` set (t_clear, t_settled, incident_duration, ground truth, label,
  scenario key, split answer) may never enter a feature. Ground truth is joined only at scoring
  time, never used as input.
- **No position/localization leakage.** `healthy_control` localizes at chance (AUROC ~0.50) for
  every method — evidence there is no manufactured localization signal or leaf-position leakage.

## 6. Known limitations and intended use

- **Lab corpus, not production traffic.** Signals come from a containerlab SR Linux fabric under a
  synthetic all-to-all traffic profile; the veth links enforce no real hardware capacity, so
  `util_ratio` is a normalized-throughput signal, not hardware utilization. The fault signal lives
  in the rates. Do not read absolute magnitudes as production numbers.
- **Gray faults are genuinely subtle — and a detection blind spot.** The classical single-interface
  ensemble (oper-state FSM + robust-EWMA/z + CUSUM) detects all blunt faults (52/52 each) and is
  blind to both gray faults (0/52 each), even under load: test recall 0.60 (78/130), precision 1.00,
  F1 0.75, FP/healthy 0.00. This is a structural property of single-interface absolute detection,
  reported as a finding, not hidden.
- **Localization recovers gray faults — with an honest weak spot.** Over 8 fabric-link candidates
  (chance top-1 = 0.125), the oper-state rule is at chance on gray faults (AUROC 0.500 — the link
  stays oper-up), while MLP/GNN models lift gray-fault localization AUROC to ~0.91 with temporal
  features. Gray exact-link top-1 remains the honest weak spot (e.g. impaired_link GNN.v2 top-1
  0.462). Full tables, CIs, and the leave-one-leaf-out CV supplement are in
  `evals/reports/gate12_5-evaluation.md` and `docs/RESULTS.md`.
- **Intended use:** benchmarking detection/localization/reasoning methods against a provenance-bound,
  leakage-guarded lab corpus with pre-registered splits. Not intended as a production detector, a
  capacity model, or an external (NIKA) result — the internal metrics are never presented as NIKA
  validation.

## 7. Regeneration

From the manifest's `creation_command`:

```
make corpus (v3, under load, fabric-wide) \
  -> make evaluate-sensors-v3 \
  -> make evaluate-localization \
  -> uv run python scripts/emit_manifest_v3.py
```

The final step re-emits `artifacts/manifests/gate12_5-dataset-v3.json`; a faithful regeneration
reproduces the manifest hash above. Reports regenerate with `make reports-v3` and refuse to run
without the immutable manifest run id.

---

## Source ledger (where each numeric claim came from)

- **All hashes, digests, seed, exclusions, source run id, creation command, config/feature/graph/
  dependency-lock hashes, `corpus_windows_rollup (4992 windows)`:** `artifacts/manifests/gate12_5-dataset-v3.json`.
- **Per-class settled counts (52 each × 6), total 312 settled, 2 quarantined, 1 stale injecting,
  quarantine IDs, per-leaf 78:** live DB queries against `evaluation.campaigns` /
  `evaluation.fault_injections` for `campaign_key='gate8-full-corpus-v3'`.
- **4992 = 312 × 16 window files:** `find data/raw_telemetry/campaign=gate8-full-corpus-v3 -name '*.parquet'` (4992) and the manifest roll-up.
- **Collection loop, traffic profile, blunt=25 s / gray=40 s windows, quarantine rule, 16-endpoint
  fabric-wide capture:** `scripts/corpus_run_v3.py`.
- **Split policy, invariants (E06 link-disjoint, repeats-together, purge), leaf→split map:**
  `src/closcall/datasets/splits.py`.
- **§10.3 truncation guard `EVAL_WINDOW_S = 25.0`, "without this fix gray faults falsely scored
  52/52":** `scripts/evaluate_sensors_v3.py`, `scripts/evaluate_sensors.py`.
- **Strictly-causal feature rule and `FORBIDDEN_FEATURE_COLUMNS`:** `src/closcall/datasets/features.py`.
- **Detection metrics (recall 0.60, 78/130, precision 1.00, F1 0.75, FP/healthy 0.00, per-class
  52/52 & 0/52):** `evals/reports/gate12_5-detection-v3.txt`.
- **Localization AUROC/top-1 tables, 8 candidates, chance top-1 0.125, gray weak spot:**
  `evals/reports/localization-v3.txt` and `evals/reports/gate12_5-evaluation.md`.
- **Fabric composition (2 spines / 4 leaves / 4 hosts, 10 Gbps, MTU 1500):** `lab/fabric.yaml`.
