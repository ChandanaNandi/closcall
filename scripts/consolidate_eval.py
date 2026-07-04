"""Gate 12 consolidated evaluation report (exit: reports only from immutable run ids).

Assembles every study result into one report ANCHORED to the immutable run id — the §9.4 dataset
manifest (its `manifest_hash` + source run id + code revision). If the manifest is missing the
report is refused: without an immutable run id there is no report (exit criterion 1). The NIKA
section keeps the published paper (arXiv) and the pinned repo snapshot strictly distinct and never
presents an internal sensor metric as NIKA validation (exit criteria 2-3).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "artifacts" / "manifests" / "gate9-dataset.json"
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
        "STATUS: not yet run (piece 4). When run, this is an AGENT-ONLY external result — our\n"
        "diagnostic agent against the NIKA harness — reported separately from internal metrics.\n"
        f"- Published benchmark: {NIKA_PAPER} (paper version).\n"
        f"- Repository snapshot (pinned, distinct from the paper): {NIKA_REPO_PIN}.\n"
        "NOTE: no internal ClosCall metric above is NIKA validation; NIKA is a separate external\n"
        "harness with its own incidents and scoring."
    )


def main() -> int:
    if not MANIFEST.exists():
        print(
            "[REFUSED] no §9.4 manifest — cannot generate a report without an immutable run id"
        )
        return 1
    m = json.loads(MANIFEST.read_text())
    anchor = (
        f"- dataset: {m['dataset_kind']}\n"
        f"- source run id(s): {', '.join(m['source_run_ids'])}\n"
        f"- manifest hash (immutable run id): {m['manifest_hash']}\n"
        f"- code revision: {m['code_revision']}\n"
        f"- split manifest: {m['split_manifest_hash']}\n"
        f"- feature schema: {m['feature_schema_hash']}"
    )
    doc = f"""# Gate 12 — Consolidated Evaluation

Every result below is anchored to one immutable run id (the §9.4 dataset manifest). This report is
generated ONLY from that manifest + the study artifacts it binds; regenerate with `make reports`.

## Immutable run anchor
{anchor}

## Detection study (§10.4; artifact: gate9-detection.txt)
```
{_read("gate9-detection.txt")}
```

## Localization study (§11.6-11.7; artifact: gate9-localization.txt)
```
{_read("gate9-localization.txt")}
```

## Reasoning / LLM qualification (§4.1, §12.4; artifact: gate10-llm.txt)
```
{_read("gate10-llm.txt")}
```

## External benchmark — NIKA (agent-only)
{_nika_section()}

## Integrity notes (Gate 12 exit)
- Reports are generated only from the immutable manifest run id (refused without it).
- NIKA paper ({NIKA_PAPER}) and repo snapshot ({NIKA_REPO_PIN}) are kept distinct.
- No internal ClosCall metric is presented as NIKA validation.
- Honest scope: the corpus is traffic-free, so gray faults are a documented detection blind spot and
  localization is oper-state-driven (R23/R29); neural TS/MLP/GNN were not built as they cannot beat
  the oper-state baseline on this corpus (§11).
"""
    out = REPORTS / "gate12-evaluation.md"
    out.write_text(doc)
    print(f"consolidated evaluation report: {out.relative_to(REPO)}")
    print(f"  anchored to manifest {m['manifest_hash'][:16]}... (run id {m['source_run_ids']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
