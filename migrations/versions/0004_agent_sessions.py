"""0004_agent_sessions: agent sessions, messages, plans, actions, coverage

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False, server_default="anonymous"),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("task_spec", JSONVariant, nullable=True),
        sa.Column("budget", JSONVariant, nullable=True),
        sa.Column("budget_state", JSONVariant, nullable=True),
        sa.Column("stop_reason", JSONVariant, nullable=True),
        sa.Column("current_plan_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload", JSONVariant, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id"])
    op.create_table(
        "agent_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("steps", JSONVariant, nullable=True),
        sa.Column("approved_by_human", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "version", name="uq_session_plan_version"),
    )
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(64), nullable=True),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("arguments", JSONVariant, nullable=True),
        sa.Column("expected_information_gain", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("budget_delta", JSONVariant, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_actions_session", "agent_actions", ["session_id"])
    op.create_table(
        "coverage_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("agent_sessions.id"), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("coverage_snapshots")
    op.drop_index("ix_agent_actions_session", table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_table("agent_plans")
    op.drop_index("ix_agent_messages_session", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")
