"""The single approval->plan binding gate (Bible §13.1/§13.2).

Execution is authorized ONLY by an `approve` decision bound to the plan's EXACT immutable SHA-256
digest. This one predicate is shared by the isolated executor's precheck AND the Gate 14 browser
approve path, so both enforce the identical rule — the UI is a face on the gated flow, never a side
door around it. An edited plan gets a new digest, so any prior approval stops authorizing it (H03).
"""

from __future__ import annotations


def approval_authorizes_plan(*, decision: str, approval_digest: str, plan_digest: str) -> bool:
    """True iff this decision approves EXACTLY this plan digest. Any mismatch -> not authorized."""
    return decision == "approve" and approval_digest == plan_digest


__all__ = ["approval_authorizes_plan"]
