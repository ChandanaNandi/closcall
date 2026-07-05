"""Gate 12.5 — SUPPLEMENTARY leave-one-leaf-out 4-fold location-CV (features=v2 temporal).

Purpose (single, narrow): resolve one caveat — is the GNN's flat impaired result under the frozen
headline (MLP 0.910 vs GNN 0.721) TRAINING-DATA SCARCITY or a real model ceiling? The frozen
location-inductive split trains on leaf1+leaf2 (26 impaired-class incidents); this CV rotates the
held-out leaf so each fold trains on 3 leaves (~39 impaired), leakage-safe per fold (held-out leaf
disjoint from that fold's training — same E06 guarantee).

GUARDRAIL: the frozen leaf3/leaf4 result is THE headline (pre-registered before any results existed).
This CV is an AFTER-THE-FACT robustness check reported ALONGSIDE it — never a replacement, never an
upgrade to the headline number. Both are printed here with identical methodology for honest comparison.

Reuses the exact headline models (fit_mlp/fit_gnn/rule_score_fn) so no methodology drifts between the
two. Read-only. Writes evals/reports/gate12_5-localization-cv.txt.
"""  # noqa: E501

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import gate12_5_localization_ablation as abl  # noqa: E402

LEAVES = ("leaf1", "leaf2", "leaf3", "leaf4")


def _models(fit, node_ids, nidx, fabric_links, edge_index, dim):
    return {
        "RULE": abl.rule_score_fn(fabric_links),
        "MLP": abl.fit_mlp(fit, fabric_links),
        "GNN": abl.fit_gnn(fit, node_ids, nidx, fabric_links, edge_index, dim),
    }


async def main() -> int:
    abl.VERSION = "v2"  # temporal features — the locus of the impaired confound
    torch.manual_seed(0)
    np.random.seed(0)
    incidents, node_ids, nidx, fabric_links, edge_index = await abl.load()
    dim = len(next(iter(incidents[0]["node_feat"].values())))

    out: list[str] = []

    def emit(s=""):
        out.append(s)
        print(s)

    emit("=" * 78)
    emit("GATE 12.5 — LOCALIZATION: FROZEN HEADLINE vs SUPPLEMENTARY 4-FOLD CV  [features=v2]")
    emit("=" * 78)
    emit(
        "Why two numbers: the location-inductive split fixed leaf3/leaf4 as TEST BEFORE any results"
    )
    emit(
        "existed (pre-registration). That frozen result is THE headline. The 4-fold leave-one-leaf-out"  # noqa: E501
    )
    emit(
        "CV below is an AFTER-THE-FACT robustness check (rotate held-out leaf; 3 training leaves/fold,"  # noqa: E501
    )
    emit(
        "leakage-safe per fold), run ONLY to test whether the GNN's flat impaired result is training-"  # noqa: E501
    )
    emit(
        "data scarcity or a real ceiling. It is a SUPPLEMENT, never a replacement for the headline."
    )
    emit("")

    # ---- frozen headline: fit=leaf1+leaf2, TEST=leaf3+leaf4 (identical to the pre-registered run) ----  # noqa: E501
    fit_h = [c for c in incidents if c["leaf"] in ("leaf1", "leaf2")]
    test_h = [c for c in incidents if c["leaf"] in ("leaf3", "leaf4")]
    emit(
        f"[FROZEN HEADLINE] fit=leaf1+leaf2 (n={len(fit_h)}), TEST=leaf3+leaf4 (n={len(test_h)}) — pre-registered:"  # noqa: E501
    )
    frozen = {}
    for name, fn in _models(fit_h, node_ids, nidx, fabric_links, edge_index, dim).items():
        emit(f"  [{name}]")
        frozen[name] = abl.per_class(abl.eval_ranks(fn, test_h), emit)
    emit("")

    # ---- supplement: 4-fold leave-one-leaf-out CV, pooled held-out predictions ----
    emit(
        "[SUPPLEMENT — 4-fold leave-one-leaf-out CV] each fold: 3 train leaves, held-out leaf scored:"  # noqa: E501
    )
    pooled: dict[str, list] = {"RULE": [], "MLP": [], "GNN": []}
    for held in LEAVES:
        fit = [c for c in incidents if c["leaf"] != held]
        test = [c for c in incidents if c["leaf"] == held]
        models = _models(fit, node_ids, nidx, fabric_links, edge_index, dim)
        for name, fn in models.items():
            pooled[name] += abl.eval_ranks(fn, test)
    cv = {}
    for name in ("RULE", "MLP", "GNN"):
        emit(f"  [{name}] (pooled over 4 held-out leaves)")
        cv[name] = abl.per_class(pooled[name], emit)
    emit("")

    # ---- verdict on the impaired confound (data-driven, both directions honest) ----
    gf = frozen["GNN"]["impaired_link"]["auc"]
    gc = cv["GNN"]["impaired_link"]["auc"]
    gc_lo = cv["GNN"]["impaired_link"]["lo"]
    mc = cv["MLP"]["impaired_link"]["auc"]
    emit("[VERDICT] impaired-class GNN-vs-MLP confound:")
    emit(
        f"    frozen headline : GNN impaired AUROC {gf:.3f}  (MLP {frozen['MLP']['impaired_link']['auc']:.3f})"  # noqa: E501
    )
    emit(f"    4-fold CV       : GNN impaired AUROC {gc:.3f} [CI-lo {gc_lo:.3f}]  (MLP {mc:.3f})")
    recovered = gc >= 0.80 and (mc - gc) < 0.10
    persists = gc < 0.76
    if recovered:
        emit("    => RESOLVED as DATA-SCARCITY: with 3 training leaves the GNN recovers impaired")
        emit(
            f"       localization ({gf:.3f} -> {gc:.3f}, closing on the MLP's {mc:.3f}). The frozen flat"  # noqa: E501
        )
        emit("       result reflects the impaired-class training count (26), NOT a model ceiling.")
    elif persists:
        emit(
            "    => GENUINE, not a confound: the GNN's flat impaired persists under CV with more data"  # noqa: E501
        )
        emit(
            f"       ({gf:.3f} -> {gc:.3f}). The temporal-fed MLP genuinely leads on impaired; the"
        )
        emit(
            "       comparison is real and the data-scarcity caveat is RETIRED (tested, not merely flagged)."  # noqa: E501
        )
    else:
        emit(
            f"    => PARTIAL: GNN impaired moves {gf:.3f} -> {gc:.3f} under CV (MLP {mc:.3f}). Some"
        )
        emit(
            "       data-scarcity effect, but the MLP still leads; report both, neither claim is clean."  # noqa: E501
        )
    emit("")
    emit(
        "HEADLINE UNCHANGED: the pre-registered leaf3/leaf4 numbers remain THE result; this CV is the"  # noqa: E501
    )
    emit(
        "labeled supplement that resolves the confound. No headline number is replaced or upgraded."
    )
    emit("=" * 78)

    rep = REPO / "evals" / "reports" / "gate12_5-localization-cv.txt"
    rep.write_text("\n".join(out) + "\n")
    print(f"\n(report -> {rep.relative_to(REPO)})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
