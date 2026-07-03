"""Deterministic renderer: fabric spec -> generated artifacts (Bible §7, §5).

Consumes the resolved topology and writes, into an output directory:
  - per-switch SR Linux startup configs (`<node>.cli`), using the 25.3.3 syntax verified in R15;
  - a containerlab topology file (`topology-srl.clab.yml`);
  - a machine-readable `topology.json`;
  - a human IPAM document (`ipam.md`);
  - `manifest.json` with the SHA-256 of every other generated file.

Determinism (acceptance A04): no timestamps, no wall-clock, sorted iteration everywhere, and the
manifest excludes PKI material (certs carry random serials — generated separately, never hashed
into the determinism manifest). Rendering the same fabric twice yields byte-identical output.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path

from closcall.domain.fabric import FabricSpec, ResolvedTopology, allocate

# Pinned SR Linux image (digest is the forever-referent; see docs/toolchain.md, R12).
SRL_IMAGE = (
    "ghcr.io/nokia/srlinux@sha256:f711ddadbca870996793ac9bb3fccb950aa2c6a906da64a304c5274a2c2dceee"
)
# Pinned host image: netshoot (ping/iperf3/nping for reachability + ECMP flow generation).
HOST_IMAGE = "ghcr.io/nicolaka/netshoot@sha256:a20c2531bf35436ed3766cd6cfe89d352b050ccc4d7005ce6400adf97503da1b"
# Host subnets share the 172.16.0.0/16 space; one summary route via the leaf gateway reaches all.
HOST_SUMMARY_ROUTE = "172.16.0.0/16"


def _switch_endpoints(topo: ResolvedTopology, node: str) -> list[tuple[str, str]]:
    """(interface, address) for every subinterface this switch owns, sorted by interface."""
    out: list[tuple[str, str]] = []
    for lk in topo.links:
        for ep in (lk.a, lk.b):
            if ep.node == node and ep.address is not None:
                out.append((ep.interface, ep.address))
    return sorted(out)


def render_srl_config(topo: ResolvedTopology, node_name: str) -> str:
    """Render one switch's SR Linux startup config as `set /` CLI lines (R15-verified syntax)."""
    node = next(n for n in topo.nodes if n.name == node_name)
    assert node.role in ("spine", "leaf") and node.asn is not None and node.loopback is not None
    lines: list[str] = []

    # Data interfaces (each fabric/access endpoint on this node).
    for iface, addr in _switch_endpoints(topo, node_name):
        lines += [
            f"set / interface {iface} admin-state enable",
            f"set / interface {iface} subinterface 0 admin-state enable",
            f"set / interface {iface} subinterface 0 ipv4 admin-state enable",
            f"set / interface {iface} subinterface 0 ipv4 address {addr}",
        ]
    # Loopback on system0.
    lines += [
        "set / interface system0 admin-state enable",
        "set / interface system0 subinterface 0 admin-state enable",
        "set / interface system0 subinterface 0 ipv4 admin-state enable",
        f"set / interface system0 subinterface 0 ipv4 address {node.loopback}",
    ]

    # Prefixes this node originates: its /32 loopback, plus (leaves) its attached host /24.
    lo_host = node.loopback.split("/")[0]
    own_prefixes = [f"{lo_host}/32"]
    for hn in topo.host_networks:
        if hn.leaf == node_name:
            own_prefixes.append(hn.subnet)

    # routing-policy: export only own prefixes; reject everything else (Bible §7.2 tightened in G3).
    for pfx in sorted(own_prefixes):
        net = ipaddress.ip_network(pfx)
        plen = net.prefixlen
        lines.append(
            f"set / routing-policy prefix-set own-prefixes prefix {pfx} "
            f"mask-length-range {plen}..{plen}"
        )
    lines += [
        "set / routing-policy policy export-own statement 10 match prefix prefix-set own-prefixes",
        "set / routing-policy policy export-own statement 10 action policy-result accept",
        "set / routing-policy policy export-own default-action policy-result reject",
        # import: accept received routes (spine relays leaf routes); tightened live in Gate 3.
        "set / routing-policy policy import-any default-action policy-result accept",
    ]

    # network-instance default: bind subinterfaces + BGP.
    ni = "set / network-instance default"
    lines += [f"{ni} type default", f"{ni} admin-state enable"]
    for iface, _ in _switch_endpoints(topo, node_name):
        lines.append(f"{ni} interface {iface}.0")
    lines.append(f"{ni} interface system0.0")
    bgp = f"{ni} protocols bgp"
    lines += [
        f"{bgp} admin-state enable",
        f"{bgp} autonomous-system {node.asn}",
        f"{bgp} router-id {lo_host}",
        f"{bgp} afi-safi ipv4-unicast admin-state enable",
        f"{bgp} group ebgp export-policy [export-own]",
        f"{bgp} group ebgp import-policy [import-any]",
    ]
    # eBGP neighbors: the far endpoint of each fabric link on this node, with per-neighbor peer-as
    # (Bible §7.2: no peer group hides a wrong remote ASN).
    neighbors: list[tuple[str, int]] = []
    for lk in topo.links:
        if lk.kind != "fabric":
            continue
        near, far = (
            (lk.a, lk.b)
            if lk.a.node == node_name
            else ((lk.b, lk.a) if lk.b.node == node_name else (None, None))
        )
        if near is None or far is None or far.address is None:
            continue
        far_node = next(n for n in topo.nodes if n.name == far.node)
        assert far_node.asn is not None
        neighbors.append((far.address.split("/")[0], far_node.asn))
    for nbr_ip, nbr_asn in sorted(neighbors):
        lines += [
            f"{bgp} neighbor {nbr_ip} peer-group ebgp",
            f"{bgp} neighbor {nbr_ip} peer-as {nbr_asn}",
        ]
    return "\n".join(lines) + "\n"


