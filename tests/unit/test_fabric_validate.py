"""Static fabric validation tests (B01) and malformed-fixture rejection (Gate 2 exit)."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from closcall.domain.fabric import FabricSpec
from closcall.domain.validate import validate_fabric

FABRIC = Path(__file__).resolve().parents[2] / "lab" / "fabric.yaml"


def _raw() -> dict[str, Any]:
    return yaml.safe_load(FABRIC.read_text())  # type: ignore[no-any-return]


def test_canonical_fabric_is_valid() -> None:
    assert validate_fabric(FabricSpec.model_validate(_raw())) == []


def test_duplicate_asn_rejected() -> None:
    raw = _raw()
    raw["nodes"]["leaves"][1]["asn"] = raw["nodes"]["leaves"][0]["asn"]  # dup ASN
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("duplicate ASN" in e for e in errors)


def test_asn_out_of_private_range_rejected() -> None:
    raw = _raw()
    raw["nodes"]["spines"][0]["asn"] = 100  # public/invalid
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("private" in e for e in errors)


def test_dangling_host_leaf_rejected() -> None:
    raw = _raw()
    raw["nodes"]["hosts"][0]["leaf"] = "leaf99"
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("unknown leaf" in e for e in errors)


def test_bad_prefix_pool_rejected() -> None:
    raw = _raw()
    raw["pools"]["p2p_supernet"] = "10.0.0.0/33"  # invalid mask
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("not a valid network" in e for e in errors)


def test_p2p_pool_too_small_rejected() -> None:
    raw = _raw()
    raw["pools"]["p2p_supernet"] = "10.0.0.0/30"  # only 2 addrs -> 1 /31, need 8
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("/31s but" in e for e in errors)


def test_empty_interface_rejected() -> None:
    raw = _raw()
    raw["interfaces"]["leaf_uplink_to_spine1"] = ""
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("interface mapping" in e for e in errors)


def test_duplicate_node_name_rejected() -> None:
    raw = _raw()
    raw["nodes"]["leaves"][1]["name"] = "leaf1"
    errors = validate_fabric(FabricSpec.model_validate(raw))
    assert any("duplicate node name" in e for e in errors)


def test_unknown_field_rejected_at_parse() -> None:
    raw = _raw()
    raw["topology"]["bogus"] = 1
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError (extra=forbid)
        FabricSpec.model_validate(raw)


def test_fixture_mutations_are_isolated() -> None:
    # sanity: deepcopy of raw doesn't leak between cases
    a, b = _raw(), _raw()
    b["topology"]["name"] = "changed"
    assert a["topology"]["name"] != b["topology"]["name"]
    assert copy.deepcopy(a) == a
