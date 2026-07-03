"""Static fabric validation (Bible §7.1 consistency, acceptance B01).

`validate_fabric` returns a list of human-readable error strings; empty means valid. It catches
malformed ASN / prefix / interface / topology *before* any deployment (Gate 2 exit criterion),
covering both structural errors on the source spec and address-collision errors after allocation.
Pydantic already rejects wrong-typed / unknown / missing fields at parse time; this layer covers the
semantic checks Pydantic cannot.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence

from closcall.domain.fabric import FabricSpec, allocate


def validate_fabric(spec: FabricSpec) -> list[str]:
    """Return all validation errors for a fabric spec (empty list == valid)."""
    errors: list[str] = []

    switches = spec.nodes.spines + spec.nodes.leaves
    all_names = [n.name for n in switches] + [h.name for h in spec.nodes.hosts]
    leaf_names = {leaf.name for leaf in spec.nodes.leaves}

    # Unique node names.
    _report_dupes(errors, all_names, "node name")
    # Unique switch ASNs, all private-range.
    asns = [sw.asn for sw in switches]
    _report_dupes(errors, asns, "ASN")
    for sw in switches:
        if not (64512 <= sw.asn <= 65534):
            errors.append(
                f"ASN {sw.asn} on {sw.name} is outside the private 16-bit range 64512-65534"
            )
    # Host must attach to an existing leaf.
    for h in spec.nodes.hosts:
        if h.leaf not in leaf_names:
            errors.append(f"host {h.name} references unknown leaf '{h.leaf}'")

    # Interfaces must be non-empty strings.
    for field, value in spec.interfaces.model_dump().items():
        if not isinstance(value, str) or not value.strip():
            errors.append(f"interface mapping '{field}' is empty or invalid")

    # Pools must parse; capacity/MTU sane.
    for field in ("p2p_supernet", "loopback_supernet", "management_supernet"):
        val = getattr(spec.pools, field)
        try:
            ipaddress.ip_network(val)
        except ValueError as exc:
            errors.append(f"pool {field}='{val}' is not a valid network: {exc}")
    if spec.topology.mtu <= 0:
        errors.append(f"mtu {spec.topology.mtu} must be positive")
    if spec.topology.link_capacity_bps <= 0:
        errors.append(f"link_capacity_bps {spec.topology.link_capacity_bps} must be positive")

    # p2p supernet must hold one /31 per leaf-spine link.
    if not errors:
        p2p = ipaddress.ip_network(spec.pools.p2p_supernet)
        needed = len(spec.nodes.leaves) * len(spec.nodes.spines)
        available = p2p.num_addresses // 2
        if needed > available:
            errors.append(f"p2p_supernet holds {available} /31s but {needed} links need one each")

    # If structurally sound, allocate and check for address collisions.
    if not errors:
        errors.extend(_address_collision_errors(spec))
    return errors


def _address_collision_errors(spec: FabricSpec) -> list[str]:
    out: list[str] = []
    topo = allocate(spec)
    loopbacks = [n.loopback for n in topo.nodes if n.loopback]
    mgmt = [n.management for n in topo.nodes]
    _report_dupes(out, loopbacks, "loopback")
    _report_dupes(out, mgmt, "management address")

    p2p_addrs: list[str] = []
    for lk in topo.links:
        if lk.kind == "fabric":
            for ep in (lk.a, lk.b):
                if ep.address:
                    p2p_addrs.append(ep.address.split("/")[0])
    _report_dupes(out, p2p_addrs, "p2p address")

    subnets = [ipaddress.ip_network(hn.subnet) for hn in topo.host_networks]
    for i, a in enumerate(subnets):
        for b in subnets[i + 1 :]:
            if a.overlaps(b):
                out.append(f"host subnets {a} and {b} overlap")
    return out


def _report_dupes(errors: list[str], items: Sequence[object], label: str) -> None:
    seen: set[object] = set()
    for it in items:
        if it in seen:
            errors.append(f"duplicate {label}: {it}")
        seen.add(it)


__all__ = ["validate_fabric"]
