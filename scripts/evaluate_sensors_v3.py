"""Gate 12.5 / 13 detection evaluation on the v3 UNDER-LOAD corpus (Bible §11.1-11.3, §10.2, §10.4).

Re-runs the SAME frozen classical detector ensemble as `evaluate_sensors.py`, but over the v3 corpus
(gate8-full-corpus-v3, collected UNDER traffic load, fabric-wide capture). The v3 capture stores one
Parquet per fabric endpoint per incident; detection semantics are unchanged from v2 — score the
incident's own designated interface (from `target_json` node+interface, present for healthy controls
too), truncated to a common window so fault-class-correlated window length cannot leak (§10.3, R28).

Only the corpus changes (v2 traffic-free -> v3 under-load); method, freeze protocol, window guard,
CIs and seed are identical. This is a new benchmark version (§16), NOT a contract change: the v2
result in gate9-detection.txt stays immutable. Read-only over the finished corpus (DB + Parquet).

The scientific question it answers: does traffic load make the gray tc-faults (rate_limited_uplink,
impaired_link) detectable by the classical device-counter ensemble? v2 found them a blind spot with
the explicit caveat "no signal WITHOUT load" (R23). v3 tests that caveat directly.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from evaluate_sensors import (  # noqa: E402
    BLUNT,
    BOOT_N,
    BOOT_SEED,
    EVAL_WINDOW_S,
    HEALTHY,
    Incident,
    _fmt,
    bootstrap_cis,
    freeze_on_train_val,
    metrics_from_outcomes,
    outcomes,
    per_class_recall,
)

from closcall.datasets.splits import LOCATION_INDUCTIVE_POLICY  # noqa: E402
from closcall.datasets.telemetry_window import read_window_samples  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection  # noqa: E402

CAMPAIGN_KEY = "gate8-full-corpus-v3"
DATA_ROOT = REPO / "data" / "raw_telemetry" / f"campaign={CAMPAIGN_KEY}"


def target_iface_file(inc_id: str, node: str, interface: str) -> Path | None:
    """The Parquet for this incident's own designated interface (v2 single-interface semantics).

    v3 filenames encode the endpoint as `{node}-{interface_with_/->_}`, e.g. leaf3:ethernet-1/1 ->
    `incident-{id}--leaf3-ethernet-1_1.parquet`. Returns the match or None if absent.
    """
    tail = f"{node}-{interface.replace('/', '_')}"
    matches = list(DATA_ROOT.rglob(f"incident-{inc_id}--{tail}.parquet"))
    return matches[0] if matches else None


async def load_incidents() -> list[Incident]:
    Session = make_sessionmaker()
    async with Session() as s:
        cid = (
            await s.execute(
                select(EvalCampaign.id).where(EvalCampaign.campaign_key == CAMPAIGN_KEY)
            )
        ).scalar_one()
        rows = (
            await s.execute(
                select(
                    EvalFaultInjection.id,
                    EvalFaultInjection.fault_class,
                    EvalFaultInjection.shard_key,
                    EvalFaultInjection.target_json,
                ).where(
                    EvalFaultInjection.campaign_id == cid,
                    EvalFaultInjection.status == "settled",
                )
            )
        ).all()

    incidents: list[Incident] = []
    for inc_id, fc, leaf, target in rows:
        f = target_iface_file(str(inc_id), target["node"], target["interface"])
        if f is None:
            continue
        samples = read_window_samples(f)
        if not samples:
            continue
        onset = min((x.t for x in samples), default=0.0)
        # same §10.3 leakage guard: truncate every incident to a common span
        samples = [x for x in samples if x.t <= onset + EVAL_WINDOW_S]
        incidents.append(
            Incident(
                fault_class=fc,
                split=LOCATION_INDUCTIVE_POLICY[leaf],
                onset_t=onset,
                is_healthy=(fc == HEALTHY),
                samples=samples,
            )
        )
    return incidents


async def run() -> int:
    incidents = await load_incidents()
    cfg = freeze_on_train_val(incidents)
    lines = [
        "ClosCall — detection evaluation (classical ensemble) — v3 UNDER-LOAD corpus",
        f"corpus={CAMPAIGN_KEY} (traffic during every incident window; SAME method as v2, new "
        "benchmark version §16). v2 result (gate9-detection.txt) stays immutable.",
        f"frozen config (fit on TRAIN+VALIDATION): ewma_z={cfg.ewma_z} cusum_h={cfg.cusum_h} "
        f"fsm_persistence={cfg.fsm_persistence} horizon_s={cfg.horizon_s}",
        f"CIs: 95% incident-clustered bootstrap, n={BOOT_N}, seed={BOOT_SEED} (§10.4)",
        f"detection unit: the incident's own designated interface (target_json), truncated to a "
        f"common {EVAL_WINDOW_S:.0f}s window (§10.3 leakage guard, R28).",
        "",
    ]
    for split in ("train", "validation", "test"):
        sub = [i for i in incidents if i.split == split]
        outs = outcomes(sub, cfg)
        lines.append(f"[{split}] {_fmt(metrics_from_outcomes(outs), bootstrap_cis(outs))}")
    lines.append("")
    lines.append("per-class recall (all splits):")
    for fc, (d, n) in sorted(per_class_recall(incidents, cfg).items()):
        tag = "blunt" if fc in BLUNT else "gray"
        lines.append(f"  {fc:<20} {d:>2}/{n:<2}  ({tag})")
    lines.append("")
    lines.append(
        "COMPARISON TO v2 (gate9-detection.txt): v2 was traffic-free and gray faults produced no "
        "device-counter signal (0/52, R23 blind spot). This run tests whether traffic load makes "
        "the gray tc-faults detectable by the same classical ensemble."
    )
    report = "\n".join(lines)
    print(report)
    (REPO / "evals" / "reports" / "gate12_5-detection-v3.txt").write_text(report + "\n")
    print("\n(report -> evals/reports/gate12_5-detection-v3.txt)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
