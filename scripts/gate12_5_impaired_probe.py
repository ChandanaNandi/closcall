"""Gate 12.5 — quick learned-model probe for impaired_link (the one class the hand detector left
at chance, AUROC 0.545). Question: does a model with the FULL per-endpoint time-series (not the
window-aggregate maxes the hand rule used) localize the faulted link above chance on HELD-OUT leaves?

Design (honest, leakage-guarded):
  - features: per endpoint, per counter, the rate-sample series -> mean/std/min/max/last/slope/CoV;
    oper-state -> frac_up + #transitions. Two endpoints per link concatenated.
  - localization is RELATIONAL, so features are peer-normalized WITHIN each incident (z vs the 8 links).
  - LEAVE-ONE-LEAF-OUT CV: train on 3 leaves' incidents, test on the held-out leaf. The model cannot
    memorize link position. Pooled held-out predictions -> AUROC (faulted vs peer) + top1 + bootstrap CI.
  - baselines: logistic regression (linear floor) and the hand detector's 0.545.

Usage: CLOSCALL_DB_PASSWORD=... uv run python scripts/gate12_5_impaired_probe.py [fault_class]
"""  # noqa: E501

from __future__ import annotations

import asyncio
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from gate12_5_exit_check import DATA_ROOT, link_map  # noqa: E402

from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection  # noqa: E402

CAMPAIGN = "gate8-full-corpus-v3"
FAULT = sys.argv[1] if len(sys.argv) > 1 else "impaired_link"
COUNTERS = (
    "in_octets",
    "out_octets",
    "in_error_packets",
    "out_error_packets",
    "in_discarded_packets",
    "out_discarded_packets",
)


def endpoint_ts_features(path: Path) -> list[float]:
    """Rich time-series features for one endpoint window."""
    t = pq.ParquetFile(path).read().to_pydict()  # type: ignore[no-untyped-call]
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for et, metric, val in zip(t["event_time"], t["metric"], t["value"], strict=True):
        series[metric].append((et.timestamp(), float(val)))

    feats: list[float] = []
    for m in COUNTERS:
        pts = sorted(series.get(m, []))
        # per-step rate samples (counter differences / dt), reset-guarded
        rates: list[float] = []
        for (t0, v0), (t1, v1) in zip(pts, pts[1:], strict=False):  # noqa: RUF007
            dt = max(t1 - t0, 1e-3)
            rates.append(max(0.0, v1 - v0) / dt)
        if rates:
            arr = np.array(rates)
            slope = float(np.polyfit(np.arange(len(arr)), arr, 1)[0]) if len(arr) > 1 else 0.0
            mean = float(arr.mean())
            feats += [
                mean,
                float(arr.std()),
                float(arr.min()),
                float(arr.max()),
                float(arr[-1]),
                slope,
                float(arr.std() / (mean + 1.0)),
            ]
        else:
            feats += [0.0] * 7
    oper = [v for _, v in sorted(series.get("oper_state", []))]
    frac_up = float(np.mean(oper)) if oper else 1.0
    flaps = sum(1 for a, b in zip(oper, oper[1:], strict=False) if a != b)  # noqa: RUF007
    feats += [frac_up, float(flaps)]
    return feats


