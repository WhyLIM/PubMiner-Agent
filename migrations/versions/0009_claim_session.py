"""0009_claim_session: claims.session_id（命题的会话归属，多课题隔离）

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.create_index("ix_claims_session_id", "claims", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_claims_session_id", table_name="claims")
    op.drop_column("claims", "session_id")
