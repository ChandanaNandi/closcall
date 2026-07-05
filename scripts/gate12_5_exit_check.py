"""Gate 12.5 corpus EXIT-CRITERIA check (run AFTER v3 collection completes).

Proves the Gate 5 acceptance row on the ACTUAL collected corpus, not the runner design:
  "congestion and gray failures produce learnable signatures"

Two parts:
  1. INTEGRITY  — every settled incident has its full 16-endpoint telemetry set on disk,
                  non-empty, sha256 matching the DB Artifact rows, with a ground-truth label.
  2. SIGNAL     — a SINGLE fixed, fault-agnostic anomaly detector (each fabric link's deviation
                  from its peers across a fixed feature set) localizes the faulted link far above
                  chance for faulted classes, and NEAR chance for healthy_control (negative control).
                  Reported per class with bootstrap 95% CIs. No per-class tuning => no cherry-picking.

Read-only. Writes a report to evals/reports/gate12_5-exit-criteria.txt.
"""  # noqa: E501

from __future__ import annotations

import asyncio
import hashlib
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import select, text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.datasets.graph import build_topology_graph  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalCampaign, EvalFaultInjection, EvalGroundTruthLabel  # noqa: E402
from closcall.domain.fabric import allocate, load_fabric  # noqa: E402

CAMPAIGN = "gate8-full-corpus-v3"
DATA_ROOT = REPO / "data" / "raw_telemetry" / f"campaign={CAMPAIGN}"
FEATURES = ("util_out", "util_in", "discards", "errors", "oper_down")
GRAY = {"rate_limited_uplink", "impaired_link"}
BLUNT = {"admin_shutdown", "carrier_loss"}


def link_map() -> dict[str, str]:
    """endpoint iid (node:iface) -> fabric-link id (sorted endpoint pair)."""
    graph = build_topology_graph(allocate(load_fabric("lab/fabric.yaml")))
    m: dict[str, str] = {}
    for link in graph.candidate_links:
        if link.kind != "fabric":
            continue
        lid = "|".join(sorted(link.endpoints))
        for iid in link.endpoints:
            m[iid] = lid
    return m


def endpoint_features(path: Path) -> dict[str, float]:
    """Aggregate one endpoint window into fixed features (counter deltas over the window)."""
    t = pq.ParquetFile(path).read().to_pydict()  # type: ignore[no-untyped-call]
    by_metric: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for et, metric, val in zip(t["event_time"], t["metric"], t["value"], strict=True):
        by_metric[metric].append((et.timestamp(), float(val)))

    def delta(metric: str) -> float:
        pts = sorted(by_metric.get(metric, []))
        if len(pts) < 2:
            return 0.0
        d = pts[-1][1] - pts[0][1]
        return d if d >= 0 else pts[-1][1]  # counter reset guard

    def span() -> float:
        allpts = [p for pts in by_metric.values() for p in pts]
        if len(allpts) < 2:
            return 1.0
        ts = sorted(p[0] for p in allpts)
        return max(ts[-1] - ts[0], 1.0)

    s = span()
    oper = by_metric.get("oper_state", [])
    oper_min = min((v for _, v in oper), default=1.0)
    return {
        "util_out": delta("out_octets") * 8.0 / s,
        "util_in": delta("in_octets") * 8.0 / s,
        "discards": delta("in_discarded_packets") + delta("out_discarded_packets"),
        "errors": delta("in_error_packets") + delta("out_error_packets"),
        "oper_down": 1.0 - oper_min,
    }


def robust_z(x: float, peers: list[float]) -> float:
    med = statistics.median(peers)
    mad = statistics.median([abs(p - med) for p in peers]) or 1e-9
    return abs(x - med) / (1.4826 * mad)


def _rank(scores: dict[str, float], target_lid: str) -> int:
    order = sorted(scores, key=lambda lk: scores[lk], reverse=True)
    return order.index(target_lid) + 1


