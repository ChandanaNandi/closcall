"""Seed the Gate 14 login identities into core.app_users (idempotent).

Creates a viewer, an operator, and an approver with Argon2id-hashed passwords. Password comes from
CLOSCALL_SEED_PASSWORD (default 'closcall-demo'). Run: uv run python scripts/api_seed.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from closcall.api.auth import hash_password  # noqa: E402
from closcall.db.engine import make_sessionmaker  # noqa: E402
from closcall.db.models import AppUser  # noqa: E402

USERS = [("viewer1", "viewer"), ("operator1", "operator"), ("approver1", "approver")]


async def run() -> int:
    pw = os.environ.get("CLOSCALL_SEED_PASSWORD", "closcall-demo")
    Session = make_sessionmaker()
    async with Session() as s:
        for uid, role in USERS:
            await s.execute(
                pg_insert(AppUser)
                .values(user_id=uid, role=role, password_hash=hash_password(pw))
                .on_conflict_do_update(
                    index_elements=["user_id"],
                    set_={"role": role, "password_hash": hash_password(pw)},
                )
            )
        await s.commit()
    print(f"seeded {len(USERS)} app users: " + ", ".join(f"{u}/{r}" for u, r in USERS))
    print(f"  password = CLOSCALL_SEED_PASSWORD (default 'closcall-demo'); current = {pw!r}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
