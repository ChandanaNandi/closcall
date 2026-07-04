"""Live corpus progress tracker — reads the DB (which the runner commits to per incident), so it
shows real-time status even while a batch is running. Run anytime: `make corpus-status`
(or `watch -n 10 make corpus-status` for an auto-refreshing on-screen tracker)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import EvalFaultInjection  # noqa: E402

TARGET = 300
CLASSES = (
    "admin_shutdown",
    "carrier_loss",
    "intermittent_link",
    "rate_limited_uplink",
    "impaired_link",
    "healthy_control",
)
LEAVES = ("leaf1", "leaf2", "leaf3", "leaf4")
PER_CELL = -(-TARGET // (len(CLASSES) * len(LEAVES)))  # ceil


async def main() -> int:
    Session = make_sessionmaker()
    async with Session() as s:
        settled = dict(
            (
                await s.execute(
                    select(EvalFaultInjection.fault_class, func.count())
                    .where(EvalFaultInjection.status == "settled")
                    .group_by(EvalFaultInjection.fault_class)
                )
            ).all()
        )
        cells = dict(
            (
                await s.execute(
                    select(
                        func.concat(
                            EvalFaultInjection.fault_class, "|", EvalFaultInjection.shard_key
                        ),
                        func.count(),
                    )
                    .where(EvalFaultInjection.status == "settled")
                    .group_by(EvalFaultInjection.fault_class, EvalFaultInjection.shard_key)
                )
            ).all()
        )
        total = (
            await s.execute(
                select(func.count())
                .select_from(EvalFaultInjection)
                .where(EvalFaultInjection.status == "settled")
            )
        ).scalar_one()
        quar = (
            await s.execute(
                select(func.count())
                .select_from(EvalFaultInjection)
                .where(EvalFaultInjection.status == "quarantined")
            )
        ).scalar_one()
        inflight = (
            await s.execute(
                select(func.count())
                .select_from(EvalFaultInjection)
                .where(EvalFaultInjection.status == "injecting")
            )
        ).scalar_one()

    bar_n = int(30 * min(total, TARGET) / TARGET)
    bar = "#" * bar_n + "-" * (30 - bar_n)
    print(
        f"ClosCall corpus  [{bar}] {total}/{TARGET} settled  "
        f"({quar} quarantined, {inflight} in-flight)"
    )
    filled = 0
    for c in CLASSES:
        row = " ".join(
            f"{leaf.replace('leaf', 'L')}:{cells.get(f'{c}|{leaf}', 0):>2}" for leaf in LEAVES
        )
        got = settled.get(c, 0)
        for leaf in LEAVES:
            if cells.get(f"{c}|{leaf}", 0) >= PER_CELL:
                filled += 1
        print(f"  {c:<20} total {got:>3}   {row}")
    print(f"strata filled (>= {PER_CELL}/cell): {filled}/{len(CLASSES) * len(LEAVES)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
