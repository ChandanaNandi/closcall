"""§10.2 split assembler: location-inductive assignment + disjointness/repeats/purge invariants.

Pure/offline — synthetic incident metadata only. No DB or fabric.
"""

from __future__ import annotations

import pytest

from closcall.datasets.splits import (
    IncidentRef,
    PurgeParams,
    assemble_location_inductive,
)


def _inc(i: int, leaf: str, iface: str = "ethernet-1/1", fam: int | None = None) -> IncidentRef:
    return IncidentRef(
        incident_id=f"inc{i}",
        link_key=f"{leaf}:{iface}",
        leaf=leaf,
        seed_family=fam if fam is not None else i,
        campaign_batch="b1",
        onset_t=float(i * 60),
    )


def _corpus() -> list[IncidentRef]:
    # one incident per leaf x two uplinks
    out = []
    i = 0
    for leaf in ("leaf1", "leaf2", "leaf3", "leaf4"):
        for iface in ("ethernet-1/1", "ethernet-1/2"):
            out.append(_inc(i, leaf, iface))
            i += 1
    return out


def test_location_inductive_assignment_and_frozen_test_set() -> None:
    m = assemble_location_inductive(_corpus())
    # leaf1 train, leaf2 validation, leaf3/4 test
    assert m.counts == {"train": 2, "validation": 2, "test": 4}
    test_links = set(m.link_groups["test"])
    assert all(k.startswith(("leaf3", "leaf4")) for k in test_links)  # TEST = leaf3/4 preserved
    assert set(m.link_groups["train"]) == {"leaf1:ethernet-1/1", "leaf1:ethernet-1/2"}
    assert set(m.link_groups["validation"]) == {"leaf2:ethernet-1/1", "leaf2:ethernet-1/2"}


def test_link_groups_are_disjoint() -> None:
    m = assemble_location_inductive(_corpus())
    seen: set[str] = set()
    for links in m.link_groups.values():
        assert not (set(links) & seen)  # no physical link in two splits (E06)
        seen |= set(links)


def test_disjointness_violation_raises() -> None:
    # same physical link forced into two leaves -> two splits -> E06 leakage
    bad = [
        IncidentRef("a", "leafX:ethernet-1/1", "leaf1", 1, "b1", 0.0),  # -> train
        IncidentRef("b", "leafX:ethernet-1/1", "leaf3", 2, "b1", 60.0),  # -> test, same link
    ]
    with pytest.raises(ValueError, match="E06 leakage"):
        assemble_location_inductive(bad)


def test_repeat_family_straddling_splits_raises() -> None:
    # same seed-family on leaf1 (train) and leaf3 (test) must be rejected
    inc = [_inc(0, "leaf1", fam=99), _inc(1, "leaf3", fam=99)]
    with pytest.raises(ValueError, match="straddles splits"):
        assemble_location_inductive(inc)


def test_unknown_leaf_raises() -> None:
    with pytest.raises(ValueError, match="no split policy"):
        assemble_location_inductive([_inc(0, "leaf9")])


def test_manifest_hash_deterministic_and_records_purge() -> None:
    a = assemble_location_inductive(_corpus())
    b = assemble_location_inductive(_corpus())
    assert a.manifest_hash == b.manifest_hash and len(a.manifest_hash) == 64
    assert a.purge_gap_s == 90.0  # 30 + 30 + 30


def test_purge_gap_flows_into_hash() -> None:
    a = assemble_location_inductive(_corpus())
    b = assemble_location_inductive(_corpus(), purge=PurgeParams(10.0, 10.0, 10.0))
    assert a.manifest_hash != b.manifest_hash  # purge gap is part of provenance
