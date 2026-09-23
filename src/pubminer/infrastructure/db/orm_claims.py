"""ORM：claims / evidence（migration 0003_claim_evidence）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pubminer.infrastructure.db.base import Base, JSONVariant
from pubminer.infrastructure.db.orm_documents import utcnow


class ClaimRow(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("canonical_signature", "context_schema_version", name="uq_claim_signature"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id"), nullable=False
    )
    object_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    object_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicate: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), default="UNSPECIFIED")
    context: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    context_schema_version: Mapped[str] = mapped_column(String(64), default="biomarker-v1")
    canonical_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="CANDIDATE", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evidence_items: Mapped[list["EvidenceRow"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin"
    )


class EvidenceRow(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "passage_id", "claim_id", "extraction_run_id",
            name="uq_evidence_pipeline",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id"), nullable=False
    )
    passage_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    polarity: Mapped[str] = mapped_column(String(16), nullable=False)
    span_text: Mapped[str] = mapped_column(Text, nullable=False)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    span_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    section_path: Mapped[str] = mapped_column(String(64), default="")
    study: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    statistics: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    claim: Mapped[ClaimRow] = relationship(back_populates="evidence_items")
