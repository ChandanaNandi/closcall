"""§12.1 workflow — commit only on supported claims, honest undiagnosed, pure. Pure/offline."""

from __future__ import annotations

from closcall.evidence.claims import Claim, Evidence, Predicate, Snapshot
from closcall.workflow.diagnose import (
    Hypothesis,
    RuleHypothesizer,
    WorkflowResult,
    diagnose,
)

SUBJ = "leaf1:ethernet-1/1"


def _oper(eid: str, value: float, at: float, subject: str = SUBJ) -> Evidence:
    return Evidence(eid, subject, "oper_state", value, "state", at)


def _snap(records: list[Evidence], as_of: float = 30.0) -> Snapshot:
    return Snapshot(as_of=as_of, records=tuple(records))


class _Fixed:
    def __init__(self, hyps: list[Hypothesis]) -> None:
        self._hyps = hyps

    def hypothesize(self, snapshot: Snapshot) -> list[Hypothesis]:
        return self._hyps


def test_down_link_is_diagnosed_and_gets_allowlisted_plan() -> None:
    snap = _snap([_oper("e1", 0.0, 10), _oper("e2", 0.0, 15), _oper("e3", 0.0, 20)])
    res = diagnose(snap, RuleHypothesizer())
    assert res.outcome == "diagnosed"
    assert res.diagnosis is not None and res.diagnosis.diagnosis_class == "link_down"
    assert res.plan_template == "tmpl-restart-interface"  # verified class -> allow-listed template


def test_healthy_snapshot_is_undiagnosed_with_no_plan() -> None:
    snap = _snap([_oper("e1", 1.0, 10), _oper("e2", 1.0, 15)])  # oper up -> no hypothesis
    res = diagnose(snap, RuleHypothesizer())
    assert res.outcome == "undiagnosed"
    assert res.diagnosis is None and res.plan_template is None


def test_contradicted_hypothesis_yields_undiagnosed_not_fabrication() -> None:
    # oper flaps (one sample up) -> sustained-down claim is contradicted -> honest undiagnosed
    snap = _snap([_oper("e1", 0.0, 10), _oper("e2", 1.0, 15), _oper("e3", 0.0, 20)])
    res = diagnose(snap, RuleHypothesizer())
    assert res.outcome == "undiagnosed"
    assert res.plan_template is None


def test_at_most_three_hypotheses_are_tested() -> None:
    # five bogus hypotheses (no claims) -> capped to 3 tested, and none commit -> undiagnosed
    hyps = [Hypothesis(f"class{i}", SUBJ, ()) for i in range(5)]
    res = diagnose(_snap([]), _Fixed(hyps))
    assert len(res.tested) == 3
    assert res.outcome == "undiagnosed"


def test_verified_but_unknown_class_gets_no_plan() -> None:
    # a supported claim whose class isn't allow-listed -> diagnosed, but plan None
    ev = _oper("e1", 0.0, 10)
    claim = Claim(
        claim_id="c",
        predicate_type=Predicate.SUSTAINED,
        subject=SUBJ,
        metric_or_event="oper_state",
        operator="<",
        comparison=0.5,
        unit="state",
        interval=(0.0, 30.0),
        polarity=True,
        evidence_ids=("e1",),
    )
    res = diagnose(_snap([ev]), _Fixed([Hypothesis("novel_class", SUBJ, (claim,))]))
    assert (
        res.outcome == "diagnosed" and res.plan_template is None
    )  # can't map an un-allowlisted class


def test_diagnose_is_pure_no_snapshot_mutation() -> None:
    records = (_oper("e1", 0.0, 10), _oper("e2", 0.0, 20))
    snap = Snapshot(as_of=30.0, records=records)
    before = snap.records
    diagnose(snap, RuleHypothesizer())
    assert snap.records is before  # immutable snapshot untouched (no side effects, §12.1 interrupt)


def test_result_is_a_dataclass_carrying_audit_trail() -> None:
    snap = _snap([_oper("e1", 0.0, 10), _oper("e2", 0.0, 20)])
    res = diagnose(snap, RuleHypothesizer())
    assert isinstance(res, WorkflowResult)
    assert res.tested  # per-claim verdicts recorded for audit
