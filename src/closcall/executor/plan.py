"""Immutable remediation plan (Bible §13.1).

A plan version is frozen and content-addressed: its SHA-256 digest covers every field, so ANY edit
produces a different digest — which invalidates an approval bound to the old digest (an edit
supersedes the old version, §13.1). The digest is the anchor the prechecks and approvals verify.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Action:
    """One exact, bounded action (§13.1 'exact ordered actions and bounded parameters')."""

    action: str  # allow-listed verb, e.g. "set_admin_state"
    node: str
    interface: str
    value: str  # bounded parameter, e.g. "enable"


@dataclass(frozen=True)
class Plan:
    incident_id: str
    plan_version: int
    actions: tuple[Action, ...]  # exact ordered actions
    topology_hash: str  # target topology / config revision
    preconditions: tuple[str, ...]  # safety invariants that must hold
    postconditions: tuple[str, ...]  # expected postconditions
    recovery_predicate: str  # recovery predicate (must be defined)
    rollback: tuple[Action, ...]  # captured rollback procedure
    risk_class: str  # risk / blast-radius class
    provenance: dict[str, str]  # source incident/run/model refs

    def digest(self) -> str:
        """SHA-256 over the canonical serialization of every field (§13.1 provenance + digest)."""
        payload = asdict(self)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=list).encode()
        ).hexdigest()


__all__ = ["Action", "Plan"]
