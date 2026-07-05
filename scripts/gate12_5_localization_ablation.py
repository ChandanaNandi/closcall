"""Gate 12.5 — localization ablation: oper-state RULE vs per-link MLP (§11.7) vs GNN (§11.8),
on the v3 under-load corpus, over the pre-registered location-inductive split (§10.2).

Feature version is a CLI arg and is the ONLY thing that changes between the pre-registered runs:
  v1  = frozen §9.2 aggregate contract: util_ratio, error_rate, discard_rate, sample_age_s,
        missingness_mask (preprocessor gate9-causal-features-v1). Nothing added.
  v2  = v1 + strictly-causal TEMPORAL channels per counter (per-step rate std / slope / CoV) and
        oper transition count (preprocessor gate9-causal-features-v2-temporal). Pre-registered in
        evals/reports/gate12_5-preregistration.txt with a physics rationale BEFORE this run.

Integrity: only samples with event_time <= as_of_at (= window_end) enter any feature (v1 and v2).
Models fit on train(leaf1)+validation(leaf2); TEST (leaf3+leaf4) scored once. Determinism: fixed
seeds; no Date/random in feature code.

Usage: CLOSCALL_DB_PASSWORD=... uv run python scripts/gate12_5_localization_ablation.py [v1|v2]
"""

from __future__ import annotations

import asyncio
import hashlib
import statistics
import sys
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from gate12_5_exit_check import DATA_ROOT, link_map  # noqa: E402

from closcall.datasets.features import causal_features  # noqa: E402
from closcall.datasets.graph import build_topology_graph  # noqa: E402
from closcall.datasets.splits import LOCATION_INDUCTIVE_POLICY  # noqa: E402
from closcall.datasets.telemetry_window import read_window_samples  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection  # noqa: E402
from closcall.domain.fabric import allocate, load_fabric  # noqa: E402

CAMPAIGN = "gate8-full-corpus-v3"
VERSION = sys.argv[1] if len(sys.argv) > 1 else "v1"
COUNTERS = (
    "in_octets",
    "out_octets",
    "in_error_packets",
    "out_error_packets",
    "in_discarded_packets",
    "out_discarded_packets",
)
V1_KEYS = ("util_ratio", "error_rate", "discard_rate", "sample_age_s", "missingness_mask")
BLUNT = {"admin_shutdown", "carrier_loss", "intermittent_link"}
GRAY = {"rate_limited_uplink", "impaired_link"}
ORDER = (
    "admin_shutdown",
    "carrier_loss",
    "intermittent_link",
    "rate_limited_uplink",
    "impaired_link",
    "healthy_control",
)


def preprocessor_id() -> str:
    return "gate9-causal-features-v1" if VERSION == "v1" else "gate9-causal-features-v2-temporal"


def iface_features(samples, as_of_at: float, w_seconds: float) -> tuple[list[float], bool]:
    """Per-interface feature vector for the requested version + oper-down flag. Strictly causal."""
    v1 = causal_features(samples, as_of_at=as_of_at, w_seconds=w_seconds)
    feats = [float(v1[k]) for k in V1_KEYS]
    lo = as_of_at - w_seconds
    win = [s for s in samples if lo <= s.t <= as_of_at]  # causal window (same cutoff as v1)
    oper = [s.value for s in sorted(win, key=lambda s: s.t) if s.metric == "oper_state"]
    oper_down = any(v < 0.5 for v in oper)
    if VERSION == "v2":
        by: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for s in win:
            by[s.metric].append((s.t, s.value))
        for m in COUNTERS:  # per-step rate std / slope / CoV (temporal structure v1 discards)
            pts = sorted(by.get(m, []))
            rates = [
                max(0.0, v1_ - v0) / max(t1 - t0, 1e-3) for (t0, v0), (t1, v1_) in pairwise(pts)
            ]
            if len(rates) >= 2:
                a = np.array(rates)
                slope = float(np.polyfit(np.arange(len(a)), a, 1)[0])
                feats += [float(a.std()), slope, float(a.std() / (a.mean() + 1.0))]
            else:
                feats += [0.0, 0.0, 0.0]
        transitions = sum(1 for x, y in pairwise(oper) if x != y)
        feats.append(float(transitions))
    return feats, oper_down


