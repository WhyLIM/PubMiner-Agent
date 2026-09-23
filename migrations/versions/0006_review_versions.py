"""0006_review_versions: reviews

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer_id", sa.String(128), nullable=False),
        sa.Column("before", JSONVariant, nullable=True),
        sa.Column("after", JSONVariant, nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_target", "reviews", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_target", table_name="reviews")
    op.drop_table("reviews")