async def load() -> tuple[list, list]:
    Session = make_sessionmaker()
    async with Session() as s:
        cid = (
            await s.execute(select(EvalCampaign.id).where(EvalCampaign.campaign_key == CAMPAIGN))
        ).scalar_one()
        injs = (
            await s.execute(
                select(
                    EvalFaultInjection.id,
                    EvalFaultInjection.target_json,
                    EvalFaultInjection.shard_key,
                ).where(
                    EvalFaultInjection.status == "settled",
                    EvalFaultInjection.fault_class == FAULT,
                    EvalFaultInjection.campaign_id == cid,
                )
            )
        ).all()
    lmap = link_map()
    files = list(DATA_ROOT.rglob("incident-*--*.parquet"))
    by_inc: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_inc[f.name[len("incident-") :].split("--", 1)[0]].append(f)

    incidents = []  # (leaf, X[8,F], y[8])
    for i in injs:
        tlid = lmap.get(i.target_json["link"])
        link_ep_feats: dict[str, dict[str, list[float]]] = defaultdict(dict)
        for f in by_inc.get(str(i.id), []):
            iid = (
                f.name[len("incident-") :]
                .rsplit(".", 1)[0]
                .split("--", 1)[1]
                .replace("-ethernet-1_", ":ethernet-1/")
            )
            lid = lmap.get(iid)
            if lid is None:
                continue
            link_ep_feats[lid][iid] = endpoint_ts_features(f)
        rows, labels, lids = [], [], []
        for lid, eps in link_ep_feats.items():
            # concat the link's two endpoints (sorted for a stable order)
            vec = [x for iid in sorted(eps) for x in eps[iid]]
            rows.append(vec)
            labels.append(1 if lid == tlid else 0)
            lids.append(lid)
        if len(rows) < 2 or sum(labels) != 1:
            continue
        X = np.array(rows, dtype=float)
        # peer-normalize WITHIN incident (relational): z vs the other links per feature
        med = np.median(X, axis=0)
        mad = np.median(np.abs(X - med), axis=0)
        Xn = (X - med) / (1.4826 * mad + 1e-9)
        Xfull = np.hstack([X, Xn])  # raw + peer-relative
        incidents.append((i.shard_key, Xfull, np.array(labels)))
    return incidents, sorted({i[0] for i in incidents})


def evaluate(incidents, leaves, model_fn):
    """Leave-one-leaf-out CV. Returns pooled held-out (per-incident faulted rank, faulted score, peer scores)."""  # noqa: E501
    ranks, auc_pairs = [], []
    for held in leaves:
        tr = [c for c in incidents if c[0] != held]
        te = [c for c in incidents if c[0] == held]
        if not tr or not te:
            continue
        Xtr = np.vstack([c[1] for c in tr])
        ytr = np.concatenate([c[2] for c in tr])
        scaler = StandardScaler().fit(Xtr)
        clf = model_fn()
        clf.fit(scaler.transform(Xtr), ytr)
        for _held_leaf, X, y in te:
            p = clf.predict_proba(scaler.transform(X))[:, 1]
            order = np.argsort(-p)
            faulted_idx = int(np.argmax(y))
            rank = int(np.where(order == faulted_idx)[0][0]) + 1
            ranks.append(rank)
            auc_pairs.append(
                (float(p[faulted_idx]), [float(v) for k, v in enumerate(p) if k != faulted_idx])
            )
    return ranks, auc_pairs


def auroc(pairs) -> float:
    pos = [p for p, _ in pairs]
    neg = [x for _, ns in pairs for x in ns]
    if not pos or not neg:
        return 0.5
    wins = ties = 0
    for p in pos:
        for n in neg:
            wins += p > n
            ties += p == n
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def boot(pairs, n=2000):
    seed, m, s = 424242, len(pairs), []
    for _ in range(n):
        samp = []
        for _ in range(m):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            samp.append(pairs[seed % m])
        s.append(auroc(samp))
    s.sort()
    return s[int(0.025 * n)], s[int(0.975 * n)]


async def main() -> int:
    incidents, leaves = await load()
    print(f"=== impaired-probe: {FAULT} ===")
    print(f"incidents={len(incidents)}  leaves={leaves}  features/link={incidents[0][1].shape[1]}")
    n_links = len(incidents[0][2])
    print(f"chance: top1={1 / n_links:.3f}, AUROC=0.500, hand-detector AUROC=0.545\n")
    for name, fn in [
        ("logistic", lambda: LogisticRegression(max_iter=2000, C=0.5)),
        (
            "mlp",
            lambda: MLPClassifier(
                hidden_layer_sizes=(64, 32), max_iter=1500, alpha=1e-2, random_state=0
            ),
        ),
    ]:
        ranks, pairs = evaluate(incidents, leaves, fn)
        auc = auroc(pairs)
        lo, hi = boot(pairs)
        top1 = sum(1 for r in ranks if r == 1) / len(ranks)
        top2 = sum(1 for r in ranks if r <= 2) / len(ranks)
        print(
            f"{name:<9} held-out AUROC={auc:.3f} [{lo:.3f},{hi:.3f}]  "
            f"top1={top1:.3f} top2={top2:.3f} mean_rank={statistics.mean(ranks):.2f}"
        )
    print("\nverdict: model lifts impaired above chance if AUROC CI-lo > 0.5.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
