# ClosCall — Hardening Backlog

Items deferred from core acceptance by ADR-001 (Amendment A1). Fully specified in planning docs 03/04.
Promotion back to core requires a superseding ADR. None of these gate the core release.

1. Approval expiry and revocation (time-bounded decisions; revocation blocking execution)
2. Multi-worker executor leasing + transactional outbox (core uses single executor with DB idempotency + outcome_unknown reconciliation)
3. JWT refresh-token rotation and revocation infrastructure; API rate limits (CSRF remains core)
4. Cryptographic tamper-evident audit hash chain (core: append-only audit, FK integrity, mutation-blocking on audit failure)
5. Full multi-service restart/failure matrix (Prometheus/LLM/device permutations; core covers executor + PostgreSQL)
6. Backup / point-in-time-recovery program with restore drills
7. **H07 full precheck-suite live wiring (ADR-004, Amendment A2).** Wire `run_prechecks` into
   `executor.execute_job`. Requires: (a) a `Plan` deserializer reconciling `rv.plan_json`
   `{action,value,node,interface}` with the structured `Plan`; (b) five real `PrecheckContext` fact
   providers — live topology-hash, telemetry freshness/completeness, alternate-path health, capacity
   headroom, final-usable-path; (c) an integration test proving `execute_job` fails closed on the
   live path when any provider trips. Live path today enforces the narrower subset (approval-digest +
   allowlist + mgmt-interface). Do NOT wire with stubbed context (safety theater).

Post-core feature extensions (from Spec §12, unchanged): SONiC profile; NIKA scenario-pack contribution;
eBPF host telemetry exporter; NCCL-in-the-loop benchmarks; K8s/Helm on kind + event bus with measured
justification; sim-to-real pretraining on discrete-event sim.
