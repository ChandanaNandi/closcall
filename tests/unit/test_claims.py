"""§12.2 verifier — adversarial fixtures: no bad claim may reach `supported`. Pure/offline.

Covers the six §12.2 adversarial cases: wrong polarity, unit, interface, time, nearby-but-irrelevant
metric, and cherry-picked samples — plus the happy path, ill-typed comparison, and the commit gate.
"""

from __future__ import annotations

from closcall.evidence.claims import (
    Claim,
    Evidence,
    Predicate,
    Snapshot,
    Verdict,
    committable,
    verify,
)

SUBJECT = "leaf1:ethernet-1/1"
METRIC = "in_error_rate"
UNIT = "packets_per_s"


def _ev(eid: str, value: float | str, at: float, *, subject=SUBJECT, metric=METRIC, unit=UNIT):  # type: ignore[no-untyped-def]
    return Evidence(
        evidence_id=eid, subject=subject, metric_or_event=metric, value=value, unit=unit, at=at
    )


def _claim(**over):  # type: ignore[no-untyped-def]
    base = dict(
        claim_id="c1",
        predicate_type=Predicate.SUSTAINED,
        subject=SUBJECT,
        metric_or_event=METRIC,
        operator=">",
        comparison=5.0,
        unit=UNIT,
        interval=(0.0, 20.0),
        polarity=True,
        evidence_ids=("e1", "e2", "e3"),
    )
    base.update(over)
    return Claim(**base)  # type: ignore[arg-type]


def _snap(records):  # type: ignore[no-untyped-def]
    return Snapshot(as_of=20.0, records=tuple(records))


def test_genuine_sustained_claim_is_supported() -> None:
    snap = _snap([_ev("e1", 10.0, 5), _ev("e2", 8.0, 10), _ev("e3", 12.0, 15)])
    assert verify(_claim(), snap) is Verdict.SUPPORTED
    assert committable(Verdict.SUPPORTED)


def test_cherry_picked_sample_cannot_carry_a_sustained_claim() -> None:
    # one sample below threshold -> sustained fails -> contradicted (not supported)
    snap = _snap([_ev("e1", 10.0, 5), _ev("e2", 2.0, 10), _ev("e3", 12.0, 15)])
    assert verify(_claim(), snap) is Verdict.CONTRADICTED


def test_wrong_polarity_is_contradicted() -> None:
    # claim asserts NOT(>5) but all samples are >5
    snap = _snap([_ev("e1", 10.0, 5), _ev("e2", 8.0, 10), _ev("e3", 12.0, 15)])
    assert verify(_claim(polarity=False), snap) is Verdict.CONTRADICTED


def test_wrong_unit_is_insufficient() -> None:
    snap = _snap([_ev("e1", 10.0, 5, unit="bytes"), _ev("e2", 8.0, 10, unit="bytes")])
    assert verify(_claim(), snap) is Verdict.INSUFFICIENT


def test_wrong_interface_is_insufficient() -> None:
    snap = _snap([_ev("e1", 10.0, 5, subject="leaf2:ethernet-1/1")])
    assert verify(_claim(), snap) is Verdict.INSUFFICIENT


def test_out_of_time_evidence_is_insufficient() -> None:
    snap = _snap([_ev("e1", 10.0, 100), _ev("e2", 8.0, 200)])  # outside [0,20]
    assert verify(_claim(), snap) is Verdict.INSUFFICIENT


def test_nearby_but_irrelevant_metric_is_insufficient() -> None:
    snap = _snap([_ev("e1", 10.0, 5, metric="in_discard_rate")])  # not in_error_rate
    assert verify(_claim(), snap) is Verdict.INSUFFICIENT


def test_ill_typed_comparison_is_insufficient() -> None:
    # ordering operator against a string state value -> cannot support
    snap = _snap([_ev("e1", "up", 5, unit="state")])
    assert verify(_claim(unit="state"), snap) is Verdict.INSUFFICIENT


def test_only_supported_is_committable() -> None:
    assert committable(Verdict.SUPPORTED)
    assert not committable(Verdict.CONTRADICTED)
    assert not committable(Verdict.INSUFFICIENT)
