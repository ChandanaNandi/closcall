"""Gate 9 detection evaluation (Bible §11.1-11.3, §10.2, §10.4).

Runs the classical detector ensemble over every incident window, freezes the detector thresholds on
TRAIN+VALIDATION only (grid search, max F1), then reports detection metrics per split and per fault
class on the frozen config — TEST scored only after selection. Honest by construction: blunt faults
(oper-state) are detectable; gray tc-based faults leave no device-counter signal without traffic
load (R23), so they surface as a documented blind spot, not hidden.

Read-only over the finished corpus (DB + §9.1 Parquet); no injection, no DB writes.
"""

from __future__ import annotations

import asyncio
import glob
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.datasets.splits import LOCATION_INDUCTIVE_POLICY  # noqa: E402
from closcall.datasets.telemetry_window import read_window_samples  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection  # noqa: E402
from closcall.sensors.detection import DetectorConfig, detect_incident  # noqa: E402

CAMPAIGN_KEY = "gate8-full-corpus-v2"
HEALTHY = "healthy_control"
BLUNT = ("admin_shutdown", "carrier_loss", "intermittent_link")
# Common evaluation window: the collector used WINDOW_GRAY_S=40 for gray faults vs 25 elsewhere, so
# window length correlates with fault class. Detecting off that length is incident_duration leakage
# (§10.3). Truncate EVERY incident to a fixed span so length cannot leak; detection must use signal.
EVAL_WINDOW_S = 25.0
BOOT_N = 2000  # bootstrap resamples for 95% CIs
BOOT_SEED = 1337  # seeded so CIs reproduce (matches campaign master_seed)


@dataclass
class Incident:
    fault_class: str
    split: str
    onset_t: float
    is_healthy: bool
    samples: list  # type: ignore[type-arg]


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
                ).where(
                    EvalFaultInjection.campaign_id == cid,
                    EvalFaultInjection.status == "settled",
                )
            )
        ).all()
    incidents: list[Incident] = []
    for inc_id, fc, leaf in rows:
        matches = glob.glob(
            f"{REPO}/data/raw_telemetry/**/incident-{inc_id}.parquet", recursive=True
        )
        if not matches:
            continue
        samples = read_window_samples(Path(matches[0]))
        onset = min((x.t for x in samples), default=0.0)
        # truncate to a common window so fault-class-correlated window length cannot leak (§10.3)
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


@dataclass
class Metrics:
    recall: float
    precision: float
    f1: float
    fp_rate: float
    latency_med: float | None
    latency_p90: float | None
    detected: int
    faults: int
    healthy_fired: int
    healthy: int


@dataclass
class Outcome:
    is_healthy: bool
    detected: bool  # fault detected within horizon (False for healthy)
    fired: bool  # healthy incident produced any alarm (False for faults)
    latency: float | None


def outcomes(incidents: list[Incident], cfg: DetectorConfig) -> list[Outcome]:
    """Per-incident detection outcome under a config — computed once, then bootstrapped over."""
    out: list[Outcome] = []
    for inc in incidents:
        res = detect_incident(inc.samples, cfg, onset_t=inc.onset_t, is_healthy=inc.is_healthy)
        hit = res.detected and not inc.is_healthy
        out.append(
            Outcome(
                is_healthy=inc.is_healthy,
                detected=hit,
                fired=(inc.is_healthy and res.false_positives > 0),
                latency=res.latency_s if hit else None,
            )
        )
    return out


def metrics_from_outcomes(outs: list[Outcome]) -> Metrics:
    detected = sum(o.detected for o in outs)
    faults = sum(not o.is_healthy for o in outs)
    healthy = sum(o.is_healthy for o in outs)
    healthy_fired = sum(o.fired for o in outs)
    recall = detected / faults if faults else 0.0
    precision = detected / (detected + healthy_fired) if (detected + healthy_fired) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fp_rate = healthy_fired / healthy if healthy else 0.0
    lat = sorted(o.latency for o in outs if o.latency is not None)
    med = statistics.median(lat) if lat else None
    p90 = lat[min(len(lat) - 1, int(0.9 * len(lat)))] if lat else None
    return Metrics(
        recall, precision, f1, fp_rate, med, p90, detected, faults, healthy_fired, healthy
    )


