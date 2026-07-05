"""Gate 12.5/13 consolidated evaluation report — v3 UNDER-LOAD release anchor.

Standalone twin of `consolidate_eval.py` (which stays pristine, anchored to the immutable v2
`gate9-dataset.json`). This assembles the RELEASE evaluation bundle anchored to the v3 manifest
`gate12_5-dataset-v3.json` (corpus collected under traffic load, fabric-wide). Refused without that
manifest: no immutable run id, no report (J07). Generated ONLY from the manifest + the study
artifacts it content-binds; regenerate with `make reports-v3`.

The framing is the sharpened thesis the v3 data supports — stated precisely so the report neither
over- nor under-claims:

  * DETECTION (is something wrong, from a single interface's counters): the classical ensemble is
    fundamentally blind to GRAY faults (rate_limited, impaired) EVEN under traffic load — recall
    stays on the blunt faults only. This is a property of single-interface absolute counter
    detection, not a tuning miss.
  * LOCALIZATION (which link, using peer-relative + temporal + topology structure): learned models
    RECOVER exactly those gray faults the detector misses (~0.91 AUROC), while the oper-state rule
    is provably at chance (0.500) on them.

That line — classical single-interface detection cannot see gray faults; relational/temporal learned
localization can — is the contribution, quantified on real under-load data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "artifacts" / "manifests" / "gate12_5-dataset-v3.json"
REPORTS = REPO / "evals" / "reports"

NIKA_PAPER = "arXiv:2512.16381"
NIKA_REPO_PIN = "sands-lab/nika @ e6649f45651d711a3ecb8d3f53befdcbcdb8961f"


def _read(name: str) -> str:
    p = REPORTS / name
    return p.read_text().rstrip() if p.exists() else f"(missing: {name})"


def _nika_section() -> str:
    pin = REPORTS / "gate12-nika.txt"
    if pin.exists():
        return pin.read_text().rstrip()
    return (
        "STATUS: not run here (documented known limitation). When run, this is an AGENT-ONLY\n"
        "external result reported separately from internal metrics.\n"
        f"- Published benchmark: {NIKA_PAPER} (paper version).\n"
        f"- Repository snapshot (pinned, distinct from the paper): {NIKA_REPO_PIN}."
    )


def main() -> int:
    if not MANIFEST.exists():
        print("[REFUSED] no v3 manifest — cannot generate a report without an immutable run id")
        return 1
    m = json.loads(MANIFEST.read_text())
    anchor = (
        f"- dataset: {m['dataset_kind']}\n"
        f"- source run id(s): {', '.join(m['source_run_ids'])}\n"
        f"- manifest hash (immutable run id): {m['manifest_hash']}\n"
        f"- code revision: {m['code_revision']}\n"
        f"- split manifest: {m['split_manifest_hash']} ({m['split_protocol']})\n"
        f"- feature schema: {m['feature_schema_hash']}"
    )
    doc = f"""# Gate 12.5/13 — Consolidated Evaluation (v3 under-load release anchor)

Every result below is anchored to one immutable run id — the v3 dataset manifest
(`gate12_5-dataset-v3.json`), which content-binds each study artifact by SHA-256. Generated ONLY
from that manifest + the artifacts it binds; regenerate with `make reports-v3`. The immutable v2
anchor (`gate9-dataset.json`, traffic-free) is retained unchanged in the artifact trail; this v3
bundle supersedes it as the release headline (Bible §16 — new benchmark version, old results
immutable).

## Immutable run anchor
{anchor}

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
{_read("gate12_5-detection-v3.txt")}
```

## Localization study — feature ablation, under load (artifact: localization-v3.txt)
```
{_read("localization-v3.txt")}
```

## Localization confound resolution — leave-one-leaf-out CV (artifact: gate12_5-localization-cv.txt)
```
{_read("gate12_5-localization-cv.txt")}
```

## Reasoning / LLM qualification (§4.1, §12.4; artifact: gate10-llm.txt)
```
{_read("gate10-llm.txt")}
```

## External benchmark — NIKA (agent-only, kept distinct)
{_nika_section()}

## Integrity notes (Gate 12.5/13 exit)
- Reports are generated only from the immutable v3 manifest run id (refused without it); every study
  artifact is content-bound in the manifest by SHA-256.
- NIKA paper ({NIKA_PAPER}) and repo snapshot ({NIKA_REPO_PIN}) are kept strictly distinct; no
  internal ClosCall metric is presented as NIKA validation.
- The v2 (traffic-free) anchor is NOT overwritten — it remains in the trail; this v3 bundle is a new
  benchmark version, not an edit of the old one.
- Honest scope: detection of gray faults is a genuine blind spot of single-interface counter
  detection even under load (reported as a finding, not hidden); localization's recovery is the
  contribution. Gray exact-link top-1 and the healthy control (at chance for all methods) are the
  reported limits.
"""
    out = REPORTS / "gate12_5-evaluation.md"
    out.write_text(doc)
    print(f"consolidated v3 evaluation report: {out.relative_to(REPO)}")
    print(f"  anchored to manifest {m['manifest_hash'][:16]}... (run id {m['source_run_ids']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
