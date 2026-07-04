"""§9.3 typed-graph builder (Bible §9.3, §11.6; Contracts §9.3).

Turns the static Clos topology (`domain.fabric.ResolvedTopology`) into the canonical typed graph the
edge-ranking GNN consumes (§4.2, §11.6): device and interface node tables, typed directed relations
(`contains`: device->interface; `link`: interface<->interface), and the eligible physical-link
candidate table (root cause is a physical-link candidate, §4.2). Down links are RETAINED as
candidates (§11.6): down-ness is a per-incident feature, never a structural pruning.

Identity is kept strictly out of features (the §11.9 ID-removal invariant): node/link ids live in
the tables for structure and evaluator joins, but only structural attributes (role, interface kind,
link kind/capacity/mtu) and the §9.2 causal features may inform the model. The ground-truth
root-cause link is an evaluator-only sidecar (`GraphLabel`), never merged into features.

Graph *structure* is static (one hash per topology); §9.2 causal features are attached per incident.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from closcall.datasets.schemas import FORBIDDEN_FEATURE_COLUMNS, schema_hash
from closcall.domain.fabric import ResolvedTopology

NODE_TYPES = ("device", "interface")
EDGE_RELATIONS = ("contains", "link")
GRAPH_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DeviceNode:
    id: str  # identity — structure/eval only, NEVER a feature
    role: str  # spine | leaf | host — structural feature


@dataclass(frozen=True)
class InterfaceNode:
    id: str  # "node:interface" identity — structure/eval only, NEVER a feature
    device: str  # owning device id
    kind: str  # uplink | fabric_face | downlink | access — structural role of the interface


@dataclass(frozen=True)
class TypedEdge:
    src: str
    dst: str
    relation: str  # "contains" | "link"
    link_kind: str | None = None  # fabric | access (link edges only)
    capacity_bps: int | None = None
    mtu: int | None = None


@dataclass(frozen=True)
class CandidateLink:
    key: str  # physical-link identity (the edge-ranking target)
    kind: str  # fabric | access
    endpoints: tuple[str, str]  # the two interface-node ids


@dataclass(frozen=True)
class TypedGraph:
    device_nodes: list[DeviceNode]
    interface_nodes: list[InterfaceNode]
    edges: list[TypedEdge]
    candidate_links: list[CandidateLink]
    topology_hash: str


@dataclass(frozen=True)
class GraphExample:
    """One per-incident graph: static structure + §9.2 causal features on interface nodes."""

    topology_hash: str
    interface_features: dict[str, dict[str, float | int]]  # interface_id -> §9.2 numeric features
    feature_schema_hash: str


@dataclass(frozen=True)
class GraphLabel:
    """Evaluator-only sidecar: ground-truth root-cause physical link. Never a feature (§9.3)."""

    root_cause_link_key: str


def graph_schema_hash() -> str:
    """Pins the graph *schema* (node/edge/candidate contract), distinct from a topology instance."""
    payload = {
        "version": GRAPH_SCHEMA_VERSION,
        "node_types": NODE_TYPES,
        "edge_relations": EDGE_RELATIONS,
        "device_fields": ["id", "role"],
        "interface_fields": ["id", "device", "kind"],
        "edge_fields": ["src", "dst", "relation", "link_kind", "capacity_bps", "mtu"],
        "candidate_fields": ["key", "kind", "endpoints"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _iface_kind(role: str, link_kind: str) -> str:
    if link_kind == "fabric":
        return (
            "uplink" if role == "leaf" else "fabric_face"
        )  # leaf side up, spine side faces fabric
    return "downlink" if role == "leaf" else "access"  # access link: leaf downlink / host access


def _hash_topology(g: TypedGraph) -> str:
    payload = {
        "devices": [asdict(d) for d in g.device_nodes],
        "interfaces": [asdict(i) for i in g.interface_nodes],
        "edges": [asdict(e) for e in g.edges],
        "candidates": [asdict(c) for c in g.candidate_links],
        "schema": graph_schema_hash(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=list).encode()).hexdigest()


def build_topology_graph(topo: ResolvedTopology) -> TypedGraph:
    """Build the canonical typed graph from a resolved topology (pure, deterministic)."""
    role = {n.name: n.role for n in topo.nodes}
    devices = sorted((DeviceNode(id=n.name, role=n.role) for n in topo.nodes), key=lambda d: d.id)

    ifaces: dict[str, InterfaceNode] = {}
    edges: list[TypedEdge] = []
    candidates: list[CandidateLink] = []
    for link in topo.links:
        a_id = f"{link.a.node}:{link.a.interface}"
        b_id = f"{link.b.node}:{link.b.interface}"
        for ep, iid in ((link.a, a_id), (link.b, b_id)):
            if iid not in ifaces:
                ifaces[iid] = InterfaceNode(
                    id=iid, device=ep.node, kind=_iface_kind(role[ep.node], link.kind)
                )
        # typed link relation, both directions (undirected physical link -> two directed edges)
        edges.append(TypedEdge(a_id, b_id, "link", link.kind, link.capacity_bps, link.mtu))
        edges.append(TypedEdge(b_id, a_id, "link", link.kind, link.capacity_bps, link.mtu))
        candidates.append(CandidateLink(key=link.key, kind=link.kind, endpoints=(a_id, b_id)))

    for iid, ifn in ifaces.items():
        edges.append(TypedEdge(ifn.device, iid, "contains"))

    interface_nodes = [ifaces[k] for k in sorted(ifaces)]
    edges.sort(key=lambda e: (e.relation, e.src, e.dst))
    candidates.sort(key=lambda c: c.key)
    g = TypedGraph(devices, interface_nodes, edges, candidates, topology_hash="")
    return TypedGraph(devices, interface_nodes, edges, candidates, _hash_topology(g))


def attach_features(
    graph: TypedGraph, features_by_interface: dict[str, dict[str, float | int]]
) -> GraphExample:
    """Attach §9.2 features to interface nodes, asserting no identity/leakage (§11.9, §9.3)."""
    attached: dict[str, dict[str, float | int]] = {}
    for node in graph.interface_nodes:
        feats = features_by_interface.get(node.id, {})
        if set(feats) & FORBIDDEN_FEATURE_COLUMNS:
            raise ValueError(
                f"leakage: forbidden feature on {node.id}: {set(feats) & FORBIDDEN_FEATURE_COLUMNS}"
            )
        if any(k in {"id", "node", "interface", "name", "key"} for k in feats):
            raise ValueError(f"identity feature on {node.id} (violates §11.9 ID removal)")
        attached[node.id] = dict(feats)
    return GraphExample(
        topology_hash=graph.topology_hash,
        interface_features=attached,
        feature_schema_hash=schema_hash(),
    )


__all__ = [
    "EDGE_RELATIONS",
    "NODE_TYPES",
    "CandidateLink",
    "DeviceNode",
    "GraphExample",
    "GraphLabel",
    "InterfaceNode",
    "TypedEdge",
    "TypedGraph",
    "attach_features",
    "build_topology_graph",
    "graph_schema_hash",
]
