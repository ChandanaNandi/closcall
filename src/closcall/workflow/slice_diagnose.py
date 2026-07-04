"""Deterministic diagnosis + prebuilt plan for the Gate 6 slice (NO LLM/neural).

A typed claim evaluates a predicate against an immutable evidence snapshot and returns
supported/contradicted/insufficient (Bible §12.2). A supported down-interface claim maps to a
prebuilt, allowlisted remediation template with an immutable SHA-256 plan digest (§13.1).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

ClaimResult = Literal["supported", "contradicted", "insufficient"]


def evaluate_oper_state_claim(evidence: dict[str, str], expected: str) -> ClaimResult:
    """Typed predicate: interface oper-state == expected, evaluated on the evidence snapshot."""
    observed = evidence.get("oper_state")
    if observed is None:
        return "insufficient"
    return "supported" if observed == expected else "contradicted"


def plan_digest(plan_json: dict[str, str]) -> str:
    """Immutable content digest of a plan (canonical JSON -> sha256 hex)."""
    return hashlib.sha256(json.dumps(plan_json, sort_keys=True).encode()).hexdigest()


def build_link_down_plan(
    node: str, interface: str, topology_hash: str
) -> tuple[dict[str, str], str]:
    """Prebuilt safe remediation for a down fabric interface: re-enable admin-state."""
    plan = {
        "diagnosis_class": "link_down",
        "action": "set_admin_state",
        "node": node,
        "interface": interface,
        "value": "enable",
        "topology_hash": topology_hash,
        "risk_class": "low",
        "recovery_predicate": "oper_state_up",
    }
    return plan, plan_digest(plan)


__all__ = ["ClaimResult", "build_link_down_plan", "evaluate_oper_state_claim", "plan_digest"]
