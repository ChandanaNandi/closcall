# Corpus & Evaluation Pre-Registration (FROZEN before collection)

Status: frozen 2026-07-03, BEFORE any pilot corpus is collected (Bible §10.1). Exclusions,
stratum design, and split protocols are declared here first; changes after TEST freeze create a new
benchmark version (§16). This satisfies the Gate 7 exit criterion "exclusions are predeclared."

## Fault ontology (frozen)
The seven §8.2 classes, honestly named (mechanism == label; no PFC/ECN/optics claims — R23):
`admin_shutdown`, `carrier_loss`, `intermittent_link`, `rate_limited_uplink`, `impaired_link`,
`healthy_control` (paired negative), `telemetry_gap`. Every injection is `simulated: true` (§2.12).

## Eligible link candidates
Physical fabric links only (leaf↔spine and leaf↔host); management interfaces are never fault
targets. Root cause is a physical-link candidate (§4.2).

## Stratum design
Balanced across {fault_class × fault_location × traffic_load × severity}, each stratum paired with a
healthy/hard-negative control (high utilization, no impairment). `>=300 incidents` is an operational
target, NOT a statistical design by itself (§10.1); minimum independent incidents per stratum are
set from the desired CI width at collection time and recorded in the campaign manifest.

## Split protocols (frozen)
1. **Location-inductive:** disjoint physical-link groups for train/validation/test within 2s4l.
2. **Topology-size transfer:** train/validation on 2s4l; frozen 2s6l test.
3. **Operating-condition shift (optional):** held-out traffic/severity combinations.
Rule: split BEFORE windowing/preprocessing; all repeats sharing incident/seed-family/campaign-batch/
overlapping-time stay in ONE split; purge adjacent blocks by >= lookback + persistence + cooldown;
scalers/imputers/baselines/calibrators/thresholds fit on TRAIN/VALIDATION only; TEST evaluated only
after selection freezes (§10.2).

## Causal windows (frozen)
For decision time t, every feature reads only [t-W, t]. No backward interpolation, future
aggregation, t_clear, t_settled, incident duration, split, scenario key, or ground truth may enter a
feature (§10.3). Online and offline feature implementations must pass golden parity tests (E08).

## Predeclared exclusions / quarantine
An injection is EXCLUDED from the corpus (quarantined, not silently dropped) when: baseline invalid;
telemetry missing/insufficient to distinguish the fault from missing data; dirty pre-state; failed
cleanup; unsettled recovery; clock offset outside policy; or observed onset never confirmed. Quarantine
reason is recorded in `evaluation.fault_injections.quarantine_reason`.

## Provenance
Every campaign records code revision, dependency-lock hash, image/model digests, master seed, and
per-injection traffic/fault seeds (§2.10). Ground truth lives only in the `evaluation` schema and is
readable only by the evaluator role (proven: ground-truth isolation test, gate7-db.txt).