async def load():
    lmap = link_map()
    graph = build_topology_graph(allocate(load_fabric("lab/fabric.yaml")))
    fabric_links = {
        "|".join(sorted(lk.endpoints)): sorted(lk.endpoints)
        for lk in graph.candidate_links
        if lk.kind == "fabric"
    }
    node_ids = sorted({e for eps in fabric_links.values() for e in eps})  # 16 interfaces
    nidx = {n: i for i, n in enumerate(node_ids)}
    dev = {n: n.split(":", 1)[0] for n in node_ids}
    # adjacency: fabric-link edges (cross-device) + same-device edges (co-located interfaces)
    edges = set()
    for a, b in fabric_links.values():
        edges.add((nidx[a], nidx[b]))
        edges.add((nidx[b], nidx[a]))
    for a in node_ids:
        for b in node_ids:
            if a != b and dev[a] == dev[b]:
                edges.add((nidx[a], nidx[b]))
    edge_index = torch.tensor(sorted(edges), dtype=torch.long).t().contiguous()

    Session = make_sessionmaker()
    async with Session() as s:
        cid = (
            await s.execute(select(EvalCampaign.id).where(EvalCampaign.campaign_key == CAMPAIGN))
        ).scalar_one()
        injs = (
            await s.execute(
                select(
                    EvalFaultInjection.id,
                    EvalFaultInjection.fault_class,
                    EvalFaultInjection.shard_key,
                    EvalFaultInjection.target_json,
                ).where(
                    EvalFaultInjection.status == "settled", EvalFaultInjection.campaign_id == cid
                )
            )
        ).all()
    files = list(DATA_ROOT.rglob("incident-*--*.parquet"))
    by_inc = defaultdict(list)
    for f in files:
        by_inc[f.name[len("incident-") :].split("--", 1)[0]].append(f)

    incidents = []
    for i in injs:
        tlid = lmap.get(i.target_json["link"])
        node_feat: dict[str, list[float]] = {}
        node_down: dict[str, bool] = {}
        for f in by_inc.get(str(i.id), []):
            iid = (
                f.name[len("incident-") :]
                .rsplit(".", 1)[0]
                .split("--", 1)[1]
                .replace("-ethernet-1_", ":ethernet-1/")
            )
            if iid not in nidx:
                continue
            sm = read_window_samples(f)
            if not sm:
                continue
            as_of = max(s.t for s in sm)
            w = as_of - min(s.t for s in sm)
            node_feat[iid], node_down[iid] = iface_features(sm, as_of, w)
        if len(node_feat) != len(node_ids) or tlid not in fabric_links:
            continue
        incidents.append(
            {
                "leaf": i.shard_key,
                "fc": i.fault_class,
                "tlid": tlid,
                "split": LOCATION_INDUCTIVE_POLICY[i.shard_key],
                "node_feat": node_feat,
                "node_down": node_down,
            }
        )
    return incidents, node_ids, nidx, fabric_links, edge_index


