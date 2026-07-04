"""§12.1 evidence-grounded diagnostic workflow (Bible §12.1; Gate 10 exit criterion 3).

State machine: collect -> hypothesize -> test -> commit_or_abstain -> draft_plan -> interrupt.
Collect (the §12.3 tools) produces an immutable snapshot; this module runs the rest of it.

- HYPOTHESIZE emits at most three structured hypotheses (capped here; the source may be the LLM or
  the deterministic `RuleHypothesizer` fallback, §10 "LLM unavailable -> deterministic path").
- TEST runs every hypothesis claim through the §12.2 verifier.
- COMMIT_OR_ABSTAIN commits a diagnosis only if ALL its claims are `supported`; otherwise the
  outcome is honest `undiagnosed` — never fabricated certainty (exit criterion 3).
- DRAFT_PLAN maps only a VERIFIED diagnosis class to an allow-listed template id (no untrusted text,
  no evidence-derived parameters reach the plan).
- INTERRUPT: this function is PURE — it performs no I/O and mutates nothing, so no side effect can
  occur before or during the interrupt. The caller persists the returned result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from closcall.evidence.claims import (
    Claim,
    Predicate,
    Snapshot,
    Verdict,
    committable,
    verify,
)

MAX_HYPOTHESES = 3


@dataclass(frozen=True)
class DiagnosisDef:
    """A recognized diagnosis class + the supported-claim signature that ENTAILS it (§12.2)."""

    diagnosis_class: str
    metric: str  # the claim metric that defines this class
    operators: frozenset[str]  # allowed operators for the defining claim
    polarity: bool  # required polarity of the defining claim
    plan_template: str  # allow-listed remediation template id (realized in Gate 11)

    def entailed_by(self, claim: Claim) -> bool:
        return (
            claim.metric_or_event == self.metric
            and claim.operator in self.operators
            and claim.polarity == self.polarity
        )


# Recognized diagnosis classes. A hypothesis with an UNRECOGNIZED class can never commit, and a
# recognized class commits only if a *supported* claim entails it — so a supported-but-irrelevant
# claim (or an arbitrary model-invented class) cannot fabricate a diagnosis (found via 7b fixture).
DIAGNOSIS_DEFINITIONS: dict[str, DiagnosisDef] = {
    "link_down": DiagnosisDef(
        "link_down", "oper_state", frozenset({"<", "<="}), True, "tmpl-restart-interface"
    ),
    "bgp_session_down": DiagnosisDef(
        "bgp_session_down", "bgp_session_state", frozenset({"=="}), True, "tmpl-reset-bgp-session"
    ),
}


@dataclass(frozen=True)
class Hypothesis:
    diagnosis_class: str  # e.g. "link_down"
    subject: str  # candidate root-cause link
    claims: tuple[Claim, ...]  # all must verify `supported` to commit this hypothesis


class Hypothesizer(Protocol):
    def hypothesize(self, snapshot: Snapshot) -> list[Hypothesis]: ...


@dataclass(frozen=True)
class Diagnosis:
    diagnosis_class: str
    subject: str
    committed_claims: tuple[Claim, ...]


@dataclass(frozen=True)
class WorkflowResult:
    outcome: str  # "diagnosed" | "undiagnosed"
    diagnosis: Diagnosis | None
    plan_template: str | None
    tested: list[tuple[str, dict[str, Verdict]]] = field(default_factory=list)  # audit trail


def diagnose(snapshot: Snapshot, hypothesizer: Hypothesizer) -> WorkflowResult:
    """Run hypothesize -> test -> commit_or_abstain -> draft_plan. Pure; returns a result."""
    hypotheses = list(hypothesizer.hypothesize(snapshot))[:MAX_HYPOTHESES]  # at most three (§12.1)
    tested: list[tuple[str, dict[str, Verdict]]] = []

    for hyp in hypotheses:
        verdicts = {c.claim_id: verify(c, snapshot) for c in hyp.claims}
        tested.append((hyp.diagnosis_class, verdicts))
        definition = DIAGNOSIS_DEFINITIONS.get(hyp.diagnosis_class)
        if definition is None or not hyp.claims:
            continue  # unrecognized class or no claims -> cannot commit
        if not all(committable(v) for v in verdicts.values()):
            continue  # any unsupported/contradicted claim -> cannot commit
        if not any(definition.entailed_by(c) for c in hyp.claims):
            continue  # no supported claim ENTAILS the class -> cannot commit (relevance gate)
        return WorkflowResult(
            outcome="diagnosed",
            diagnosis=Diagnosis(hyp.diagnosis_class, hyp.subject, hyp.claims),
            plan_template=definition.plan_template,
            tested=tested,
        )

    # nothing verified/entailed -> honest abstention, no plan (exit criterion 3)
    return WorkflowResult(outcome="undiagnosed", diagnosis=None, plan_template=None, tested=tested)


class RuleHypothesizer:
    """Deterministic fallback (§10): hypothesize `link_down` for each interface observed down."""

    def hypothesize(self, snapshot: Snapshot) -> list[Hypothesis]:
        # gather ALL oper-state evidence per subject (not just the down samples) so the claim is
        # verified over the full window — a flap (any up sample) must contradict "sustained down".
        oper: dict[str, list] = {}  # type: ignore[type-arg]
        any_down: set[str] = set()
        for r in snapshot.records:
            if r.metric_or_event == "oper_state":
                oper.setdefault(r.subject, []).append(r)
                if isinstance(r.value, int | float) and r.value < 0.5:
                    any_down.add(r.subject)
        out: list[Hypothesis] = []
        for subject, recs in oper.items():  # dict preserves insertion order -> deterministic
            if subject not in any_down or len(out) >= MAX_HYPOTHESES:
                continue
            claim = Claim(
                claim_id=f"oper-down::{subject}",
                predicate_type=Predicate.SUSTAINED,
                subject=subject,
                metric_or_event="oper_state",
                operator="<",
                comparison=0.5,
                unit="state",
                interval=(min(r.at for r in recs), snapshot.as_of),
                polarity=True,
                evidence_ids=tuple(r.evidence_id for r in recs),
            )
            out.append(Hypothesis("link_down", subject, (claim,)))
        return out


__all__ = [
    "DIAGNOSIS_DEFINITIONS",
    "MAX_HYPOTHESES",
    "Diagnosis",
    "DiagnosisDef",
    "Hypothesis",
    "Hypothesizer",
    "RuleHypothesizer",
    "WorkflowResult",
    "diagnose",
]
