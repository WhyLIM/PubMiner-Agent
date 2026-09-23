"""0001_core_documents: documents, document_identifiers, document_versions, passages

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("journal", sa.Text(), nullable=False, server_default=""),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("authors", JSONVariant, nullable=True),
        sa.Column("abstract", sa.Text(), nullable=False, server_default=""),
        sa.Column("publication_types", JSONVariant, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "document_identifiers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.UniqueConstraint("kind", "value", name="uq_identifier_kind_value"),
    )
    op.create_index("ix_document_identifiers_document", "document_identifiers", ["document_id"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("content_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("canonical_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("license", sa.String(64), nullable=True),
        sa.Column("source", sa.String(64), nullable=False, server_default="pubmed"),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "content_version", name="uq_doc_version"),
    )
    op.create_table(
        "passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id"), nullable=False),
        sa.Column("section_path", sa.String(64), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", JSONVariant, nullable=True),
        sa.UniqueConstraint("document_version_id", "start_char", "end_char", name="uq_passage_span"),
    )
    op.create_index("ix_passages_version", "passages", ["document_version_id"])


def downgrade() -> None:
    op.drop_table("passages")
    op.drop_table("document_versions")
    op.drop_index("ix_document_identifiers_document", table_name="document_identifiers")
    op.drop_table("document_identifiers")
    op.drop_table("documents")
