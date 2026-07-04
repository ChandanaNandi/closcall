"""Async database engine/session (Bible §4: SQLAlchemy 2 + asyncpg on PostgreSQL 16).

The password comes from the environment (CLOSCALL_DB_PASSWORD, §6 — never in code/YAML). Host/port
default to the loopback compose mapping (127.0.0.1:15432).
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def db_url(async_driver: bool = True) -> str:
    pw = os.environ.get("CLOSCALL_DB_PASSWORD", "closcall_dev_pw")
    host = os.environ.get("CLOSCALL_DB_HOST", "127.0.0.1")
    port = os.environ.get("CLOSCALL_DB_PORT", "15432")
    driver = "postgresql+asyncpg" if async_driver else "postgresql"
    return f"{driver}://closcall:{pw}@{host}:{port}/closcall"


def make_engine() -> AsyncEngine:
    return create_async_engine(db_url(), pool_pre_ping=True)


def make_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(make_engine(), expire_on_commit=False)


__all__ = ["db_url", "make_engine", "make_sessionmaker"]
