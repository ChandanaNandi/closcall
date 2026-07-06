"""The build journey: Gates 0-14, what each built, and where its evidence lives.

Descriptive documentation (like the operator guide), sourced from the Canonical Execution Bible
gate definitions and the per-gate status notes in evals/reports/. Measured RESULTS are not typed
here — the dashboard parses those from the content-hashed artifacts; each gate instead points at
its evidence (artifact, module, or test) so every claim remains checkable.
"""

from __future__ import annotations

from dataclasses import dataclass

# phase -> validated accent (see charts.py; 4-hue set passed the dataviz six checks)
PHASES = {
    "foundation": ("Foundation", "var(--s-mlp)"),
    "experiment": ("Experiment", "var(--s-gnn)"),
    "science": ("Science", "var(--s-amber)"),
    "delivery": ("Safety & delivery", "var(--s-violet)"),
}


@dataclass(frozen=True)
class Gate:
    num: str
    title: str
    phase: str
    built: str  # what this gate produced (1-2 sentences)
    evidence: tuple[str, ...]  # artifacts / modules / tests backing it


GATES: tuple[Gate, ...] = (
    Gate(
        "0",
        "Authority & threat model",
        "foundation",
        "Wrote down what the system defends against and — just as loudly — what it does not: "
        "single-operator lab, Docker VM boundary, no same-host adversary claim.",
        ("docs/threat-model.md", "ADR-002 runtime boundary"),
    ),
    Gate(
        "1",
        "Repository & environment",
        "foundation",
        "Reproducible toolchain: uv-locked dependencies, lint/typecheck gates, secret scanning, "
        "SBOM. Every later result runs from this pinned base.",
        ("make doctor / lint / secret-scan / sbom", "uv.lock"),
    ),
    Gate(
        "2",
        "Topology, IPAM & config rendering",
        "foundation",
        "One machine-readable fabric definition renders deterministic SR Linux configs — same "
        "input, byte-identical configs, content-hashed.",
        ("lab/fabric.yaml", "make render / fabric-validate"),
    ),
    Gate(
        "3",
        "Network feasibility",
        "foundation",
        "The 2-spine/4-leaf fabric boots for real: exact BGP sessions, clean route tables, 2-way "
        "ECMP, measured failure convergence, zero teardown residue.",
        ("gate3-run1/2.txt", "make lab-up / lab-check", "scripts/b09-b12"),
    ),
    Gate(
        "4",
        "Trustworthy telemetry",
        "foundation",
        "gNMI streaming into Prometheus with timestamps preserved, counter wrap/gap golden tests, "
        "and a stale-data signal — bad telemetry blocks action instead of feeding it.",
        ("gate4-telemetry.txt", "make telemetry-check"),
    ),
    Gate(
        "5",
        "Fault framework",
        "experiment",
        "Five fault classes (3 blunt, 2 gray) plus healthy controls, injected with a write-ahead "
        "ledger, verified impairment, and quarantine on any dirty baseline.",
        ("artifacts/chaos-ledger.jsonl", "make fault-smoke"),
    ),
    Gate(
        "6",
        "Deterministic vertical slice",
        "experiment",
        "The whole pipeline end-to-end with zero ML: inject → detect → correlate (100 duplicate "
        "signals → 1 incident) → typed claim → immutable plan → approval → live executor → audit. "
        "Injector cleanup is never the remediation.",
        ("gate6-slice.txt", "make vertical-slice (runs live inside make demo)"),
    ),
    Gate(
        "7",
        "Data contracts & corpus pilot",
        "experiment",
        "PostgreSQL schemas with a hard wall: runtime roles cannot read ground truth (enforced by "
        "DB grants, not convention). Content-addressed artifacts; leakage-proof split design.",
        ("gate7-db.txt", "make db-isolation"),
    ),
    Gate(
        "8",
        "Full corpus",
        "experiment",
        "312 incidents across 24 strata — later regenerated UNDER live traffic load with "
        "fabric-wide capture (v3), the collection the whole study stands on.",
        ("data/raw_telemetry/campaign=gate8-full-corpus-v3", "make corpus-verify"),
    ),
    Gate(
        "9",
        "Sensor baselines",
        "science",
        "Classical detection ensemble (EWMA/CUSUM/FSM) frozen on train+validation only, and the "
        "oper-state localization rule — plus the R28 window-length leakage catch that kept a fake "
        "52/52 out of the results.",
        ("gate9-detection.txt", "gate9-localization.txt", "gate9-dataset.json (immutable v2)"),
    ),
    Gate(
        "10",
        "Diagnostic workflow",
        "science",
        "Typed claims checked by a deterministic verifier; the LLM proposes and can never commit. "
        "The R30 relevance gate closed a real fabrication path found by adversarial testing.",
        ("gate10-status.md", "gate10-llm.txt", "evidence/claims.py"),
    ),
    Gate(
        "11",
        "Secured HITL & executor",
        "delivery",
        "Argon2id + short-lived JWT, RBAC/CSRF/IDOR; SHA-256-immutable plans; fail-closed "
        "prechecks; audit-write-first execution; ambiguity becomes outcome_unknown, never success.",
        ("gate11-status.md", "test_auth / test_api / test_prechecks / test_rollback_audit"),
    ),
    Gate(
        "12",
        "Controlled evaluation",
        "science",
        "Every result bound to one immutable run id; the external NIKA benchmark kept strictly "
        "distinct from internal metrics (documented as not-run, not blurred in).",
        ("gate12-evaluation.md", "make reports"),
    ),
    Gate(
        "12.5",
        "Core completion — the finding",
        "science",
        "Traffic generator + v3 under-load corpus + MLP/GNN localization. The centerpiece: the "
        "rule is provably blind to gray faults (AUROC 0.500); temporal learned models recover them "
        "(~0.91). Pre-registered, CI'd, confound resolved by leaf-CV — wrong early conclusion kept "
        "visible.",
        ("gate12_5-ablation.txt", "gate12_5-preregistration.txt", "gate12_5-localization-cv.txt"),
    ),
    Gate(
        "13",
        "Packaging & handoff",
        "delivery",
        "Clean-clone demo (deploy→diagnose→remediate→teardown, no manual repair), README numbers "
        "generated from the immutable run id, limitations & negative findings published, H07 "
        "honestly downgraded (ADR-004) instead of fake-wired.",
        ("make demo", "docs/LIMITATIONS.md", "docs/TRACEABILITY.md", "ADR-004"),
    ),
    Gate(
        "14",
        "Approval UI — this application",
        "delivery",
        "The browser face on the gated flow: results dashboard (every number parsed from the "
        "hashed artifacts), incident console, approve/edit/reject driving the same executor "
        "through one shared digest gate — no side door, proven by a test that tries to open one.",
        (
            "test_ui.py::test_side_door_tampered_digest_refused_and_no_mutation",
            "ADR-005",
            "make api-smoke",
        ),
    ),
)

__all__ = ["GATES", "PHASES", "Gate"]
