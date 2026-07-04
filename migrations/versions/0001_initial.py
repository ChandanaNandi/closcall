"""initial core/audit slice schema

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

from closcall.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_SCHEMAS = ("core", "audit", "identity", "evaluation")


def upgrade() -> None:
    for s in _SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
    for s in reversed(_SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE")
