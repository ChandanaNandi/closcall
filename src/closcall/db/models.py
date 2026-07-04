"""SQLAlchemy 2 models for the Gate 6 vertical slice (Contracts §4 subset).

Only the tables the deterministic slice touches: incidents + signals + events, remediation versions
(immutable, digest-addressed), approval decisions, execution jobs (idempotent), executions/steps,
recovery checks, and an append-only audit log. Names/constraints follow Bible §6 and Contracts §4.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = ({"schema": "core"},)
    id: Mapped[uuid.UUID] = _uuid_pk()
    incident_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class IncidentSignal(Base):
    __tablename__ = "incident_signals"
    __table_args__ = (
        UniqueConstraint("source", "source_event_id", name="uq_signal_source_event"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.incidents.id", ondelete="RESTRICT")
    )
    source: Mapped[str] = mapped_column(String(64))
    source_event_id: Mapped[str] = mapped_column(String(128))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    __table_args__ = (
        UniqueConstraint("incident_id", "sequence_no", name="uq_event_incident_seq"),
        {"schema": "core"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.incidents.id", ondelete="RESTRICT")
    )
    sequence_no: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(48))
    actor_type: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RemediationVersion(Base):
    __tablename__ = "remediation_versions"
    __table_args__ = (
        UniqueConstraint("incident_id", "plan_version", name="uq_remv_incident_version"),
        UniqueConstraint("plan_digest", name="uq_remv_digest"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.incidents.id", ondelete="RESTRICT")
    )
    plan_version: Mapped[int] = mapped_column(BigInteger)
    plan_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    plan_digest: Mapped[str] = mapped_column(String(64))  # sha256 hex
    topology_hash: Mapped[str] = mapped_column(String(64))
    risk_class: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("remediation_version_id", "user_id", name="uq_decision_remv_user"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    remediation_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.remediation_versions.id", ondelete="RESTRICT")
    )
    plan_digest: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))  # approve|reject
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecutionJob(Base):
    __tablename__ = "execution_jobs"
    __table_args__ = (
        UniqueConstraint("remediation_version_id", name="uq_job_remv"),
        UniqueConstraint("idempotency_key", name="uq_job_idem"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    remediation_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.remediation_versions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24))  # pending|running|completed|...
    attempts: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("execution_job_id", name="uq_exec_job"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    execution_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.execution_jobs.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(24))  # succeeded|failed|outcome_unknown
    observed_config_before: Mapped[dict | None] = mapped_column(JSONB)  # type: ignore[type-arg]
    observed_config_after: Mapped[dict | None] = mapped_column(JSONB)  # type: ignore[type-arg]
    failure_class: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecoveryCheck(Base):
    __tablename__ = "recovery_checks"
    __table_args__ = ({"schema": "core"},)
    id: Mapped[uuid.UUID] = _uuid_pk()
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.executions.id", ondelete="RESTRICT")
    )
    check_type: Mapped[str] = mapped_column(String(48))
    result: Mapped[str] = mapped_column(String(16))  # passed|failed
    observed_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("sha256", name="uq_artifact_sha256"), {"schema": "core"})
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(48))
    uri: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalCampaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("campaign_key", name="uq_campaign_key"),
        {"schema": "evaluation"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    campaign_key: Mapped[str] = mapped_column(String(128))
    code_revision: Mapped[str] = mapped_column(String(64))
    master_seed: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalFaultInjection(Base):
    __tablename__ = "fault_injections"
    __table_args__ = ({"schema": "evaluation"},)
    id: Mapped[uuid.UUID] = _uuid_pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation.campaigns.id", ondelete="RESTRICT")
    )
    fault_class: Mapped[str] = mapped_column(String(32))
    shard_key: Mapped[str] = mapped_column(String(32))
    target_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    parameters_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    traffic_seed: Mapped[int] = mapped_column(BigInteger)
    fault_seed: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24))
    device_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    simulated: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalGroundTruthLabel(Base):
    __tablename__ = "ground_truth_labels"
    __table_args__ = (
        UniqueConstraint("fault_injection_id", name="uq_gtlabel_injection"),
        {"schema": "evaluation"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    fault_injection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation.fault_injections.id", ondelete="RESTRICT")
    )
    label_json: Mapped[dict] = mapped_column(JSONB)  # type: ignore[type-arg]
    label_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalSplitManifest(Base):
    __tablename__ = "split_manifests"
    __table_args__ = (
        UniqueConstraint("protocol_name", "version", name="uq_split_proto_version"),
        {"schema": "evaluation"},
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    protocol_name: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(BigInteger)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "events"
    __table_args__ = ({"schema": "audit"},)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(48))
    entity_id: Mapped[str] = mapped_column(String(64))
    before_json: Mapped[dict | None] = mapped_column(JSONB)  # type: ignore[type-arg]
    after_json: Mapped[dict | None] = mapped_column(JSONB)  # type: ignore[type-arg]


CHECK_JOB_STATUS = CheckConstraint(
    "status in ('pending','running','reconciling','completed','retryable_failed',"
    "'permanent_failed','outcome_unknown')",
    name="ck_job_status",
)


__all__ = [
    "ApprovalDecision",
    "Artifact",
    "AuditEvent",
    "Base",
    "EvalCampaign",
    "EvalFaultInjection",
    "EvalGroundTruthLabel",
    "EvalSplitManifest",
    "Execution",
    "ExecutionJob",
    "Incident",
    "IncidentEvent",
    "IncidentSignal",
    "RecoveryCheck",
    "RemediationVersion",
]
