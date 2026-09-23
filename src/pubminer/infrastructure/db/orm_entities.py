"""ORM：entities 聚合（migration 0002_entities）。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pubminer.infrastructure.db.base import Base, JSONVariant
from pubminer.infrastructure.db.orm_documents import utcnow


class EntityRow(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONVariant, default=list)

    identifiers: Mapped[list["EntityIdentifierRow"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )


class EntityIdentifierRow(Base):
    __tablename__ = "entity_identifiers"
    __table_args__ = (
        UniqueConstraint("namespace", "value", "ontology_version", name="uq_entity_identifier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("entities.id"), nullable=False)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entity: Mapped[EntityRow] = relationship(back_populates="identifiers")


class MentionRow(Base):
    __tablename__ = "mentions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id"), nullable=False
    )
    passage_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    extractor: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)


class ResolutionRow(Base):
    __tablename__ = "resolutions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    mention_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("mentions.id"), nullable=False)
    candidate_entity_ids: Mapped[list] = mapped_column(JSONVariant, default=list)
    chosen_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    needs_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    resolver: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
