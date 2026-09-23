"""0003_claim_evidence: claims, evidence

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject_entity_id", sa.Uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("object_entity_id", sa.Uuid(), nullable=True),
        sa.Column("object_value", sa.Text(), nullable=True),
        sa.Column("predicate", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False, server_default="UNSPECIFIED"),
        sa.Column("context", JSONVariant, nullable=True),
        sa.Column("context_schema_version", sa.String(64), nullable=False, server_default="biomarker-v1"),
        sa.Column("canonical_signature", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="CANDIDATE"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(128), nullable=False, server_default="agent"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("canonical_signature", "context_schema_version", name="uq_claim_signature"),
    )
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("claim_id", sa.Uuid(), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id"), nullable=False),
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("polarity", sa.String(16), nullable=False),
        sa.Column("span_text", sa.Text(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("span_text_hash", sa.String(64), nullable=False),
        sa.Column("section_path", sa.String(64), nullable=False, server_default=""),
        sa.Column("study", JSONVariant, nullable=True),
        sa.Column("statistics", JSONVariant, nullable=True),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=True),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_version_id", "passage_id", "claim_id", "extraction_run_id",
            name="uq_evidence_pipeline",
        ),
    )
    op.create_index("ix_evidence_claim", "evidence", ["claim_id"])
    op.create_index("ix_evidence_document_version", "evidence", ["document_version_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_document_version", table_name="evidence")
    op.drop_index("ix_evidence_claim", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_claims_status", table_name="claims")
    op.drop_table("claims")
