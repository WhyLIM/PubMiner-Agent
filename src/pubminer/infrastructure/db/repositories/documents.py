"""Document 仓储：标识符去重 upsert + 版本追加。"""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from pubminer.domain.documents import (
    Document,
    DocumentIdentifier,
    DocumentVersion,
)
from pubminer.infrastructure.db.orm_documents import (
    DocumentIdentifierRow,
    DocumentRow,
    DocumentVersionRow,
    PassageRow,
)


def _identifier_values(doc: Document) -> dict[str, str]:
    return {i.kind: i.normalized().value for i in doc.identifiers}


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------------------------------------------------------------- query

    def find_id_by_identifier(self, kind: str, value: str) -> UUID | None:
        stmt = select(DocumentIdentifierRow.document_id).where(
            DocumentIdentifierRow.kind == kind, DocumentIdentifierRow.value == value
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get(self, document_id: UUID) -> Document | None:
        row = self.session.get(DocumentRow, document_id)
        return self._to_domain(row) if row else None

    # ---------------------------------------------------------------- write

    def upsert_document(self, doc: Document) -> Document:
        """按 identity_key 去重写入 document 元数据（不写版本）。"""
        by_kind = _identifier_values(doc)
        for kind in ("pmid", "pmcid", "doi"):
            value = by_kind.get(kind)
            if not value:
                continue
            existing = self.find_id_by_identifier(kind, value)
            if existing:
                found = self.get(existing)
                if found is not None:
                    return found

        row = DocumentRow(
            id=doc.id,
            title=doc.title,
            journal=doc.journal,
            year=doc.year,
            authors=list(doc.authors),
            abstract=doc.abstract,
            publication_types=list(doc.publication_types),
            created_at=doc.created_at,
        )
        for kind, value in by_kind.items():
            row.identifiers.append(DocumentIdentifierRow(kind=kind, value=value))
        self.session.add(row)
        self.session.flush()
        return self._to_domain(row)

    def add_document_version(
        self,
        document_id: UUID,
        version: DocumentVersion,
        section_spans: list[tuple[str, int, int]],
    ) -> UUID:
        """追加不可变版本并落 passages。

        Args:
            section_spans: [(section_path, start_char, end_char)]，相对
                version.canonical_text；文本按 span 从 canonical_text 切片，
                保证与 text_hash 一致。
        重复 content_version 由唯一约束拒绝。
        """
        document_row = self.session.get(DocumentRow, document_id)
        if document_row is None:
            raise LookupError(f"document {document_id} not found")
        row = DocumentVersionRow(
            id=version.id,
            content_version=version.content_version,
            title=version.title,
            canonical_text=version.canonical_text,
            text_hash=version.text_hash,
            license=version.license,
            source=version.source,
            retrieved_at=version.retrieved_at,
        )
        # 通过 relationship 追加：保证 identity map 内集合与数据库一致
        document_row.versions.append(row)
        self.session.flush()
        self.session.add_all(
            PassageRow(
                id=uuid4(),
                document_version_id=row.id,
                section_path=path,
                text=version.canonical_text[start:end],
                start_char=start,
                end_char=end,
                text_hash=version.text_hash,
            )
            for path, start, end in section_spans
        )
        self.session.flush()
        return row.id

    def get_or_add_version(
        self,
        document_id: UUID,
        version: DocumentVersion,
        section_spans: list[tuple[str, int, int]],
    ) -> UUID:
        """幂等追加：同 (document, content_version) 已存在时返回既有版本 id。"""
        existing = self.session.execute(
            select(DocumentVersionRow).where(
                DocumentVersionRow.document_id == document_id,
                DocumentVersionRow.content_version == version.content_version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id
        return self.add_document_version(document_id, version, section_spans)

    def get_passage(self, document_version_id: UUID, passage_id: UUID) -> PassageRow | None:
        return self.session.get(PassageRow, passage_id)

    # ---------------------------------------------------------------- mapping

    def _to_domain(self, row: DocumentRow) -> Document:
        return Document(
            id=row.id,
            identifiers=[DocumentIdentifier(kind=i.kind, value=i.value) for i in row.identifiers],
            title=row.title,
            journal=row.journal,
            year=row.year,
            authors=list(row.authors or []),
            abstract=row.abstract,
            publication_types=list(row.publication_types or []),
            versions=[
                DocumentVersion(
                    id=v.id,
                    document_id=row.id,
                    content_version=v.content_version,
                    title=v.title,
                    canonical_text=v.canonical_text,
                    text_hash=v.text_hash,
                    license=v.license,
                    source=v.source,
                    retrieved_at=v.retrieved_at,
                )
                for v in row.versions
            ],
            created_at=row.created_at,
        )
