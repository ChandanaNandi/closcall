"""Durable write-ahead chaos ledger (Bible §8.3).

Before any impairment is applied, a `planned` record with the EXACT cleanup payload is written
durably (append + fsync). Apply, observed-onset, clear, and settle transitions are appended after.
A startup reconciler replays the ledger: any injection left `active`/`injecting` (no matching
`cleared`) is cleaned up via its stored payload, or the lab is quarantined (§8.3).

Durability now = an fsync'd JSONL file. Its canonical home is the `evaluation.fault_injections`
PostgreSQL table (Contracts §4.3); that migration happens at Gate 7 when the DB is stood up. Using
a file here honors "simplify, never add" — Postgres is not required to satisfy §8.3 durability.

Every record carries `simulated: true` (§2.12): these are emulated impairments, never real
hardware faults.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class Phase(StrEnum):
    PLANNED = "planned"
    INJECTING = "injecting"
    ACTIVE = "active"
    CLEARING = "clearing"
    CLEARED = "cleared"
    SETTLED = "settled"
    FAILED = "failed"
    QUARANTINED = "quarantined"


# Phases from which an unfinished injection must be reconciled (cleanup owed).
UNRECONCILED = {Phase.PLANNED, Phase.INJECTING, Phase.ACTIVE, Phase.CLEARING}


@dataclass(frozen=True)
class LedgerRecord:
    injection_id: str
    fault_class: str
    phase: Phase
    target: dict[str, str]  # {node, interface}
    cleanup: dict[str, str]  # exact payload to undo the impairment
    event_time: float  # UTC epoch seconds
    monotonic: float  # monotonic clock for durations
    simulated: bool = True
    detail: dict[str, object] = field(default_factory=dict)


class Ledger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, rec: LedgerRecord) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(rec)) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def records(self) -> list[LedgerRecord]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                d["phase"] = Phase(d["phase"])
                out.append(LedgerRecord(**d))
        return out

    def outstanding(self) -> list[LedgerRecord]:
        """Injections whose latest phase is unreconciled (cleanup owed); latest phase per id."""
        latest: dict[str, LedgerRecord] = {}
        for r in self.records():
            latest[r.injection_id] = r
        return [r for r in latest.values() if r.phase in UNRECONCILED]


def now_record(
    injection_id: str,
    fault_class: str,
    phase: Phase,
    target: dict[str, str],
    cleanup: dict[str, str],
    detail: dict[str, object] | None = None,
) -> LedgerRecord:
    return LedgerRecord(
        injection_id=injection_id,
        fault_class=fault_class,
        phase=phase,
        target=target,
        cleanup=cleanup,
        event_time=time.time(),
        monotonic=time.monotonic(),
        detail=detail or {},
    )


__all__ = ["UNRECONCILED", "Ledger", "LedgerRecord", "Phase", "now_record"]
