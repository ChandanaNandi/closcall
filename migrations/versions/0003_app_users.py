"""app_users table for the Gate 14 browser UI login identity

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

from closcall.db.models import Base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_RUNTIME_ROLES = ("closcall_api", "closcall_workflow", "closcall_sensor", "closcall_correlator")


def upgrade() -> None:
    # create_all is idempotent — only the new core.app_users table is added.
    Base.metadata.create_all(op.get_bind())
    # The API role must read/write app_users (login + seeding) but still never touches evaluation.
    for role in _RUNTIME_ROLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON core.app_users TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.app_users")
