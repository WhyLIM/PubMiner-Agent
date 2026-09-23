"""ORM：agent_sessions 聚合（migration 0004_agent_sessions）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pubminer.infrastructure.db.base import Base, JSONVariant
from pubminer.infrastructure.db.orm_documents import utcnow


class AgentSessionRow(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), default="anonymous")
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    task_spec: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    budget: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    budget_state: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    stop_reason: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    current_plan_version: Mapped[int] = mapped_column(Integer, default=0)
    turn: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["AgentMessageRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin",
        order_by="AgentMessageRow.created_at",
    )
    plans: Mapped[list["AgentPlanRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin",
        order_by="AgentPlanRow.version",
    )
    actions: Mapped[list["AgentActionRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin",
        order_by="AgentActionRow.turn, AgentActionRow.created_at",
    )
    coverage_snapshots: Mapped[list["CoverageSnapshotRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin",
        order_by="CoverageSnapshotRow.turn",
    )


class AgentMessageRow(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[AgentSessionRow] = relationship(back_populates="messages")


class AgentPlanRow(Base):
    __tablename__ = "agent_plans"
    __table_args__ = (UniqueConstraint("session_id", "version", name="uq_session_plan_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_sessions.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSONVariant, default=list)
    approved_by_human: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[AgentSessionRow] = relationship(back_populates="plans")


class AgentActionRow(Base):
    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_sessions.id"), nullable=False
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arguments: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    expected_information_gain: Mapped[str] = mapped_column(Text, default="")
    result_summary: Mapped[str] = mapped_column(Text, default="")
    budget_delta: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[AgentSessionRow] = relationship(back_populates="actions")


class CoverageSnapshotRow(Base):
    __tablename__ = "coverage_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_sessions.id"), nullable=False
    )
    turn: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[AgentSessionRow] = relationship(back_populates="coverage_snapshots")
