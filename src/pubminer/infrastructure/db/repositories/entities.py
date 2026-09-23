"""Entity 仓储：resolver 结果落库、按 identifier 查找（ADR-006）。"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pubminer.domain.entities import Entity, IdentifierSource
from pubminer.infrastructure.db.orm_entities import EntityIdentifierRow, EntityRow


class EntityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_identifier(self, namespace: str, value: str, ontology_version: str) -> Entity | None:
        stmt = (
            select(EntityRow)
            .join(EntityIdentifierRow, EntityIdentifierRow.entity_id == EntityRow.id)
            .where(
                EntityIdentifierRow.namespace == namespace,
                EntityIdentifierRow.value == value,
                EntityIdentifierRow.ontology_version == ontology_version,
            )
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        return self._to_domain(row) if row else None

    def create_entity(self, entity: Entity) -> Entity:
        """写入实体及其 resolver 来源的 identifier。"""
        row = EntityRow(
            id=entity.id,
            type=entity.type.value,
            canonical_name=entity.canonical_name,
            ontology_version=entity.ontology_version,
            aliases=[a.model_dump(mode="json") for a in entity.aliases],
        )
        for identifier in entity.identifiers:
            row.identifiers.append(
                EntityIdentifierRow(
                    namespace=identifier.namespace,
                    value=identifier.value,
                    ontology_version=identifier.ontology_version,
                    source=identifier.source.value,
                    score=identifier.score,
                    resolved_at=identifier.resolved_at,
                )
            )
        self.session.add(row)
        self.session.flush()
        return self._to_domain(row)

    def get(self, entity_id: UUID) -> Entity | None:
        row = self.session.get(EntityRow, entity_id)
        return self._to_domain(row) if row else None

    def _to_domain(self, row: EntityRow) -> Entity:
        from pubminer.domain.entities import EntityAlias, EntityIdentifier

        return Entity(
            id=row.id,
            type=row.type,
            canonical_name=row.canonical_name,
            ontology_version=row.ontology_version,
            aliases=[EntityAlias.model_validate(a) for a in (row.aliases or [])],
            identifiers=[
                EntityIdentifier(
                    entity_id=row.id,
                    namespace=i.namespace,
                    value=i.value,
                    ontology_version=i.ontology_version,
                    source=IdentifierSource(i.source),
                    score=i.score,
                    resolved_at=i.resolved_at,
                )
                for i in row.identifiers
            ],
        )