def render_clab(topo: ResolvedTopology) -> str:
    """Render the containerlab topology file (deterministic YAML, stable ordering)."""
    # Force the management network to the fabric.yaml scheme (10.100.0.0/24) so gNMI-over-TLS
    # cert SANs (bound to these IPs by gen_pki.py) stay valid (ADR-003 mgmt ruling, R18). The docker
    # gateway is parked at .254 so nodes can claim .1+ as allocated.
    mgmt_net = ipaddress.ip_network(topo.management_supernet)
    mgmt_gw = ipaddress.ip_address(int(mgmt_net.broadcast_address) - 1)
    lines = [
        "# GENERATED from lab/fabric.yaml — do not edit (Bible §5). Regenerate via `make render`.",
        f"name: {topo.name}",
        "mgmt:",
        "  network: closcall-mgmt",
        f"  ipv4-subnet: {mgmt_net}",
        f"  ipv4-gw: {mgmt_gw}",
        "topology:",
        "  nodes:",
    ]
    # host name -> (interface, host_addr/24, leaf gateway ip) from the access links.
    host_data: dict[str, tuple[str, str, str]] = {}
    for lk in topo.links:
        if lk.kind == "access" and lk.b.address:
            gw = lk.a.address.split("/")[0] if lk.a.address else ""
            host_data[lk.b.node] = (lk.b.interface, lk.b.address, gw)

    for n in sorted(topo.nodes, key=lambda x: x.name):
        mgmt_ip = n.management
        if n.role == "host":
            iface, addr, gw = host_data[n.name]
            lines += [
                f"    {n.name}:",
                "      kind: linux",
                f"      image: {HOST_IMAGE}",
                f"      mgmt-ipv4: {mgmt_ip}",
                "      exec:",
                f"        - ip address add {addr} dev {iface}",
                f"        - ip route add {HOST_SUMMARY_ROUTE} via {gw}",
            ]
        else:
            lines += [
                f"    {n.name}:",
                "      kind: nokia_srlinux",
                f"      image: {SRL_IMAGE}",
                f"      startup-config: {n.name}.cli",
                f"      mgmt-ipv4: {mgmt_ip}",
            ]
    lines += ["  links:"]
    for lk in sorted(topo.links, key=lambda x: x.key):
        a = f"{lk.a.node}:{lk.a.interface}"
        b = f"{lk.b.node}:{lk.b.interface}"
        lines.append(f"    - endpoints: [{a}, {b}]")
    return "\n".join(lines) + "\n"


def render_ipam_doc(topo: ResolvedTopology) -> str:
    lines = [
        f"# IPAM — {topo.name} (GENERATED; do not edit)",
        "",
        "## Nodes",
        "",
        "| node | role | ASN | loopback | mgmt |",
        "|---|---|---|---|---|",
    ]
    for n in sorted(topo.nodes, key=lambda x: x.name):
        lines.append(
            f"| {n.name} | {n.role} | {n.asn or '-'} | {n.loopback or '-'} | {n.management} |"
        )
    lines += ["", "## Fabric links (/31)", "", "| link | leaf end | spine end |", "|---|---|---|"]
    for lk in sorted((x for x in topo.links if x.kind == "fabric"), key=lambda x: x.key):
        a = f"{lk.a.node}:{lk.a.interface} {lk.a.address}"
        b = f"{lk.b.node}:{lk.b.interface} {lk.b.address}"
        lines.append(f"| {lk.key} | {a} | {b} |")
    lines += ["", "## Host networks", "", "| leaf | subnet | gateway | host |", "|---|---|---|---|"]
    for hn in sorted(topo.host_networks, key=lambda x: x.leaf):
        lines.append(f"| {hn.leaf} | {hn.subnet} | {hn.gateway} | {hn.host_ip} |")
    return "\n".join(lines) + "\n"


def render_all(spec: FabricSpec, out_dir: str | Path) -> dict[str, str]:
    """Render every artifact into out_dir; return {filename: sha256}. Deterministic."""
    topo = allocate(spec)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}

    def _write(name: str, content: str) -> None:
        (out / name).write_text(content)
        files[name] = hashlib.sha256(content.encode()).hexdigest()

    for n in sorted(topo.nodes, key=lambda x: x.name):
        if n.role in ("spine", "leaf"):
            _write(f"{n.name}.cli", render_srl_config(topo, n.name))
    _write("topology-srl.clab.yml", render_clab(topo))
    _write("topology.json", json.dumps(topo.model_dump(), indent=2, sort_keys=True) + "\n")
    _write("ipam.md", render_ipam_doc(topo))

    manifest = {"topology": topo.name, "files": dict(sorted(files.items()))}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return files


__all__ = ["render_all", "render_clab", "render_ipam_doc", "render_srl_config"]
