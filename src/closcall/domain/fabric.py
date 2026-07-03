"""Fabric source-of-truth model and deterministic IPAM allocator (Bible §7.1, §7.2).

`lab/fabric.yaml` is the only hand-authored fabric/IPAM source. `load_fabric` parses and validates
it; `allocate` derives the fully-resolved topology (per-node loopback/mgmt, per-link /31 endpoints,
host subnets, interface names) as a pure, deterministic function. Nothing here talks to a device —
it is offline rendering input. Address math is verified against SR Linux 25.3.3 (research log R15:
/31 on P2P interfaces is accepted).
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

Role = Literal["spine", "leaf", "host"]


# --- Hand-authored source schema (mirrors lab/fabric.yaml) ---


class _Topology(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    mtu: int
    link_capacity_bps: int


class _Pools(BaseModel):
    model_config = {"extra": "forbid"}
    p2p_supernet: str
    loopback_supernet: str
    management_supernet: str
    host_subnet_template: str


class _Interfaces(BaseModel):
    model_config = {"extra": "forbid"}
    leaf_uplink_to_spine1: str
    leaf_uplink_to_spine2: str
    leaf_downlink_to_host: str
    spine_port_prefix: str
    host_port: str


class _SwitchSpec(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    asn: int


class _HostSpec(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    leaf: str


class _Nodes(BaseModel):
    model_config = {"extra": "forbid"}
    spines: list[_SwitchSpec]
    leaves: list[_SwitchSpec]
    hosts: list[_HostSpec]


class FabricSpec(BaseModel):
    """Validated contents of lab/fabric.yaml."""

    model_config = {"extra": "forbid"}
    schema_version: int
    topology: _Topology
    pools: _Pools
    interfaces: _Interfaces
    nodes: _Nodes


# --- Resolved (rendered-input) topology ---


class ResolvedNode(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    role: Role
    asn: int | None
    loopback: str | None  # /32, switches only
    management: str  # /24-scoped host address for gNMI


class ResolvedEndpoint(BaseModel):
    model_config = {"extra": "forbid"}
    node: str
    interface: str
    address: str | None  # /31 or /24 host-facing; None for the host end of the access link


class ResolvedLink(BaseModel):
    model_config = {"extra": "forbid"}
    key: str
    kind: Literal["fabric", "access"]
    a: ResolvedEndpoint
    b: ResolvedEndpoint
    capacity_bps: int
    mtu: int


class ResolvedHostNetwork(BaseModel):
    model_config = {"extra": "forbid"}
    leaf: str
    subnet: str
    gateway: str  # leaf .1
    host_ip: str  # host .10


class ResolvedTopology(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    nodes: list[ResolvedNode]
    links: list[ResolvedLink]
    host_networks: list[ResolvedHostNetwork]


def load_fabric(path: str | Path) -> FabricSpec:
    """Load and validate lab/fabric.yaml."""
    data = yaml.safe_load(Path(path).read_text())
    return FabricSpec.model_validate(data)


def allocate(spec: FabricSpec) -> ResolvedTopology:
    """Derive the fully-resolved topology from the fabric spec (pure, deterministic).

    Address math (Bible §7.2), verified on SR Linux 25.3.3 (R15):
      - leaf N (1-based) to spine S (1-based): link index k = 2*(N-1)+(S-1);
        the k-th /31 of the p2p supernet; leaf = even address, spine = odd.
      - loopback: /32 from the loopback supernet, ordinal 1.. across spines then leaves.
      - management: host address from the management supernet, same ordinal, hosts appended.
      - host subnet: host_subnet_template with {leaf_index}; leaf gateway .1, host .10.
    """
    p2p = ipaddress.ip_network(spec.pools.p2p_supernet)
    loopback = ipaddress.ip_network(spec.pools.loopback_supernet)
    mgmt = ipaddress.ip_network(spec.pools.management_supernet)
    p2p_base = int(p2p.network_address)
    lo_base = int(loopback.network_address)
    mgmt_base = int(mgmt.network_address)

    spines = spec.nodes.spines
    leaves = spec.nodes.leaves
    if_ = spec.interfaces

    nodes: list[ResolvedNode] = []
    ordinal = 1  # 1-based; also indexes mgmt/loopback host parts (skip network .0)
    for sw in spines:
        nodes.append(
            ResolvedNode(
                name=sw.name,
                role="spine",
                asn=sw.asn,
                loopback=f"{ipaddress.ip_address(lo_base + ordinal)}/32",
                management=str(ipaddress.ip_address(mgmt_base + ordinal)),
            )
        )
        ordinal += 1
    for sw in leaves:
        nodes.append(
            ResolvedNode(
                name=sw.name,
                role="leaf",
                asn=sw.asn,
                loopback=f"{ipaddress.ip_address(lo_base + ordinal)}/32",
                management=str(ipaddress.ip_address(mgmt_base + ordinal)),
            )
        )
        ordinal += 1
    for host in spec.nodes.hosts:
        nodes.append(
            ResolvedNode(
                name=host.name,
                role="host",
                asn=None,
                loopback=None,
                management=str(ipaddress.ip_address(mgmt_base + ordinal)),
            )
        )
        ordinal += 1

    links: list[ResolvedLink] = []
    host_networks: list[ResolvedHostNetwork] = []
    uplinks = {1: if_.leaf_uplink_to_spine1, 2: if_.leaf_uplink_to_spine2}

    for n, leaf in enumerate(leaves, start=1):
        for s, spine in enumerate(spines, start=1):
            k = 2 * (n - 1) + (s - 1)
            leaf_ip = ipaddress.ip_address(p2p_base + 2 * k)
            spine_ip = ipaddress.ip_address(p2p_base + 2 * k + 1)
            links.append(
                ResolvedLink(
                    key=f"{leaf.name}-{spine.name}",
                    kind="fabric",
                    a=ResolvedEndpoint(
                        node=leaf.name, interface=uplinks[s], address=f"{leaf_ip}/31"
                    ),
                    b=ResolvedEndpoint(
                        node=spine.name,
                        interface=f"{if_.spine_port_prefix}{n}",
                        address=f"{spine_ip}/31",
                    ),
                    capacity_bps=spec.topology.link_capacity_bps,
                    mtu=spec.topology.mtu,
                )
            )

    host_by_leaf = {h.leaf: h for h in spec.nodes.hosts}
    for n, leaf in enumerate(leaves, start=1):
        hspec = host_by_leaf.get(leaf.name)
        if hspec is None:
            continue
        subnet = ipaddress.ip_network(spec.pools.host_subnet_template.format(leaf_index=n))
        gw = ipaddress.ip_address(int(subnet.network_address) + 1)
        hip = ipaddress.ip_address(int(subnet.network_address) + 10)
        host_networks.append(
            ResolvedHostNetwork(
                leaf=leaf.name, subnet=str(subnet), gateway=str(gw), host_ip=str(hip)
            )
        )
        links.append(
            ResolvedLink(
                key=f"{leaf.name}-{hspec.name}",
                kind="access",
                a=ResolvedEndpoint(
                    node=leaf.name, interface=if_.leaf_downlink_to_host, address=f"{gw}/24"
                ),
                b=ResolvedEndpoint(node=hspec.name, interface=if_.host_port, address=f"{hip}/24"),
                capacity_bps=spec.topology.link_capacity_bps,
                mtu=spec.topology.mtu,
            )
        )

    return ResolvedTopology(
        name=spec.topology.name, nodes=nodes, links=links, host_networks=host_networks
    )


__all__ = ["FabricSpec", "ResolvedTopology", "allocate", "load_fabric"]