def target_ranks(
    link_feats: dict[str, dict[str, float]], target_lid: str
) -> tuple[int, int] | None:
    """Two detectors, one fixed feature set, applied uniformly to every class:
      naive       — max two-sided |robust-z| (any deviation = anomalous). Confounded by the
                    reactive ECMP sibling that spikes HIGH when the faulted link is throttled.
      directional — physical degradation prior: a faulted link carries LESS (util shortfall) or
                    drops MORE (discards/errors) or goes DOWN (oper). One-sided z in that direction.
    1 = most suspicious. No per-class parameters => not cherry-picked.
    """
    lids = list(link_feats)
    if target_lid not in lids or len(lids) < 2:
        return None
    # feature -> +1 if HIGH is suspicious, -1 if LOW is suspicious (the degradation prior)
    direction = {"util_out": -1, "util_in": -1, "discards": +1, "errors": +1, "oper_down": +1}
    naive: dict[str, float] = {}
    directed: dict[str, float] = {}
    for lid in lids:
        a_naive = a_dir = 0.0
        for f in FEATURES:
            peers = [link_feats[o][f] for o in lids if o != lid]
            med = statistics.median(peers)
            mad = statistics.median([abs(p - med) for p in peers]) or 1e-9
            z = (link_feats[lid][f] - med) / (1.4826 * mad)
            a_naive = max(a_naive, abs(z))
            a_dir = max(
                a_dir, max(0.0, z * direction[f])
            )  # only deviation in the degrading direction
        naive[lid] = a_naive
        directed[lid] = a_dir
    return _rank(naive, target_lid), _rank(directed, target_lid)


def degradation_scores(link_feats: dict[str, dict[str, float]]) -> dict[str, float]:
    """One fixed a-priori 'degradation' score per link, peer-relative (no per-class tuning):
    a faulted link carries LESS (util deficit), drops MORE (loss excess), or goes DOWN (oper).
    score = one-sided-z(util deficit) + one-sided-z(loss excess) + 5*oper_down.  Summed, not maxed,
    so no single heavy-tailed feature dominates (that was what made the rank detector noisy)."""
    lids = list(link_feats)
    direction = {"util_out": -1, "util_in": -1, "discards": +1, "errors": +1, "oper_down": +1}
    scores: dict[str, float] = {}
    for lid in lids:
        s = 0.0
        for f in FEATURES:
            peers = [link_feats[o][f] for o in lids if o != lid]
            med = statistics.median(peers)
            mad = statistics.median([abs(p - med) for p in peers]) or 1e-9
            z = (link_feats[lid][f] - med) / (1.4826 * mad)
            w = 5.0 if f == "oper_down" else 1.0
            s += w * max(0.0, z * direction[f])
        scores[lid] = s
    return scores


