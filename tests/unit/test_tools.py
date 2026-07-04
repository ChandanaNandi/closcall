"""§12.3 evidence tools — envelope enforcement + ground-truth inaccessibility. Pure/offline.

Proves: as-of bound, result limit, budget (calls + rows), untrusted marking of logs/runbooks, metric
template allow-list, incident scope, and that EvidenceSource exposes no ground-truth accessor.
"""

from __future__ import annotations

import pytest

from closcall.evidence.tools import (
    Budget,
    BudgetExhausted,
    EvidenceSource,
    Record,
    ToolContext,
    get_interface_state,
    get_log_events,
    get_metric_window,
    search_runbooks,
)

INC = "inc-1"
SUBJ = "leaf1:ethernet-1/1"


class FakeSource:
    def __init__(self, iface=(), metric=(), logs=(), runbooks=()):  # type: ignore[no-untyped-def]
        self._iface, self._metric, self._logs, self._rb = (
            list(iface),
            list(metric),
            list(logs),
            list(runbooks),
        )

    def interface_state(self, incident_id, subject):  # type: ignore[no-untyped-def]
        return [r for r in self._iface if incident_id == INC and r.subject == subject]

    def metric_window(self, incident_id, subject, metric, lo, hi):  # type: ignore[no-untyped-def]
        return [
            r
            for r in self._metric
            if incident_id == INC and r.subject == subject and r.metric_or_event == metric
        ]

    def log_events(self, incident_id):  # type: ignore[no-untyped-def]
        return self._logs if incident_id == INC else []

    def runbooks(self, query):  # type: ignore[no-untyped-def]
        return self._rb

    def bgp_state(self, incident_id, subject):  # type: ignore[no-untyped-def]
        return []

    def topology_neighbors(self, subject):  # type: ignore[no-untyped-def]
        return []

    def ranked_links(self, incident_id):  # type: ignore[no-untyped-def]
        return []

    def incident_summary(self, incident_id):  # type: ignore[no-untyped-def]
        return []

    def similar_incidents(self, incident_id):  # type: ignore[no-untyped-def]
        return []


def _ctx(as_of=100.0, limit=10, max_calls=10, max_rows=100):  # type: ignore[no-untyped-def]
    return ToolContext(
        incident_id=INC, as_of=as_of, limit=limit, budget=Budget(max_calls, max_rows)
    )


def _oper(at, value=0.0):  # type: ignore[no-untyped-def]
    return Record(SUBJ, "oper_state", value, "state", at, "telemetry")


def test_as_of_bound_drops_future_evidence() -> None:
    src = FakeSource(iface=[_oper(50), _oper(90), _oper(150)])  # 150 is after as_of=100
    ev = get_interface_state(_ctx(as_of=100.0), src, SUBJ)
    assert [e.at for e in ev] == [50.0, 90.0]


def test_result_limit_caps_rows() -> None:
    src = FakeSource(iface=[_oper(float(t)) for t in range(10)])
    ev = get_interface_state(_ctx(limit=3), src, SUBJ)
    assert len(ev) == 3


def test_call_budget_exhaustion_raises() -> None:
    src = FakeSource(iface=[_oper(50)])
    ctx = _ctx(max_calls=1)
    get_interface_state(ctx, src, SUBJ)  # first call ok
    with pytest.raises(BudgetExhausted, match="call budget"):
        get_interface_state(ctx, src, SUBJ)  # second exceeds


def test_row_budget_exhaustion_raises() -> None:
    src = FakeSource(iface=[_oper(10), _oper(20), _oper(30)])
    with pytest.raises(BudgetExhausted, match="row budget"):
        get_interface_state(_ctx(max_rows=2), src, SUBJ)


def test_logs_and_runbooks_are_untrusted() -> None:
    src = FakeSource(
        iface=[_oper(50)],
        logs=[Record(SUBJ, "log_event", "link down", "text", 50, "log")],
        runbooks=[Record("runbook", "runbook", "reset the link", "text", 0, "runbook")],
    )
    assert get_interface_state(_ctx(), src, SUBJ)[0].trusted is True
    assert get_log_events(_ctx(), src)[0].trusted is False
    assert search_runbooks(_ctx(), src, "link")[0].trusted is False


def test_metric_template_must_be_allowlisted() -> None:
    src = FakeSource(metric=[Record(SUBJ, "in_error_rate", 9.0, "packets_per_s", 50, "telemetry")])
    assert get_metric_window(_ctx(), src, SUBJ, "in_error_rate_window")  # allow-listed
    with pytest.raises(ValueError, match="not allow-listed"):
        get_metric_window(_ctx(), src, SUBJ, "drop; select * from ground_truth")


def test_wrong_incident_scope_returns_nothing() -> None:
    src = FakeSource(iface=[_oper(50)])
    ctx = ToolContext(incident_id="other", as_of=100.0, limit=10, budget=Budget(10, 100))
    assert get_interface_state(ctx, src, SUBJ) == []


def test_evidence_source_has_no_ground_truth_accessor() -> None:
    # structural exit-#2 guard: no tool-facing method can reach ground truth / the evaluation schema
    forbidden = ("ground", "truth", "label", "evaluation", "campaign", "fault_injection")
    methods = [m for m in dir(EvidenceSource) if not m.startswith("_")]
    assert methods, "protocol should expose read-only methods"
    assert not [m for m in methods if any(f in m.lower() for f in forbidden)]
