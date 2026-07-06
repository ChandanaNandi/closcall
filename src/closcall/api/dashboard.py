"""Dashboard view-model: every number PARSED from the immutable v3 artifacts (J07 discipline).

Nothing here is hand-typed. The loader reads the content-bound study artifacts the v3 manifest
binds by SHA-256 (localization/detection tables, ablation header, the manifest itself) and exposes
one cached `load_dashboard()` view model for the UI's front door. A missing artifact degrades to an
explicit "(artifact missing)" state — never a fabricated number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / "evals" / "reports"
MANIFEST = REPO / "artifacts" / "manifests" / "gate12_5-dataset-v3.json"

CLASS_ORDER = (
    "admin_shutdown",
    "carrier_loss",
    "intermittent_link",
    "rate_limited_uplink",
    "impaired_link",
    "healthy_control",
)
GRAY = ("rate_limited_uplink", "impaired_link")
DISPLAY = {
    "admin_shutdown": "admin shutdown",
    "carrier_loss": "carrier loss",
    "intermittent_link": "intermittent",
    "rate_limited_uplink": "rate limited",
    "impaired_link": "impaired",
    "healthy_control": "healthy control",
}

_CI_ROW = re.compile(
    r"^\s{4}([a-z_]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
    r"\[([\d.]+),([\d.]+)\]\s*$"
)


@dataclass(frozen=True)
class ClassResult:
    name: str
    n: int
    top1: float
    auroc: float
    lo: float
    hi: float


@dataclass(frozen=True)
class DetectionClass:
    name: str
    detected: int
    total: int
    kind: str  # blunt | gray


@dataclass(frozen=True)
class Dashboard:
    ok: bool
    missing: list[str] = field(default_factory=list)
    # localization, v2 (temporal) features, per model -> per class (with CIs)
    rule: dict[str, ClassResult] = field(default_factory=dict)
    mlp: dict[str, ClassResult] = field(default_factory=dict)
    gnn: dict[str, ClassResult] = field(default_factory=dict)
    # v1 (aggregate) gray AUROC for the "signal is temporal" comparison
    mlp_v1_gray: dict[str, float] = field(default_factory=dict)
    detection: list[DetectionClass] = field(default_factory=list)
    detection_recall: str = "?"
    detection_detected: str = "?"
    incidents: str = "?"
    windows: str = "?"
    candidates: str = "?"
    manifest_hash: str = "?"
    source_run: str = "?"
    code_revision: str = "?"


def _read(name: str, missing: list[str]) -> str:
    p = REPORTS / name
    if not p.exists():
        missing.append(name)
        return ""
    return p.read_text()


def parse_ci_tables(text: str) -> dict[str, dict[str, ClassResult]]:
    """Parse the [RULE]/[MLP]/[GNN] per-class tables (n, top1, AUROC, 95% CI)."""
    out: dict[str, dict[str, ClassResult]] = {}
    section = ""
    for ln in text.splitlines():
        if ln.startswith("[RULE]"):
            section = "rule"
        elif ln.startswith("[MLP"):
            section = "mlp"
        elif ln.startswith("[GNN"):
            section = "gnn"
        elif ln.startswith("[SUMMARY]"):
            section = ""
        m = _CI_ROW.match(ln)
        if section and m:
            name, n, top1, _t3, _mrr, au, lo, hi = m.groups()
            out.setdefault(section, {})[name] = ClassResult(
                name=name,
                n=int(n),
                top1=float(top1),
                auroc=float(au),
                lo=float(lo),
                hi=float(hi),
            )
    return out


def parse_v1_gray_mlp(text: str) -> dict[str, float]:
    """From localization-v3.txt's AUROC grid: the MLP.v1 column for the gray classes."""
    out: dict[str, float] = {}
    lines = text.splitlines()
    i = next((k for k, ln in enumerate(lines) if ln.startswith("AUROC (test), per class:")), None)
    if i is None:
        return out
    for ln in lines[i + 2 :]:
        parts = ln.split()
        if len(parts) >= 6 and parts[0] in GRAY:
            out[parts[0]] = float(parts[2])  # columns: class RULE MLP.v1 MLP.v2 GNN.v1 GNN.v2
        if not ln.strip():
            break
    return out


def parse_detection(text: str) -> tuple[list[DetectionClass], str, str]:
    classes: list[DetectionClass] = []
    recall, detected = "?", "?"
    for ln in text.splitlines():
        if ln.startswith("[test]"):
            m = re.search(r"recall=([\d.]+)", ln)
            d = re.search(r"\[(\d+/\d+) faults", ln)
            recall = m.group(1) if m else "?"
            detected = d.group(1) if d else "?"
        m2 = re.match(r"^\s+([a-z_]+)\s+(\d+)/(\d+)\s+\((blunt|gray)\)", ln)
        if m2:
            classes.append(
                DetectionClass(
                    name=m2.group(1),
                    detected=int(m2.group(2)),
                    total=int(m2.group(3)),
                    kind=m2.group(4),
                )
            )
    classes.sort(key=lambda c: CLASS_ORDER.index(c.name) if c.name in CLASS_ORDER else 99)
    return classes, recall, detected


@lru_cache(maxsize=1)
def load_dashboard() -> Dashboard:
    missing: list[str] = []
    v2 = _read("gate12_5-localization-v2.txt", missing)
    loc = _read("localization-v3.txt", missing)
    det = _read("gate12_5-detection-v3.txt", missing)
    abl = _read("gate12_5-ablation.txt", missing)

    tables = parse_ci_tables(v2) if v2 else {}
    detection, recall, detected = parse_detection(det) if det else ([], "?", "?")

    incidents = "?"
    if abl:
        m = re.search(r"\((\d+) incidents", abl)
        incidents = m.group(1) if m else "?"
    candidates = "?"
    if loc:
        m = re.search(r"candidates=(\d+)", loc)
        candidates = m.group(1) if m else "?"

    manifest_hash, source_run, code_rev, windows = "?", "?", "?", "?"
    if MANIFEST.exists():
        mj = json.loads(MANIFEST.read_text())
        manifest_hash = mj.get("manifest_hash", "?")
        source_run = ", ".join(mj.get("source_run_ids", [])) or "?"
        code_rev = mj.get("code_revision", "?")
        m = re.search(
            r"\((\d+) windows\)", mj.get("content_hashes", {}).get("corpus_windows_rollup", "")
        )
        windows = m.group(1) if m else "?"
    else:
        missing.append("gate12_5-dataset-v3.json")

    return Dashboard(
        ok=not missing,
        missing=missing,
        rule=tables.get("rule", {}),
        mlp=tables.get("mlp", {}),
        gnn=tables.get("gnn", {}),
        mlp_v1_gray=parse_v1_gray_mlp(loc) if loc else {},
        detection=detection,
        detection_recall=recall,
        detection_detected=detected,
        incidents=incidents,
        windows=windows,
        candidates=candidates,
        manifest_hash=manifest_hash,
        source_run=source_run,
        code_revision=code_rev,
    )


__all__ = [
    "CLASS_ORDER",
    "DISPLAY",
    "GRAY",
    "ClassResult",
    "Dashboard",
    "DetectionClass",
    "load_dashboard",
]