def score(incidents: list[Incident], cfg: DetectorConfig) -> Metrics:
    return metrics_from_outcomes(outcomes(incidents, cfg))


def bootstrap_cis(
    outs: list[Outcome], *, n_boot: int = BOOT_N, seed: int = BOOT_SEED
) -> dict[str, tuple[float, float]]:
    """95% incident-clustered bootstrap CIs (each resampling unit is one incident = one cluster)."""
    rng = random.Random(seed)
    n = len(outs)
    acc: dict[str, list[float]] = {"recall": [], "precision": [], "f1": [], "fp_rate": []}
    for _ in range(n_boot):
        sample = [outs[rng.randrange(n)] for _ in range(n)]
        m = metrics_from_outcomes(sample)
        acc["recall"].append(m.recall)
        acc["precision"].append(m.precision)
        acc["f1"].append(m.f1)
        acc["fp_rate"].append(m.fp_rate)
    lo_i, hi_i = int(0.025 * n_boot), int(0.975 * n_boot)
    return {k: (sorted(v)[lo_i], sorted(v)[hi_i]) for k, v in acc.items()}


def per_class_recall(incidents: list[Incident], cfg: DetectorConfig) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = {}
    for inc in incidents:
        if inc.is_healthy:
            continue
        d = out.setdefault(inc.fault_class, [0, 0])
        d[1] += 1
        if detect_incident(inc.samples, cfg, onset_t=inc.onset_t, is_healthy=False).detected:
            d[0] += 1
    return {k: (v[0], v[1]) for k, v in out.items()}


def freeze_on_train_val(incidents: list[Incident]) -> DetectorConfig:
    """Grid-search thresholds on TRAIN+VALIDATION only; max F1 (tie-break: fewer healthy FP)."""
    fit = [i for i in incidents if i.split in ("train", "validation")]
    best: tuple[float, int, DetectorConfig] | None = None
    for z in (3.0, 4.0, 5.0):
        for h in (4.0, 6.0, 8.0):
            for p in (2, 3):
                cfg = DetectorConfig(ewma_z=z, cusum_h=h, fsm_persistence=p)
                m = score(fit, cfg)
                key = (m.f1, -m.healthy_fired)
                if best is None or key > (best[0], -best[1]):
                    best = (m.f1, m.healthy_fired, cfg)
    assert best is not None
    return best[2]


def _fmt(m: Metrics, ci: dict[str, tuple[float, float]]) -> str:
    lat = f"{m.latency_med:.0f}/{m.latency_p90:.0f}s" if m.latency_med is not None else "n/a"

    def c(name: str) -> str:
        return f"[{ci[name][0]:.2f},{ci[name][1]:.2f}]"

    return (
        f"recall={m.recall:.2f} {c('recall')} precision={m.precision:.2f} {c('precision')} "
        f"F1={m.f1:.2f} {c('f1')} FP/healthy={m.fp_rate:.2f} {c('fp_rate')} "
        f"latency(med/p90)={lat} [{m.detected}/{m.faults} faults, "
        f"{m.healthy_fired}/{m.healthy} healthy fired]"
    )


async def run() -> int:
    incidents = await load_incidents()
    cfg = freeze_on_train_val(incidents)
    lines = [
        "ClosCall Gate 9 — detection evaluation (classical ensemble)",
        f"frozen config (fit on TRAIN+VALIDATION): ewma_z={cfg.ewma_z} cusum_h={cfg.cusum_h} "
        f"fsm_persistence={cfg.fsm_persistence} horizon_s={cfg.horizon_s}",
        f"CIs: 95% incident-clustered bootstrap, n={BOOT_N}, seed={BOOT_SEED} (§10.4)",
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
        f"METHOD: every incident truncated to a common {EVAL_WINDOW_S:.0f}s window — the collector "
        "used a longer window for gray faults, and detecting off that length is incident_duration "
        "leakage (§10.3, found R28). Without this fix gray faults falsely scored 52/52."
    )
    lines.append(
        "NOTE (R23): gray tc-faults (rate_limited_uplink, impaired_link) produce no device-counter "
        "signal without traffic load — a documented detection blind spot, not a false negative bug."
    )
    report = "\n".join(lines)
    print(report)
    (REPO / "evals" / "reports" / "gate9-detection.txt").write_text(report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
