"""Unit tests for deterministic diagnosis + plan (Bible §12.2, §13.1)."""

from closcall.workflow.slice_diagnose import (
    build_link_down_plan,
    evaluate_oper_state_claim,
    plan_digest,
)


def test_claim_supported() -> None:
    assert evaluate_oper_state_claim({"oper_state": "down"}, "down") == "supported"


def test_claim_contradicted() -> None:
    assert evaluate_oper_state_claim({"oper_state": "up"}, "down") == "contradicted"


def test_claim_insufficient_when_missing() -> None:
    assert evaluate_oper_state_claim({}, "down") == "insufficient"


def test_digest_is_deterministic_and_order_independent() -> None:
    a = plan_digest({"x": "1", "y": "2"})
    b = plan_digest({"y": "2", "x": "1"})
    assert a == b and len(a) == 64


def test_digest_changes_with_content() -> None:
    assert plan_digest({"value": "enable"}) != plan_digest({"value": "disable"})


def test_build_plan_is_allowlisted_reversal() -> None:
    plan, digest = build_link_down_plan("leaf1", "ethernet-1/1", "topohash")
    assert plan["action"] == "set_admin_state" and plan["value"] == "enable"
    assert plan["recovery_predicate"] == "oper_state_up"
    assert plan_digest(plan) == digest  # digest matches its plan
