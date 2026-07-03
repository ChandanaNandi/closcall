# ADR-001 — Scope Waivers (Amendment A1)

Status: accepted
Context: An 18-fault senior review produced documents 03–05 with production-grade requirements. A scope
ruling deferred several to a hardening backlog, but the ruling initially lived only in the README while
document 05 (highest precedence) still mandated them — an internal contradiction (caught in follow-up
review). Per 05's own Master release rule, waivers must be marked in the matrix and justified by ADR.

Decision: The following are WAIVED from core acceptance and moved to docs/backlog.md:
- Approval expiry and revocation binding/blocking (H02/H03 clauses)
- Multi-worker executor leasing and transactional outbox (H06 clause)
- JWT rotation/revocation infrastructure and rate limits (I02 clause; secure cookie, CSRF, JWT claims,
  RBAC, and IDOR remain core)
- Cryptographic tamper-evident audit hash chain (I05 clause; append-only audit with FK integrity remains core)
- Full multi-service restart matrix (J03 clause; executor + PostgreSQL restart determinism remains core)
- Backup/restore program (J04 row)

Rationale: single-operator lab deployment with no untrusted callers; these items add zero evaluation
rows and materially delay completion. The project's founding doctrine ("minimum architecture that proves
the required claims safely and honestly") cuts against enterprise ceremony exactly as it cuts against
buzzword integration. All items remain fully specified in documents 03/04 for post-core hardening.

Authentication ruling: the HTMX UI uses a short-lived JWT in an HttpOnly/Secure/SameSite cookie.
Because browsers attach cookies automatically, CSRF tokens on state-changing requests remain a core
requirement. This is a small load-bearing control, not deferred ceremony.

Consequences: release README must list these as explicit limitations; resume/README claims must not
imply the waived properties; backlog items may be promoted back to core only by a superseding ADR.
