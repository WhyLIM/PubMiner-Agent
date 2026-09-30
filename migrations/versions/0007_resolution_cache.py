"""0007_resolution_cache: resolution_cache (mention -> candidates 解析缓存)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "resolution_cache",
        sa.Column("mention_key", sa.String(255), primary_key=True),
        sa.Column("entity_type", sa.String(32), primary_key=True),
        sa.Column("resolver", sa.String(128), nullable=False, server_default="composite"),
        sa.Column("candidates", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("resolution_cache")
