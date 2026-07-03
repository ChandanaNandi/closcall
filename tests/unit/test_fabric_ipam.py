"""Tests for the fabric IPAM allocator (Bible §7.2 address math)."""

import ipaddress
from pathlib import Path

from closcall.domain.fabric import ResolvedTopology, allocate, load_fabric

FABRIC = Path(__file__).resolve().parents[2] / "lab" / "fabric.yaml"


def _topo() -> ResolvedTopology:
    return allocate(load_fabric(FABRIC))


def test_loads_and_allocates() -> None:
    topo = _topo()
    assert topo.name == "closcall-2s4l"
    # 2 spines + 4 leaves + 4 hosts
    assert len(topo.nodes) == 10
    # 4 leaves x 2 spines fabric links + 4 access links
    assert sum(1 for lk in topo.links if lk.kind == "fabric") == 8
    assert sum(1 for lk in topo.links if lk.kind == "access") == 4


def test_canon_worked_example_leaf1_spine1() -> None:
    # Bible §7.2: leaf1<->spine1 has link index 0 -> 10.0.0.0/31, leaf even, spine odd.
    topo = _topo()
    lk = next(lk for lk in topo.links if lk.key == "leaf1-spine1")
    assert lk.a.node == "leaf1" and lk.a.interface == "ethernet-1/1"
    assert lk.a.address == "10.0.0.0/31"
    assert lk.b.node == "spine1" and lk.b.interface == "ethernet-1/1"
    assert lk.b.address == "10.0.0.1/31"


def test_canon_link_index_formula() -> None:
    # index = 2*(N-1)+(S-1); leaf2<->spine2 -> k=3 -> 10.0.0.6/31 (leaf .6, spine .7)
    topo = _topo()
    lk = next(lk for lk in topo.links if lk.key == "leaf2-spine2")
    assert lk.a.address == "10.0.0.6/31"
    assert lk.b.address == "10.0.0.7/31"
    # spine port faces leaf N: spine2:ethernet-1/2 for leaf2
    assert lk.b.interface == "ethernet-1/2"


def test_loopbacks_are_unique_slash32_on_switches_only() -> None:
    topo = _topo()
    switches = [n for n in topo.nodes if n.role in ("spine", "leaf")]
    hosts = [n for n in topo.nodes if n.role == "host"]
    loopbacks = [n.loopback for n in switches]
    assert all(lb is not None and lb.endswith("/32") for lb in loopbacks)
    assert len(set(loopbacks)) == len(loopbacks)  # unique
    assert all(h.loopback is None for h in hosts)


def test_host_subnets_match_template() -> None:
    topo = _topo()
    hn = {h.leaf: h for h in topo.host_networks}
    assert hn["leaf1"].subnet == "172.16.1.0/24"
    assert hn["leaf1"].gateway == "172.16.1.1"
    assert hn["leaf1"].host_ip == "172.16.1.10"
    assert hn["leaf4"].subnet == "172.16.4.0/24"


def test_asns_match_canon() -> None:
    topo = _topo()
    by_name = {n.name: n for n in topo.nodes}
    assert by_name["spine1"].asn == 65101
    assert by_name["spine2"].asn == 65102
    assert by_name["leaf1"].asn == 65001
    assert by_name["leaf4"].asn == 65004


def test_all_p2p_addresses_unique_and_paired() -> None:
    topo = _topo()
    addrs = []
    for lk in topo.links:
        if lk.kind != "fabric":
            continue
        leaf_ip = ipaddress.ip_interface(lk.a.address)
        spine_ip = ipaddress.ip_interface(lk.b.address)
        # same /31, adjacent addresses, leaf even / spine odd
        assert leaf_ip.network == spine_ip.network
        assert int(leaf_ip.ip) % 2 == 0
        assert int(spine_ip.ip) == int(leaf_ip.ip) + 1
        addrs.extend([str(leaf_ip.ip), str(spine_ip.ip)])
    assert len(set(addrs)) == len(addrs)  # no address reused across links


def test_allocation_is_deterministic() -> None:
    # Same input -> byte-identical serialized output (A04 relies on this).
    a = allocate(load_fabric(FABRIC)).model_dump_json()
    b = allocate(load_fabric(FABRIC)).model_dump_json()
    assert a == b