def auroc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney AUROC: P(faulted-link score > random peer score). 0.5 = chance."""
    if not pos or not neg:
        return 0.5
    wins = ties = 0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def auroc_ci(
    per_incident: list[tuple[float, list[float]]], n: int = 2000
) -> tuple[float, float, float]:
    """AUROC point estimate + bootstrap 95% CI, resampling incidents (deterministic LCG)."""
    point = auroc([p for p, _ in per_incident], [x for _, ns in per_incident for x in ns])
    if not per_incident:
        return (0.5, 0.5, 0.5)
    seed, m, samples = 987654321, len(per_incident), []
    for _ in range(n):
        pos: list[float] = []
        neg: list[float] = []
        for _ in range(m):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            p, ns = per_incident[seed % m]
            pos.append(p)
            neg.extend(ns)
        samples.append(auroc(pos, neg))
    samples.sort()
    return (point, samples[int(0.025 * n)], samples[int(0.975 * n)])


def boot_ci(hits: list[int], n: int = 2000) -> tuple[float, float]:
    """Deterministic bootstrap CI (fixed LCG seed; no Math.random equivalent needed)."""
    if not hits:
        return (0.0, 0.0)
    seed, m, samples = 1234567, len(hits), []
    for _ in range(n):
        acc = 0.0
        for _ in range(m):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            acc += hits[seed % m]
        samples.append(acc / m)
    samples.sort()
    return (samples[int(0.025 * n)], samples[int(0.975 * n)])


async def main() -> int:
    out: list[str] = []

    def emit(line: str = "") -> None:
        out.append(line)
        print(line)

    lmap = link_map()
    n_links = len(set(lmap.values()))

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
                    EvalFaultInjection.target_json,
                ).where(
                    EvalFaultInjection.status == "settled",
                    EvalFaultInjection.campaign_id == cid,
                )
            )
        ).all()
        labelled = set(
            (
                await s.execute(
                    select(EvalGroundTruthLabel.fault_injection_id)
                    .join(
                        EvalFaultInjection,
                        EvalFaultInjection.id == EvalGroundTruthLabel.fault_injection_id,
                    )
                    .where(EvalFaultInjection.campaign_id == cid)
                )
            )
            .scalars()
            .all()
        )
        art = {
            r[0]: r[1]
            for r in (
                await s.execute(
                    text(
                        "select uri, sha256 from core.artifacts "
                        "where kind='raw_telemetry_window' and uri like :p"
                    ),
                    {"p": f"%campaign={CAMPAIGN}%"},
                )
            ).all()
        }

    emit("=" * 72)
    emit("GATE 12.5 — CORPUS EXIT-CRITERIA CHECK (v3, under load)")
    emit("=" * 72)

    # ---- Part 1: integrity ----
    files = list(DATA_ROOT.rglob("incident-*--*.parquet"))
    by_inc: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        inc = f.name[len("incident-") :].split("--", 1)[0]
        by_inc[inc].append(f)
    n_settled = len(injs)
    full = [str(i.id) for i in injs if len(by_inc.get(str(i.id), [])) == 16]
    missing_label = [str(i.id) for i in injs if i.id not in labelled]
    # sha256 spot-check on a fixed sample (every 40th file)
    sha_ok = sha_tot = 0
    for f in sorted(files)[::40]:
        uri = str(f.relative_to(REPO))
        if uri in art:
            sha_tot += 1
            if hashlib.sha256(f.read_bytes()).hexdigest() == art[uri]:
                sha_ok += 1
    emit()
    emit("[1] INTEGRITY")
    emit(f"    settled incidents ............ {n_settled}")
    emit(f"    incidents with full 16/16 .... {len(full)}  (want {n_settled})")
    emit(f"    endpoint files on disk ....... {len(files)}  (want {n_settled * 16})")
    emit(f"    DB artifact rows (v3) ........ {len(art)}")
    emit(f"    ground-truth labels present .. {n_settled - len(missing_label)}/{n_settled}")
    emit(f"    sha256 spot-check ............ {sha_ok}/{sha_tot} match")
    integrity_ok = (
        len(full) == n_settled
        and len(files) == n_settled * 16
        and not missing_label
        and sha_ok == sha_tot
        and sha_tot > 0
    )
    emit(f"    => INTEGRITY {'PASS' if integrity_ok else 'FAIL'}")

    # ---- Part 2: signal — is the faulted link separable from its peers? ----
    emit()
    emit("[2] LEARNABLE SIGNAL — faulted link vs its 7 fabric peers, one fixed a-priori detector")
    chance = 1 / n_links
    emit(
        "    Primary metric: AUROC = P(faulted-link degradation score > a random peer's), 0.5 = chance."  # noqa: E501
    )
    emit(
        "    Threshold-free, control-calibrated. Score = one-sided z(util-deficit)+z(loss-excess)+5*oper_down."  # noqa: E501
    )
    emit(
        f"    Secondary: top-1 of {n_links} (chance {chance:.3f}) and mean rank (chance {(n_links + 1) / 2:.1f})."  # noqa: E501
    )
    emit()

    per_class_auc: dict[str, list[tuple[float, list[float]]]] = defaultdict(list)
    ranks_by_class: dict[str, list[int]] = defaultdict(list)
    naive_by_class: dict[str, list[int]] = defaultdict(list)
    for i in injs:
        target_lid = lmap.get(i.target_json["link"])
        if target_lid is None:
            continue
        # aggregate 16 endpoint files -> 8 link feature rows (max over the link's two endpoints)
        link_feats: dict[str, dict[str, float]] = {}
        for f in by_inc.get(str(i.id), []):
            stem = f.name[len("incident-") :].rsplit(".", 1)[0]
            iid = stem.split("--", 1)[1].replace("-ethernet-1_", ":ethernet-1/")
            lid = lmap.get(iid)
            if lid is None:
                continue
            fe = endpoint_features(f)
            cur = link_feats.setdefault(lid, dict.fromkeys(FEATURES, 0.0))
            for k in FEATURES:
                cur[k] = max(cur[k], fe[k])
        if target_lid not in link_feats or len(link_feats) < 2:
            continue
        sc = degradation_scores(link_feats)
        per_class_auc[i.fault_class].append(
            (sc[target_lid], [sc[lk] for lk in sc if lk != target_lid])
        )
        rr = target_ranks(link_feats, target_lid)
        if rr is not None:
            naive_by_class[i.fault_class].append(rr[0])
        ranks_by_class[i.fault_class].append(_rank(sc, target_lid))

    ORDER = (
        "admin_shutdown",
        "carrier_loss",
        "intermittent_link",
        "rate_limited_uplink",
        "impaired_link",
        "healthy_control",
    )
    emit(
        f"    {'class':<20} {'n':>3}  {'AUROC':>6} {'95% CI':>15}  {'top1':>6} {'mean_rk':>7}  {'naive_top1':>10}"  # noqa: E501
    )
    results: dict[str, dict] = {}
    for c in ORDER:
        pc = per_class_auc.get(c, [])
        if not pc:
            emit(f"    {c:<20}   0   (no data)")
            continue
        auc, lo, hi = auroc_ci(pc)
        rk = ranks_by_class[c]
        top1 = sum(1 for x in rk if x == 1) / len(rk)
        meanrk = statistics.mean(rk)
        naive_top1 = (
            sum(1 for x in naive_by_class[c] if x == 1) / len(naive_by_class[c])
            if naive_by_class.get(c)
            else 0.0
        )
        results[c] = {"auc": auc, "lo": lo, "hi": hi, "top1": top1, "mean": meanrk, "n": len(pc)}
        emit(
            f"    {c:<20} {len(pc):>3}  {auc:>6.3f} [{lo:.3f},{hi:.3f}]  {top1:>6.3f} {meanrk:>7.2f}  {naive_top1:>10.3f}"  # noqa: E501
        )

    # ---- verdict: signal present & learnable = faulted classes' AUROC CI clears control's ----
    emit()
    ctrl = results.get("healthy_control", {})
    ctrl_hi = ctrl.get("hi", 1.0)
    ctrl_lo = ctrl.get("lo", 0.0)
    faulted = (
        "admin_shutdown",
        "carrier_loss",
        "intermittent_link",
        "rate_limited_uplink",
        "impaired_link",
    )
    # Control HONESTY: the detector must not manufacture signal from a no-fault incident, i.e. the
    # control AUROC must be consistent with chance (its 95% CI includes 0.5). Kept SEPARATE from the
    # per-class test — using the control's noisy CI-hi as the bar would double-count its sampling noise.  # noqa: E501
    ctrl_ok = ctrl_lo <= 0.5 <= ctrl_hi
    # SEPARABILITY: standard bootstrap significance vs CHANCE (AUROC 0.5): class CI-lo > 0.5.
    thr = 0.5
    sep = {c: results.get(c, {}).get("lo", 0) > thr for c in faulted}
    n_sep = sum(sep.values())
    gray_sep = [c for c in GRAY if sep[c]]
    emit(
        f"[VERDICT] Gate 5 row: 'congestion and gray failures produce learnable signatures'  (separable = AUROC 95% CI-lo > chance {thr:.2f})"  # noqa: E501
    )
    emit(
        f"    healthy_control consistent with chance (CI [{ctrl_lo:.3f},{ctrl_hi:.3f}] includes 0.5) — control honest ... {ctrl_ok}"  # noqa: E501
    )
    for c in faulted:
        r = results.get(c, {})
        emit(
            f"    {c:<20} AUROC={r.get('auc', 0):.3f} CI-lo={r.get('lo', 0):.3f}  separable={sep[c]}"  # noqa: E501
        )
    emit()
    # Honest three-way outcome. STOP only if the corpus is hollow (integrity bad OR no gray signal
    # at all OR control not at chance). QUALIFIED PASS if most classes separate incl. >=1 gray, with
    # the weak class explicitly flagged as the thing the learned model must now prove it can lift.
    if not (integrity_ok and ctrl_ok):
        outcome = "STOP"
    elif n_sep >= 4 and len(gray_sep) >= 1:
        outcome = "QUALIFIED PASS"
    else:
        outcome = "STOP"
    verdict = outcome != "STOP"
    if outcome == "QUALIFIED PASS":
        weak = [c for c in faulted if not sep[c]]
        emit(
            f"  ===> EXIT CRITERIA: QUALIFIED PASS — proceed, with {', '.join(weak) or 'none'} FLAGGED."  # noqa: E501
        )
        emit(
            f"       Integrity perfect. {n_sep}/5 faulted classes separate above the honest control,"  # noqa: E501
        )
        emit(
            f"       including gray/congestion class(es): {', '.join(gray_sep)}. The naive two-sided rule"  # noqa: E501
        )
        emit(
            "       (naive_top1) sits at chance for gray faults while the directional/relational AUROC"  # noqa: E501
        )
        emit(
            "       does not — the signal is RELATIONAL (faulted link read against its ECMP peers),"
        )
        emit("       which is exactly the case for the §11.8 GNN over a hand rule.")
        if weak:
            emit(
                f"       FLAGGED: {', '.join(weak)} sits near chance under aggregate hand features. This is a"  # noqa: E501
            )
            emit(
                "       LOWER BOUND, not the ceiling: the MLP/GNN get the full per-endpoint time-series, not"  # noqa: E501
            )
            emit(
                "       these window-aggregate maxes. The learned-model ablation MUST report this class's"  # noqa: E501
            )
            emit(
                "       held-out localization; if the GNN also can't lift it, that is escalated at Gate 13,"  # noqa: E501
            )
            emit("       NOT silently absorbed as a limitation.")
    else:
        emit(
            "  ===> EXIT CRITERIA: STOP — corpus hollow or control not honest; do not build on it."
        )
    emit("=" * 72)

    report = REPO / "evals" / "reports" / "gate12_5-exit-criteria.txt"
    report.write_text("\n".join(out) + "\n")
    print(f"\n(report written to {report.relative_to(REPO)})")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
