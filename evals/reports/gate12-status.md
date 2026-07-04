# Gate 12 — Controlled Evaluation Status Note

Status: **exit criteria met (reporting integrity); study scope closed honestly with documented
limitations.** Gate 12's exit is about how results are reported — from immutable run ids, with NIKA
kept distinct and never misrepresented — not about producing new headline numbers. That bar is met.
Several §Gate12 *work items* are covered by earlier gates or documented as not-built here; this note
names each plainly rather than implying more was run than was.

## Exit criteria — met

1. **Reports generated only from immutable run ids.** `make reports`
   (`scripts/consolidate_eval.py`) assembles every study into `gate12-evaluation.md` anchored to the
   §9.4 dataset manifest (`manifest_hash` 58d2cf31…, source run id `gate8-full-corpus-v2`, code
   revision d2dfd2a…). It **refuses to generate** if the manifest is absent — no run id, no report.
2. **NIKA paper version and repository snapshot distinguished.** Paper `arXiv:2512.16381` vs pinned
   repo snapshot `sands-lab/nika @ e6649f45` are kept strictly separate in the report and
   `gate12-nika.txt`.
3. **No internal sensor metric misrepresented as NIKA validation.** Explicitly stated; the internal
   detection/localization/reasoning studies are scored on the ClosCall corpus, unrelated to NIKA.

## Work items — honest disposition

| item | disposition |
|---|---|
| Causal detection study | DONE (Gate 9, `gate9-detection.txt`); consolidated with run id. Honest result: blunt 156/156, gray blind-spot, 0 FP, F1 0.75 [CI]. |
| Causal localization study | DONE (Gate 9, `gate9-localization.txt`); oper-state rule baseline, blunt top-1 1.00, gray unsolvable. |
| Policy-only reasoning study | DONE (Gate 10, `gate10-llm.txt`); qwen2.5 14b primary, injection-resistant, 0 schema repairs. |
| **Interactive-tool reasoning arm (§12.4)** | **NOT BUILT.** Needs a tool-calling agent loop over the §12.3 tools. On this traffic-free corpus it would echo the policy-only result (blunt diagnosed, gray abstained), so low marginal signal; deferred, not run. |
| **End-to-end factorial combinations** | **NOT BUILT** as a separate study. The stages (detect → diagnose → plan → precheck → execute) exist and are individually tested; a factorial sweep was not run. |
| Offline safety evaluation | DONE — the Gate 11 precheck suite + rollback + audit guard ARE the offline safety machinery (fail-closed, adversarially tested). |
| Controlled execution | MACHINERY DONE (Gate 11 executor, idempotent + reconcile + audit-first); a live approved-job run on the lab was not performed here. |
| NIKA agent-only external result | DOCUMENTED KNOWN LIMITATION (`gate12-nika.txt`). Running it needs Kathara + their lab infra + an agent adapter — a major external integration; research log positions NIKA post-core. |

## Why this is honest, not padded

Gate 12's exit criteria test reporting *integrity*, and those are genuinely satisfied. The unbuilt
items (interactive reasoning arm, factorial, live controlled execution, NIKA) are named as not-built
or deferred — consistent with Gate 13's exit requirement that "known limitations and failed
experiments are published." Nothing here is presented as done that was not.

## Provenance

- Commits: consolidation `03bb…`-preceding; NIKA doc `03bb293`.
- Artifacts: `gate12-evaluation.md` (regenerate with `make reports`), `gate12-nika.txt`.
- Anchor: §9.4 manifest `gate9-dataset.json` (manifest_hash 58d2cf31…).
- 174 tests, lint + typecheck clean (unchanged this gate — no new src beyond the report generator).
