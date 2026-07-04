"""§9.3 typed-graph builder: topology structure, candidate table, determinism, leakage/ID guards.

Pure/offline — builds from the static lab/fabric.yaml (read-only file). No DB or fabric runtime.
"""

from __future__ import annotations

import pytest

from closcall.datasets.graph import (
    attach_features,
    build_topology_graph,
    graph_schema_hash,
)
from closcall.domain.fabric import allocate, load_fabric

FABRIC = "lab/fabric.yaml"


def _graph():  # type: ignore[no-untyped-def]
    return build_topology_graph(allocate(load_fabric(FABRIC)))


def test_node_and_candidate_counts_match_2s4l_topology() -> None:
    g = _graph()
    # 2 spines + 4 leaves + 4 hosts
    assert len(g.device_nodes) == 10
    assert {d.role for d in g.device_nodes} == {"spine", "leaf", "host"}
    # 8 fabric endpoints*2 + 4 access*2 -> 24 distinct interface nodes
    assert len(g.interface_nodes) == 24
    # candidate physical links: 4 leaves x 2 spines (fabric) + 4 access = 12
    assert len(g.candidate_links) == 12
    assert sum(c.kind == "fabric" for c in g.candidate_links) == 8
    assert sum(c.kind == "access" for c in g.candidate_links) == 4


def test_interface_kinds_are_structural_not_identity() -> None:
    g = _graph()
    kinds = {n.kind for n in g.interface_nodes}
    assert kinds == {"uplink", "fabric_face", "downlink", "access"}
    # a leaf uplink faces a spine fabric_face
    leaf1_up = next(n for n in g.interface_nodes if n.id == "leaf1:ethernet-1/1")
    assert leaf1_up.kind == "uplink" and leaf1_up.device == "leaf1"


def test_contains_and_link_edges_present_both_directions() -> None:
    g = _graph()
    link_edges = [e for e in g.edges if e.relation == "link"]
    contains = [e for e in g.edges if e.relation == "contains"]
    assert len(link_edges) == 24  # 12 physical links x 2 directions
    assert len(contains) == 24  # one per interface node
    # link edges carry structural attrs
    assert all(e.link_kind in ("fabric", "access") and e.capacity_bps for e in link_edges)


def test_topology_hash_is_deterministic() -> None:
    assert _graph().topology_hash == _graph().topology_hash
    assert len(_graph().topology_hash) == 64


def test_down_link_is_retained_as_candidate() -> None:
    # a down interface (oper 0) must NOT remove its link from the candidate set (§11.6)
    g = _graph()
    ex = attach_features(g, {"leaf1:ethernet-1/1": {"util_ratio": 0.0, "missingness_mask": 8}})
    assert any(c.endpoints[0] == "leaf1:ethernet-1/1" for c in g.candidate_links)
    assert ex.interface_features["leaf1:ethernet-1/1"]["util_ratio"] == 0.0


def test_attach_rejects_leakage_and_identity_features() -> None:
    g = _graph()
    with pytest.raises(ValueError, match="leakage"):
        attach_features(g, {"leaf1:ethernet-1/1": {"fault_class": 1}})  # forbidden column
    with pytest.raises(ValueError, match="identity"):
        attach_features(g, {"leaf1:ethernet-1/1": {"node": 1}})  # identity feature


def test_graph_schema_hash_stable() -> None:
    assert graph_schema_hash() == graph_schema_hash()
    assert len(graph_schema_hash()) == 64
