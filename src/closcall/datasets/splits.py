"""§10.2 location-inductive split assembler (Bible §10.2; E06 leakage guard).

Assigns incidents to disjoint train/validation/test groups by fault *location* (the target physical
link), then enforces the frozen split invariants and emits a hashed manifest. Pure: it never touches
the DB (persisting the manifest to `evaluation.split_manifests` is a separate post-corpus step).

Policy (default): TEST = leaf3/leaf4 is preserved exactly as the corpus stored it (TEST membership
must never shift — it is scored only after selection freezes); VALIDATION is carved out of the train
group (leaf2) so scalers/baselines/thresholds can be fit on TRAIN/VALIDATION only. Each physical
link belongs to exactly one leaf, so the groups are physical-link-disjoint by construction (E06).

Invariants enforced (§10.2):
- disjoint physical-link groups — a link key may map to only one split (else E06 leakage);
- repeats together — incidents sharing seed-family or campaign-batch stay in one split;
- purge — for a location-inductive split, link-disjointness IS the purge guarantee: different splits
  use different physical links, hence disjoint telemetry series, so no window can straddle a split
  boundary. The purge gap (lookback+persistence+cooldown) is recorded for provenance and for the
  time-based protocols (not assembled here).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass

PROTOCOL = "location-inductive"
SPLIT_VERSION = 1

# leaf -> split. TEST frozen (leaf3/4); VALIDATION carved from the train group (leaf2).
LOCATION_INDUCTIVE_POLICY: dict[str, str] = {
    "leaf1": "train",
    "leaf2": "validation",
    "leaf3": "test",
    "leaf4": "test",
}


@dataclass(frozen=True)
class IncidentRef:
    """The split-relevant metadata for one incident (no telemetry, no ground truth)."""

    incident_id: str
    link_key: str  # target physical link "leaf:iface" == the fault location
    leaf: str  # shard_key
    seed_family: int  # repeats sharing this stay in one split
    campaign_batch: str
    onset_t: float


@dataclass(frozen=True)
class PurgeParams:
    lookback_s: float
    persistence_s: float
    cooldown_s: float

    @property
    def gap_s(self) -> float:
        return self.lookback_s + self.persistence_s + self.cooldown_s


_DEFAULT_PURGE = PurgeParams(30.0, 30.0, 30.0)  # module singleton (avoids a call in arg defaults)


@dataclass(frozen=True)
class SplitManifest:
    protocol: str
    version: int
    assignments: dict[str, str]  # incident_id -> split
    link_groups: dict[str, list[str]]  # split -> sorted unique link keys
    counts: dict[str, int]  # split -> incident count
    purge_gap_s: float
    manifest_hash: str


def _hash_manifest(
    protocol: str, version: int, groups: dict[str, list[str]], purge_gap_s: float
) -> str:
    payload = {
        "protocol": protocol,
        "version": version,
        "link_groups": {k: sorted(v) for k, v in groups.items()},
        "purge_gap_s": purge_gap_s,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def assemble_location_inductive(
    incidents: list[IncidentRef],
    *,
    policy: dict[str, str] = LOCATION_INDUCTIVE_POLICY,
    purge: PurgeParams = _DEFAULT_PURGE,
    version: int = SPLIT_VERSION,
) -> SplitManifest:
    """Assign the location-inductive split and enforce the §10.2 invariants (raises on breach)."""
    assignments: dict[str, str] = {}
    link_split: dict[str, str] = {}
    for inc in incidents:
        split = policy.get(inc.leaf)
        if split is None:
            raise ValueError(f"no split policy for leaf {inc.leaf!r}")
        assignments[inc.incident_id] = split
        # disjoint physical-link groups (E06): a link may live in exactly one split
        prev = link_split.get(inc.link_key)
        if prev is not None and prev != split:
            raise ValueError(f"E06 leakage: link {inc.link_key!r} in two splits ({prev}, {split})")
        link_split[inc.link_key] = split

    # repeats together: a seed-family or campaign-batch may not straddle splits
    fam_split: dict[tuple[int, str], str] = {}
    for inc in incidents:
        key = (inc.seed_family, inc.campaign_batch)
        s = assignments[inc.incident_id]
        if key in fam_split and fam_split[key] != s:
            raise ValueError(
                f"repeat family {key} straddles splits ({fam_split[key]}, {s}) — must be one split"
            )
        fam_split[key] = s

    groups: dict[str, set[str]] = defaultdict(set)
    for inc in incidents:
        groups[assignments[inc.incident_id]].add(inc.link_key)
    link_groups = {k: sorted(v) for k, v in groups.items()}
    counts = dict(Counter(assignments.values()))
    return SplitManifest(
        protocol=PROTOCOL,
        version=version,
        assignments=assignments,
        link_groups=link_groups,
        counts=counts,
        purge_gap_s=purge.gap_s,
        manifest_hash=_hash_manifest(PROTOCOL, version, link_groups, purge.gap_s),
    )


__all__ = [
    "LOCATION_INDUCTIVE_POLICY",
    "PROTOCOL",
    "IncidentRef",
    "PurgeParams",
    "SplitManifest",
    "assemble_location_inductive",
]
