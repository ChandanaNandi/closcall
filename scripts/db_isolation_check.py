"""Gate 7 DB concurrency + role tests (Contracts §3/§12; exit "DB concurrency and role tests pass").

Proves against the live PostgreSQL:
  1. Ground-truth isolation (E02/I07): a runtime role (closcall_workflow) CANNOT read
     evaluation.ground_truth_labels; the evaluator role CAN.
  2. Concurrent duplicate signals create exactly ONE incident (Contracts §12), via many parallel
     correlate_signal calls racing on the same (source, source_event_id).
Writes evidence to evals/reports/gate7-db.txt.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import Incident, IncidentSignal  # noqa: E402
from closcall.incidents.correlator import correlate_signal  # noqa: E402

_fail = 0
_log: list[str] = []


def emit(ok: bool, name: str, detail: str) -> None:
    global _fail
    if not ok:
        _fail += 1
    line = f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
    print(line)
    _log.append(line)


async def test_ground_truth_isolation(Session) -> None:  # type: ignore[no-untyped-def]
    async def can_select(role: str) -> bool:
        async with Session() as s:
            try:
                await s.execute(text(f"SET ROLE {role}"))
                await s.execute(text("SELECT count(*) FROM evaluation.ground_truth_labels"))
                await s.execute(text("RESET ROLE"))
                return True
            except Exception:
                await s.rollback()
                return False

    workflow_blocked = not await can_select("closcall_workflow")
    evaluator_allowed = await can_select("closcall_evaluator")
    emit(
        workflow_blocked and evaluator_allowed,
        "ground-truth isolation (E02/I07)",
        f"workflow blocked={workflow_blocked}, evaluator allowed={evaluator_allowed}",
    )


async def test_concurrent_dedup(Session) -> None:  # type: ignore[no-untyped-def]
    key = "concurrency-test:leaf1:e1-1"
    sig = "leaf1:e1-1:oper-down"
    # clean any prior
    async with Session() as s:
        await s.execute(
            IncidentSignal.__table__.delete().where(IncidentSignal.source_event_id == sig)
        )
        await s.execute(Incident.__table__.delete().where(Incident.incident_key == key))
        await s.commit()

    async def one() -> None:
        async with Session() as s:
            try:
                await correlate_signal(
                    s,
                    incident_key=key,
                    source="rules",
                    source_event_id=sig,
                    observed_at=datetime.now(UTC),
                    payload={"oper_state": "down"},
                )
                await s.commit()
            except Exception:
                await s.rollback()  # a losing race on the unique key rolls back; still one incident

    await asyncio.gather(*[one() for _ in range(50)])
    async with Session() as s:
        n_inc = (
            await s.execute(
                select(func.count()).select_from(Incident).where(Incident.incident_key == key)
            )
        ).scalar_one()
        n_sig = (
            await s.execute(
                select(func.count())
                .select_from(IncidentSignal)
                .where(IncidentSignal.source_event_id == sig)
            )
        ).scalar_one()
    emit(
        n_inc == 1 and n_sig == 1,
        "concurrent duplicate signals -> one incident",
        f"50 concurrent signals -> {n_inc} incident, {n_sig} signal",
    )


async def run() -> int:
    Session = make_sessionmaker()
    await test_ground_truth_isolation(Session)
    await test_concurrent_dedup(Session)
    print(f"== {_fail} failed ==")
    (REPO / "evals" / "reports" / "gate7-db.txt").write_text(
        "\n".join(_log) + f"\n== {_fail} failed ==\n"
    )
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
