"""0002_entities: entities, entity_identifiers, mentions, resolutions

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import JSON

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("ontology_version", sa.String(64), nullable=False),
        sa.Column("aliases", JSONVariant, nullable=True),
    )
    op.create_table(
        "entity_identifiers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_id", sa.Uuid(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("namespace", sa.String(64), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("ontology_version", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "value", "ontology_version", name="uq_entity_identifier"),
    )
    op.create_index("ix_entity_identifiers_entity", "entity_identifiers", ["entity_id"])
    op.create_table(
        "mentions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_version_id", sa.Uuid(), sa.ForeignKey("document_versions.id"), nullable=False),
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("extractor", sa.String(128), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
    )
    op.create_index("ix_mentions_document_version", "mentions", ["document_version_id"])
    op.create_table(
        "resolutions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mention_id", sa.Uuid(), sa.ForeignKey("mentions.id"), nullable=False),
        sa.Column("candidate_entity_ids", JSONVariant, nullable=True),
        sa.Column("chosen_entity_id", sa.Uuid(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolver", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("resolutions")
    op.drop_index("ix_mentions_document_version", table_name="mentions")
    op.drop_table("mentions")
    op.drop_index("ix_entity_identifiers_entity", table_name="entity_identifiers")
    op.drop_table("entity_identifiers")
    op.drop_table("entities")
