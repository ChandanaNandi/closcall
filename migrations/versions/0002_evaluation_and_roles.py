"""evaluation schema, artifacts, and DB roles with ground-truth isolation

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

from closcall.db.models import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Runtime roles that must NOT read ground truth (Contracts §3; E02/I07).
_RUNTIME_ROLES = ("closcall_api", "closcall_workflow", "closcall_sensor", "closcall_correlator")
_EVAL_ROLE = "closcall_evaluator"


def upgrade() -> None:
    # New tables (create_all is idempotent — existing slice tables are skipped).
    Base.metadata.create_all(op.get_bind())

    # Roles (cluster-global; guard for idempotency).
    for role in (*_RUNTIME_ROLES, _EVAL_ROLE):
        op.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{role}') "
            f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$;"
        )

    # Runtime roles: work in core, but NEVER in evaluation (ground-truth isolation, §2.1).
    for role in _RUNTIME_ROLES:
        op.execute(f"GRANT USAGE ON SCHEMA core TO {role}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA core TO {role}")
        op.execute(f"REVOKE ALL ON SCHEMA evaluation FROM {role}")
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA evaluation FROM {role}")

    # Evaluator: read-only access to ground truth; not to runtime decision-making.
    op.execute(f"GRANT USAGE ON SCHEMA evaluation TO {_EVAL_ROLE}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA evaluation TO {_EVAL_ROLE}")


def downgrade() -> None:
    for role in (*_RUNTIME_ROLES, _EVAL_ROLE):
        op.execute(f"DROP ROLE IF EXISTS {role}")
    # tables are dropped by the 0001 downgrade if the whole stack is torn down
