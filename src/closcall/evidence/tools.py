"""§12.3 evidence tools — read-only, scoped, bounded (Bible §12.3; Gate 10 exit criterion 2).

The nine typed tools the Collect stage (§12.1) uses to build immutable evidence snapshots. Every
tool runs through one envelope enforcing: incident scope, as-of upper bound (no future reads),
result limit, and trace/budget accounting. Tools read only core/runtime data via `EvidenceSource` —
which has NO method that exposes the evaluation schema, so ground truth is inaccessible by design.

Retrieved logs and runbooks are returned as UNTRUSTED evidence (`trusted=False`); the plan/executor
stages must never let untrusted text populate action parameters (§12.3). `get_metric_window` accepts
only allow-listed template IDs — free-form metric queries are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from closcall.evidence.claims import Evidence


class BudgetExhausted(RuntimeError):
    """Raised when a tool call would exceed the per-diagnosis call/row budget (§12.3, §12.4)."""


@dataclass
class Budget:
    max_calls: int
    max_rows: int
    calls: int = 0
    rows: int = 0

    def charge(self, n_rows: int) -> None:
        self.calls += 1
        self.rows += n_rows
        if self.calls > self.max_calls:
            raise BudgetExhausted(f"call budget exceeded ({self.calls} > {self.max_calls})")
        if self.rows > self.max_rows:
            raise BudgetExhausted(f"row budget exceeded ({self.rows} > {self.max_rows})")


@dataclass
class ToolContext:
    incident_id: str  # scope — every tool query is filtered to this incident
    as_of: float  # upper time bound — evidence after this is never returned (§10.3 causal)
    limit: int  # per-call result cap
    budget: Budget
    trace: list[str] = field(default_factory=list)


# Allow-listed metric templates for get_metric_window (§12.3): id -> (metric, unit).
METRIC_TEMPLATES: dict[str, tuple[str, str]] = {
    "oper_state_window": ("oper_state", "state"),
    "in_error_rate_window": ("in_error_rate", "packets_per_s"),
    "in_discard_rate_window": ("in_discard_rate", "packets_per_s"),
    "octet_rate_window": ("octet_rate", "bytes_per_s"),
}


@dataclass(frozen=True)
class Record:
    """A read-only core-data row an EvidenceSource yields (never from the evaluation schema)."""

    subject: str
    metric_or_event: str
    value: float | str
    unit: str
    at: float
    source: str  # "telemetry" | "bgp" | "log" | "runbook" | "topology" | "ranking" | "summary"


class EvidenceSource(Protocol):
    """Read-only core-data access. Deliberately has no ground-truth/evaluation method (exit #2)."""

    def interface_state(self, incident_id: str, subject: str) -> list[Record]: ...
    def bgp_state(self, incident_id: str, subject: str) -> list[Record]: ...
    def metric_window(
        self, incident_id: str, subject: str, metric: str, lo: float, hi: float
    ) -> list[Record]: ...
    def log_events(self, incident_id: str) -> list[Record]: ...
    def topology_neighbors(self, subject: str) -> list[Record]: ...
    def ranked_links(self, incident_id: str) -> list[Record]: ...
    def incident_summary(self, incident_id: str) -> list[Record]: ...
    def runbooks(self, query: str) -> list[Record]: ...
    def similar_incidents(self, incident_id: str) -> list[Record]: ...


_UNTRUSTED_SOURCES = frozenset({"log", "runbook"})


def _emit(ctx: ToolContext, tool: str, records: list[Record]) -> list[Evidence]:
    """The shared envelope: drop future evidence, cap to limit, charge budget, tag trust."""
    kept = [r for r in records if r.at <= ctx.as_of][: ctx.limit]  # as-of bound + result limit
    ctx.budget.charge(len(kept))
    ctx.trace.append(f"{tool}: {len(kept)} evidence (as_of={ctx.as_of})")
    return [
        Evidence(
            evidence_id=f"{r.source}:{r.subject}:{r.metric_or_event}:{r.at}",
            subject=r.subject,
            metric_or_event=r.metric_or_event,
            value=r.value,
            unit=r.unit,
            at=r.at,
            trusted=r.source not in _UNTRUSTED_SOURCES,
        )
        for r in kept
    ]


def get_interface_state(ctx: ToolContext, src: EvidenceSource, subject: str) -> list[Evidence]:
    return _emit(ctx, "get_interface_state", src.interface_state(ctx.incident_id, subject))


def get_bgp_state(ctx: ToolContext, src: EvidenceSource, subject: str) -> list[Evidence]:
    return _emit(ctx, "get_bgp_state", src.bgp_state(ctx.incident_id, subject))


def get_metric_window(
    ctx: ToolContext, src: EvidenceSource, subject: str, template_id: str
) -> list[Evidence]:
    if template_id not in METRIC_TEMPLATES:
        raise ValueError(f"metric template {template_id!r} not allow-listed (§12.3)")
    metric = METRIC_TEMPLATES[template_id][0]
    records = src.metric_window(ctx.incident_id, subject, metric, ctx.as_of - ctx.limit, ctx.as_of)
    return _emit(ctx, "get_metric_window", records)


def get_log_events(ctx: ToolContext, src: EvidenceSource) -> list[Evidence]:
    return _emit(ctx, "get_log_events", src.log_events(ctx.incident_id))


def get_topology_neighbors(ctx: ToolContext, src: EvidenceSource, subject: str) -> list[Evidence]:
    return _emit(ctx, "get_topology_neighbors", src.topology_neighbors(subject))


def get_ranked_links(ctx: ToolContext, src: EvidenceSource) -> list[Evidence]:
    return _emit(ctx, "get_ranked_links", src.ranked_links(ctx.incident_id))


def get_incident_summary(ctx: ToolContext, src: EvidenceSource) -> list[Evidence]:
    return _emit(ctx, "get_incident_summary", src.incident_summary(ctx.incident_id))


def search_runbooks(ctx: ToolContext, src: EvidenceSource, query: str) -> list[Evidence]:
    return _emit(ctx, "search_runbooks", src.runbooks(query))


def get_similar_resolved_incidents(ctx: ToolContext, src: EvidenceSource) -> list[Evidence]:
    return _emit(ctx, "get_similar_resolved_incidents", src.similar_incidents(ctx.incident_id))


__all__ = [
    "METRIC_TEMPLATES",
    "Budget",
    "BudgetExhausted",
    "EvidenceSource",
    "Record",
    "ToolContext",
    "get_bgp_state",
    "get_incident_summary",
    "get_interface_state",
    "get_log_events",
    "get_metric_window",
    "get_ranked_links",
    "get_similar_resolved_incidents",
    "get_topology_neighbors",
    "search_runbooks",
]
