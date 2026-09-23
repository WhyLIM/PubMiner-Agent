"""0005_workflow: tasks, run_steps

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="mining"),
        sa.Column("request", JSONVariant, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("owner", sa.String(128), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("input_summary", JSONVariant, nullable=True),
        sa.Column("output_summary", JSONVariant, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_steps_task", "run_steps", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_run_steps_task", table_name="run_steps")
    op.drop_table("run_steps")
    op.drop_table("tasks")
