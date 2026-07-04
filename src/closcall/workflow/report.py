"""§12.1/§12.2 report generator — narrative ONLY after verification (Bible §12.2; Gate 10).

Renders a human-readable report from a `WorkflowResult`. By construction it draws exclusively from
the committed diagnosis and its verified claims (or the honest `undiagnosed` outcome) — never from
unverified hypotheses or untrusted evidence text — so "narrative prose is generated only after
verification" holds structurally.
"""

from __future__ import annotations

from closcall.workflow.diagnose import WorkflowResult


def render_report(result: WorkflowResult) -> str:
    if result.outcome != "diagnosed" or result.diagnosis is None:
        n_tested = len(result.tested)
        return (
            "UNDIAGNOSED: no hypothesis met the evidence bar after "
            f"{n_tested} tested; abstaining, no remediation plan drafted."
        )
    d = result.diagnosis
    lines = [
        f"DIAGNOSIS: {d.diagnosis_class} at {d.subject}",
        f"PLAN TEMPLATE: {result.plan_template}",
        "VERIFIED SUPPORTING CLAIMS:",
    ]
    for c in d.committed_claims:
        lines.append(
            f"  - {c.metric_or_event} {c.operator} {c.comparison} "
            f"[{c.interval[0]:.0f},{c.interval[1]:.0f}] (verified supported)"
        )
    return "\n".join(lines)


__all__ = ["render_report"]
