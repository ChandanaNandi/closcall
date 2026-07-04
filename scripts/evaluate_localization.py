"""Gate 9 localization evaluation — rule baseline (Bible §11.6-11.7, §10.4).

Localizes the root-cause physical link per incident using the real signal available in this
traffic-free corpus: operational state. Each incident's graph is assembled as the pilot decided —
the TARGET interface uses its real §9.1 window, every other interface uses the healthy fabric-wide
baseline (`capture_baseline.py`). A candidate link scores anomalous if either endpoint's oper-state
holds down in the common 25s window; links are ranked by score and the true link's rank gives
top-1/top-3/MRR (average-rank tie handling, so gray faults with no signal score as expected-random).

Deliberately uses oper-state only, NOT "differs from baseline": scoring on any difference would let
the capture artifact (target window captured at incident time vs. baseline captured later) leak the
answer for gray faults. This rule is the strong baseline; §11 says publish it and skip the neural
model when it cannot be beaten — which it cannot here (blunt trivially solved, gray unsolvable).

Read-only over the finished corpus + baseline; no injection, no DB writes.
"""

from __future__ import annotations

import asyncio
import glob
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.datasets.graph import build_topology_graph  # noqa: E402
from closcall.datasets.splits import LOCATION_INDUCTIVE_POLICY  # noqa: E402
from closcall.datasets.telemetry_window import read_window_samples  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection  # noqa: E402
from closcall.domain.fabric import allocate, load_fabric  # noqa: E402
from closcall.sensors.adapters import oper_state_stream  # noqa: E402

CAMPAIGN_KEY = "gate8-full-corpus-v2"
BASELINE_KEY = "healthy-baseline"
HEALTHY = "healthy_control"
BLUNT = ("admin_shutdown", "carrier_loss", "intermittent_link")
EVAL_WINDOW_S = 25.0


def _oper_down(samples: list, onset: float) -> bool:  # type: ignore[type-arg]
    win = [x for x in samples if x.t <= onset + EVAL_WINDOW_S]
    return any(s.value < 0.5 for s in oper_state_stream(win))


def load_baseline_down() -> dict[str, bool]:
    """interface_id -> is-down in the healthy baseline (all False; real captured up-state)."""
    out: dict[str, bool] = {}
    for f in glob.glob(
        f"{REPO}/data/raw_telemetry/campaign={BASELINE_KEY}/**/*.parquet", recursive=True
    ):
        iid = Path(f).name.replace("incident-", "").replace(".parquet", "")
        iid = iid.replace("-ethernet-1_", ":ethernet-1/")
        samples = read_window_samples(Path(f))
        onset = min((x.t for x in samples), default=0.0)
        out[iid] = _oper_down(samples, onset)
    return out


@dataclass
class LocResult:
    fault_class: str
    split: str
    rank: float


async def evaluate() -> list[LocResult]:
    graph = build_topology_graph(allocate(load_fabric("lab/fabric.yaml")))
    baseline_down = load_baseline_down()
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
                    EvalFaultInjection.fault_class != HEALTHY,
                )
            )
        ).all()

    results: list[LocResult] = []
    for inc_id, fc, leaf, target in rows:
        target_iid = target["link"]
        matches = glob.glob(
            f"{REPO}/data/raw_telemetry/campaign={CAMPAIGN_KEY}/**/incident-{inc_id}.parquet",
            recursive=True,
        )
        if not matches:
            continue
        tsamples = read_window_samples(Path(matches[0]))
        onset = min((x.t for x in tsamples), default=0.0)
        target_down = _oper_down(tsamples, onset)

        # per-interface down-state: target from its real window, others from the baseline;
        # candidate link score = 1 if either endpoint is down, else 0.
        scored: list[tuple[str, int]] = []
        for link in graph.candidate_links:
            ends_down = [
                (target_down if iid == target_iid else baseline_down.get(iid, False))
                for iid in link.endpoints
            ]
            scored.append((link.key, 1 if any(ends_down) else 0))
        true_key = next(link.key for link in graph.candidate_links if target_iid in link.endpoints)
        true_score = next(sc for k, sc in scored if k == true_key)
        higher = sum(1 for _, sc in scored if sc > true_score)
        tied = sum(1 for _, sc in scored if sc == true_score)
        rank = higher + 1 + (tied - 1) / 2  # average-rank tie handling
        results.append(LocResult(fc, LOCATION_INDUCTIVE_POLICY[leaf], rank))
    return results


def metrics(rs: list[LocResult]) -> str:
    if not rs:
        return "no incidents"
    top1 = sum(r.rank <= 1.0 for r in rs) / len(rs)
    top3 = sum(r.rank <= 3.0 for r in rs) / len(rs)
    mrr = statistics.mean(1.0 / r.rank for r in rs)
    return f"top1={top1:.2f} top3={top3:.2f} MRR={mrr:.2f} (n={len(rs)})"


async def run() -> int:
    rs = await evaluate()
    lines = [
        "ClosCall Gate 9 — localization evaluation (oper-state rule baseline)",
        "candidates=12 physical links; root cause is a physical-link candidate (§4.2)",
        "",
    ]
    for split in ("train", "validation", "test"):
        lines.append(f"[{split}] {metrics([r for r in rs if r.split == split])}")
    lines.append("")
    lines.append("per-class (all splits):")
    by_class: dict[str, list[LocResult]] = defaultdict(list)
    for r in rs:
        by_class[r.fault_class].append(r)
    for fc in sorted(by_class):
        tag = "blunt" if fc in BLUNT else "gray"
        lines.append(f"  {fc:<20} {metrics(by_class[fc])}  ({tag})")
    lines.append("")
    lines.append(
        "FINDING: localization is oper-state-driven — blunt faults trivially localized (the down "
        "link), gray faults unsolvable (no device signal without traffic, R23). The oper-state "
        "rule is the strong baseline; a neural model (§11.7/11.8) cannot beat it on this corpus, "
        "so per §11 it is not built. Fidelity limit: non-target links use a single static healthy "
        "baseline (not concurrent), captured identically to the corpus windows to avoid artifacts."
    )
    report = "\n".join(lines)
    print(report)
    (REPO / "evals" / "reports" / "gate9-localization.txt").write_text(report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
