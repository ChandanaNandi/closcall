"""Read/write contracts the Gate 14 UI needs (Bible §13 HITL face).

Dataclasses are the view models the templates render; `UIRepo` is the port the UI router depends on,
so it is injected with a DB-backed adapter in production and a fake in tests (offline). No business
rule lives here — the approve path's binding gate is `executor.binding.approval_authorizes_plan`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class IncidentSummary:
    id: str
    incident_key: str
    status: str
    severity: str
    opened_at: str
    localized_link: str | None  # node:interface the drafted plan targets, if any


@dataclass(frozen=True)
class DraftedPlan:
    remediation_version_id: str
    plan_version: int
    plan_json: dict  # type: ignore[type-arg]
    plan_digest: str
    risk_class: str
    localized_link: str
    approved: bool  # an approve decision already bound to THIS digest exists
    executed_status: str | None  # execution job status if one ran, else None


@dataclass(frozen=True)
class AuditEntry:
    occurred_at: str
    actor_type: str
    action: str
    entity_type: str
    summary: str


@dataclass(frozen=True)
class CaseFile:
    incident: IncidentSummary
    signals: list[dict] = field(default_factory=list)  # type: ignore[type-arg]
    claim: str = "insufficient"  # deterministic typed-claim result (supported|contradicted|…)
    evidence: dict = field(default_factory=dict)  # type: ignore[type-arg]
    plan: DraftedPlan | None = None
    audit: list[AuditEntry] = field(default_factory=list)


class UIRepo(Protocol):
    def is_authorized(self, incident_id: str, user_id: str) -> bool:
        """IDOR gate: may this principal see this incident? (single-tenant lab -> role-scoped)."""
        ...

    async def list_incidents(self, user_id: str) -> list[IncidentSummary]: ...
    async def get_case_file(self, incident_id: str) -> CaseFile | None: ...

    async def approve_and_execute(self, incident_id: str, user_id: str) -> str:
        """Record an approve decision bound to the current plan's EXACT digest, then drive the
        existing gated executor. Returns the resulting execution status. Never mutates a device
        outside the approval-bound executor path (no side door)."""
        ...

    async def reject(self, incident_id: str, user_id: str) -> None: ...
    async def edit_plan(self, incident_id: str, user_id: str) -> str:
        """Produce a NEW immutable plan version (bumped digest) -> invalidates any prior approval
        (H03). Returns the new digest."""
        ...


__all__ = ["AuditEntry", "CaseFile", "DraftedPlan", "IncidentSummary", "UIRepo"]
