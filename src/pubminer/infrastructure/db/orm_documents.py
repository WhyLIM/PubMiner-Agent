"""ORM：documents 聚合（migration 0001_core_documents）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pubminer.infrastructure.db.base import Base, JSONVariant


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="")
    journal: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authors: Mapped[list] = mapped_column(JSONVariant, default=list)
    abstract: Mapped[str] = mapped_column(Text, default="")
    publication_types: Mapped[list] = mapped_column(JSONVariant, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    identifiers: Mapped[list["DocumentIdentifierRow"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )
    versions: Mapped[list["DocumentVersionRow"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin",
        order_by="DocumentVersionRow.content_version",
    )


class DocumentIdentifierRow(Base):
    __tablename__ = "document_identifiers"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_identifier_kind_value"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # pmid|pmcid|doi
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    document: Mapped[DocumentRow] = relationship(back_populates="identifiers")


class DocumentVersionRow(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "content_version", name="uq_doc_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"), nullable=False)
    content_version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    canonical_text: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="pubmed")
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[DocumentRow] = relationship(back_populates="versions")
    passages: Mapped[list["PassageRow"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", lazy="selectin",
        order_by="PassageRow.start_char",
    )


class PassageRow(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("document_version_id", "start_char", "end_char", name="uq_passage_span"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id"), nullable=False
    )
    section_path: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)  # pgvector 后续迁移

    version: Mapped[DocumentVersionRow] = relationship(back_populates="passages")
