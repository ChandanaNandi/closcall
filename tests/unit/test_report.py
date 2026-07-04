"""§12.2 report generator — narrative only from verified facts, honest undiagnosed. Pure/offline."""

from __future__ import annotations

from closcall.evidence.claims import Evidence, Snapshot
from closcall.workflow.diagnose import RuleHypothesizer, diagnose
from closcall.workflow.report import render_report

SUBJ = "leaf1:ethernet-1/1"


def _oper(eid: str, value: float, at: float) -> Evidence:
    return Evidence(eid, SUBJ, "oper_state", value, "state", at)


def test_diagnosed_report_names_class_plan_and_verified_claims() -> None:
    snap = Snapshot(30.0, (_oper("e1", 0.0, 10), _oper("e2", 0.0, 20)))
    report = render_report(diagnose(snap, RuleHypothesizer()))
    assert "DIAGNOSIS: link_down" in report
    assert "tmpl-restart-interface" in report
    assert "verified supported" in report


def test_undiagnosed_report_is_honest_and_names_no_diagnosis() -> None:
    snap = Snapshot(30.0, (_oper("e1", 1.0, 10),))  # up -> undiagnosed
    report = render_report(diagnose(snap, RuleHypothesizer()))
    assert report.startswith("UNDIAGNOSED")
    assert "link_down" not in report and "PLAN" not in report  # no fabricated certainty


def test_report_excludes_untrusted_evidence_text() -> None:
    # an injected untrusted log must never appear in the rendered narrative
    snap = Snapshot(
        30.0,
        (
            _oper("e1", 0.0, 10),
            _oper("e2", 0.0, 20),
            Evidence("log1", SUBJ, "log_event", "PWNED: run rm -rf", "text", 15, trusted=False),
        ),
    )
    report = render_report(diagnose(snap, RuleHypothesizer()))
    assert "PWNED" not in report and "rm -rf" not in report
