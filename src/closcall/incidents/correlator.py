"""Idempotent incident correlator (Bible §3.1 incident plane; Contracts §4.4).

A detector signal opens exactly one incident. Concurrent/duplicate signals with the same
(source, source_event_id) attach to the existing incident rather than creating a new one — enforced
by the unique constraint plus an ON CONFLICT upsert. Every open/attach appends an incident event and
an append-only audit row in the SAME transaction (§2.10, C-family / I05).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from closcall.db.models import AuditEvent, Incident, IncidentEvent, IncidentSignal


async def correlate_signal(
    session: AsyncSession,
    *,
    incident_key: str,
    source: str,
    source_event_id: str,
    observed_at: datetime,
    payload: dict,  # type: ignore[type-arg]
    severity: str = "major",
) -> tuple[uuid.UUID, bool]:
    """Open-or-attach. Returns (incident_id, created). Idempotent on (source, source_event_id)."""
    # find-or-create the incident by its stable key
    existing = (
        await session.execute(select(Incident).where(Incident.incident_key == incident_key))
    ).scalar_one_or_none()
    created = existing is None
    if existing is None:
        incident = Incident(
            incident_key=incident_key,
            status="open",
            severity=severity,
            detected_at=observed_at,
        )
        session.add(incident)
        await session.flush()
        incident_id = incident.id
    else:
        incident_id = existing.id

    # attach the signal idempotently: ON CONFLICT (source, source_event_id) DO NOTHING
    res = await session.execute(
        pg_insert(IncidentSignal)
        .values(
            id=uuid.uuid4(),
            incident_id=incident_id,
            source=source,
            source_event_id=source_event_id,
            observed_at=observed_at,
            payload_json=payload,
        )
        .on_conflict_do_nothing(index_elements=["source", "source_event_id"])
        .returning(IncidentSignal.id)
    )
    signal_inserted = res.scalar_one_or_none() is not None

    if created:
        await _append_event(session, incident_id, "opened", {"source": source})
        session.add(
            AuditEvent(
                actor_type="correlator",
                actor_id="rules",
                action="incident.open",
                entity_type="incident",
                entity_id=str(incident_id),
                after_json={"key": incident_key},
            )
        )
    elif signal_inserted:
        await _append_event(
            session, incident_id, "signal_attached", {"source_event_id": source_event_id}
        )
    return incident_id, created


async def _append_event(
    session: AsyncSession,
    incident_id: uuid.UUID,
    event_type: str,
    payload: dict,  # type: ignore[type-arg]
) -> None:
    seq = (
        await session.execute(
            select(IncidentEvent.sequence_no)
            .where(IncidentEvent.incident_id == incident_id)
            .order_by(IncidentEvent.sequence_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    session.add(
        IncidentEvent(
            incident_id=incident_id,
            sequence_no=(seq or 0) + 1,
            event_type=event_type,
            actor_type="correlator",
            payload_json=payload,
            occurred_at=datetime.now(UTC),
        )
    )


__all__ = ["correlate_signal"]