# ---------- per-link representations ----------
def link_row(inc, fabric_links, relative: bool) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Per-link feature matrix (concat 2 endpoints) + labels. relative adds within-incident z."""
    lids = list(fabric_links)
    raw = []
    for lid in lids:
        a, b = fabric_links[lid]
        raw.append(inc["node_feat"][a] + inc["node_feat"][b])
    X = np.array(raw, dtype=float)
    if relative:
        med = np.median(X, axis=0)
        mad = np.median(np.abs(X - med), axis=0)
        X = np.hstack([X, (X - med) / (1.4826 * mad + 1e-9)])
    y = np.array([1 if lid == inc["tlid"] else 0 for lid in lids])
    return X, y, lids


# ---------- GNN ----------
class GNN(nn.Module):
    def __init__(self, in_dim, hid=32):
        super().__init__()
        self.l1 = nn.Linear(in_dim, hid)
        self.l2 = nn.Linear(hid, hid)
        self.head = nn.Linear(2 * hid, 1)  # link = concat of its 2 endpoint embeddings

    def conv(self, x, edge_index, lin):
        src, dst = edge_index
        agg = torch.zeros_like(x)
        deg = torch.zeros(x.size(0), 1)
        m = x[src]
        agg.index_add_(0, dst, m)
        deg.index_add_(0, dst, torch.ones(src.size(0), 1))
        h = lin(x + agg / deg.clamp(min=1))
        return torch.relu(h)

    def forward(self, x, edge_index, link_pairs):
        h = self.conv(x, edge_index, self.l1)
        h = self.conv(h, edge_index, self.l2)
        out = [self.head(torch.cat([h[a], h[b]])) for a, b in link_pairs]
        return torch.cat(out).flatten()


def eval_ranks(score_fn, test):
    """score_fn(inc)->dict[lid,score]; returns per-incident (fc, rank, faulted, peers)."""
    res = []
    for inc in test:
        sc = score_fn(inc)
        lids = list(sc)
        # average-rank tie handling
        tv = sc[inc["tlid"]]
        higher = sum(1 for lk in lids if sc[lk] > tv)
        tied = sum(1 for lk in lids if sc[lk] == tv)
        rank = higher + 1 + (tied - 1) / 2
        res.append((inc["fc"], rank, sc[inc["tlid"]], [sc[lk] for lk in lids if lk != inc["tlid"]]))
    return res


def auroc(pairs):
    pos = [p for _, _, p, _ in pairs]
    neg = [x for _, _, _, ns in pairs for x in ns]
    if not pos or not neg:
        return 0.5
    w = t = 0
    for p in pos:
        for n in neg:
            w += p > n
            t += p == n
    return (w + 0.5 * t) / (len(pos) * len(neg))


def boot_auroc(pairs, n=2000):
    seed, m, s = 20260704, len(pairs), []
    for _ in range(n):
        samp = []
        for _ in range(m):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            samp.append(pairs[seed % m])
        s.append(auroc(samp))
    s.sort()
    return s[int(0.025 * n)], s[int(0.975 * n)]


def per_class(rows, emit):
    emit(
        f"    {'class':<20} {'n':>3} {'top1':>6} {'top3':>6} {'MRR':>6} {'AUROC':>6} {'95% CI':>15}"
    )
    out = {}
    for c in ORDER:
        rs = [r for r in rows if r[0] == c]
        if not rs:
            continue
        ranks = [r[1] for r in rs]
        top1 = sum(rk <= 1.0 for rk in ranks) / len(rs)
        top3 = sum(rk <= 3.0 for rk in ranks) / len(rs)
        mrr = statistics.mean(1.0 / rk for rk in ranks)
        au = auroc(rs)
        lo, hi = boot_auroc(rs)
        out[c] = {"top1": top1, "auc": au, "lo": lo, "hi": hi, "n": len(rs)}
        emit(
            f"    {c:<20} {len(rs):>3} {top1:>6.3f} {top3:>6.3f} {mrr:>6.3f} "
            f"{au:>6.3f} [{lo:.3f},{hi:.3f}]"
        )
    return out


def rule_score_fn(fabric_links):
    """oper-state rule: link suspicious if either endpoint is oper-down. No fitting."""

    def score(inc):
        return {
            lid: (1.0 if (inc["node_down"][a] or inc["node_down"][b]) else 0.0)
            for lid, (a, b) in fabric_links.items()
        }

    return score


def fit_mlp(fit, fabric_links):
    """per-link MLP (§11.7): v-features raw + within-incident relative. Returns a score_fn."""
    Xtr = np.vstack([link_row(c, fabric_links, relative=True)[0] for c in fit])
    ytr = np.concatenate([link_row(c, fabric_links, relative=True)[1] for c in fit])
    scaler = StandardScaler().fit(Xtr)
    mlp = MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-2, max_iter=2000, random_state=0)
    mlp.fit(scaler.transform(Xtr), ytr)

    def score(inc):
        X, _, lids = link_row(inc, fabric_links, relative=True)
        p = mlp.predict_proba(scaler.transform(X))[:, 1]
        return dict(zip(lids, p, strict=True))

    return score


def fit_gnn(fit, node_ids, nidx, fabric_links, edge_index, dim):
    """GNN (§11.8): per-interface features + fabric-graph message passing. Returns a score_fn."""
    all_feat = np.vstack([list(c["node_feat"].values()) for c in fit])
    gs = StandardScaler().fit(all_feat)
    link_pairs = [(nidx[a], nidx[b]) for a, b in fabric_links.values()]
    lids_order = list(fabric_links)

    def to_x(inc):
        return torch.tensor(
            gs.transform(np.array([inc["node_feat"][n] for n in node_ids])), dtype=torch.float32
        )

    gnn = GNN(dim)
    opt = torch.optim.Adam(gnn.parameters(), lr=1e-2, weight_decay=1e-3)
    lossf = nn.BCEWithLogitsLoss()
    gnn.train()
    for _ep in range(120):
        opt.zero_grad()
        losses = []
        for inc in fit:
            logits = gnn(to_x(inc), edge_index, link_pairs)
            y = torch.tensor([1.0 if lid == inc["tlid"] else 0.0 for lid in lids_order])
            losses.append(lossf(logits, y))
        torch.stack(losses).mean().backward()
        opt.step()
    gnn.eval()

    def score(inc):
        with torch.no_grad():
            logits = gnn(to_x(inc), edge_index, link_pairs)
        return dict(zip(lids_order, logits.tolist(), strict=True))

    return score


async def run_ablation(version: str = "v1") -> dict:
    global VERSION
    VERSION = version
    torch.manual_seed(0)
    np.random.seed(0)
    incidents, node_ids, nidx, fabric_links, edge_index = await load()
    fit = [c for c in incidents if c["split"] in ("train", "validation")]
    test = [c for c in incidents if c["split"] == "test"]
    out_lines = []

    def emit(s=""):
        out_lines.append(s)
        print(s)

    emit("=" * 76)
    emit(f"GATE 12.5 — LOCALIZATION ABLATION  [features={VERSION}: {preprocessor_id()}]")
    emit("=" * 76)
    dim = len(next(iter(incidents[0]["node_feat"].values())))
    emit(
        f"corpus={CAMPAIGN}  fit(train+val leaf1,2)={len(fit)}  test(leaf3,4)={len(test)}  "
        f"iface_feat_dim={dim}  8 fabric-link candidates (chance top1=0.125)"
    )
    ph = hashlib.sha256(preprocessor_id().encode()).hexdigest()[:12]
    emit(f"preprocessor={preprocessor_id()} (id-hash {ph})")
    emit("")

    # ---- 1. RULE: oper-state (either endpoint down in window) ----
    emit("[RULE] oper-state (link down if either endpoint oper-down in window):")
    rule_out = per_class(eval_ranks(rule_score_fn(fabric_links), test), emit)
    emit("")

    # ---- 2. per-link MLP (§11.7): per-link v-features + within-incident relative ----
    mlp_score = fit_mlp(fit, fabric_links)
    emit("[MLP §11.7] per-link, v-features (raw + within-incident relative), no graph:")
    mlp_out = per_class(eval_ranks(mlp_score, test), emit)
    emit("")

    # ---- 3. GNN (§11.8): per-interface node features + fabric graph, learns relational compare --
    gnn_score = fit_gnn(fit, node_ids, nidx, fabric_links, edge_index, dim)
    emit("[GNN §11.8] per-interface v-features + fabric graph message passing:")
    gnn_out = per_class(eval_ranks(gnn_score, test), emit)
    emit("")

    # ---- summary: gray-fault AUROC, the headline comparison ----
    emit("[SUMMARY] gray-fault localization AUROC (test) — the headline the ablation turns on:")
    emit(f"    {'class':<20} {'rule':>16} {'MLP':>16} {'GNN':>16}")

    def cell(o, c):
        return f"{o[c]['auc']:.3f}[{o[c]['lo']:.2f},{o[c]['hi']:.2f}]" if c in o else "-"

    for c in ("rate_limited_uplink", "impaired_link"):
        emit(f"    {c:<20} {cell(rule_out, c):>16} {cell(mlp_out, c):>16} {cell(gnn_out, c):>16}")
    emit("=" * 76)

    rep = REPO / "evals" / "reports" / f"gate12_5-localization-{VERSION}.txt"
    rep.write_text("\n".join(out_lines) + "\n")
    print(f"\n(report -> {rep.relative_to(REPO)})")
    return {"version": VERSION, "rule": rule_out, "mlp": mlp_out, "gnn": gnn_out}


if __name__ == "__main__":
    asyncio.run(run_ablation(sys.argv[1] if len(sys.argv) > 1 else "v1"))
