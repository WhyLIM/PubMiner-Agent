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


_POLARITY_KEY = {
    "SUPPORT": "support_count",
    "CONTRADICT": "contradict_count",
    "NO_EFFECT": "no_effect_count",
    "UNCERTAIN": "uncertain_count",
}


def _empty_claim_entry(claim) -> dict:
    """claim 关联证据的极性计数条目（按 claim_id 聚合时复用）。"""
    return {
        "claim_id": str(claim.id),
        "canonical_signature": claim.canonical_signature,
        "status": claim.status,
        "predicate": claim.predicate,
        "direction": claim.direction,
        "support_count": 0,
        "contradict_count": 0,
        "no_effect_count": 0,
        "uncertain_count": 0,
    }


def _bump_claim_entry(claims_map: dict, ev, claim) -> None:
    entry = claims_map.setdefault(claim.id, _empty_claim_entry(claim))
    entry[_POLARITY_KEY[ev.polarity]] += 1


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

    def list_documents_with_evidence(self, limit: int = 100, *, session_id=None) -> list[dict]:
        """文献级聚合（轻量，不含正文）：metadata + 标识符 + 关联 claim/evidence 极性统计。

        按证据数降序；session_id 给定时仅统计该会话的 claim/evidence。
        """
        from collections import Counter

        from pubminer.infrastructure.db.orm_claims import ClaimRow, EvidenceRow

        pair_stmt = select(EvidenceRow, ClaimRow).join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
        if session_id is not None:
            pair_stmt = pair_stmt.where(ClaimRow.session_id == session_id)
        pairs = self.session.execute(pair_stmt).all()
        if session_id is not None:
            # 会话过滤：仅列出有该会话证据的文献
            doc_ids = {ev.document_id for ev, _ in pairs}
            doc_rows = [d for d in self.session.execute(select(DocumentRow)).scalars().unique().all() if d.id in doc_ids]
        else:
            doc_rows = self.session.execute(select(DocumentRow)).scalars().unique().all()

        evidence_by_doc: dict[UUID, list] = {}
        for ev, claim in pairs:
            evidence_by_doc.setdefault(ev.document_id, []).append((ev, claim))

        results: list[dict] = []
        for doc in doc_rows:
            identifiers = {i.kind: i.value for i in doc.identifiers}
            doc_evidence = evidence_by_doc.get(doc.id, [])
            polarities = Counter(ev.polarity for ev, _ in doc_evidence)
            claims_map: dict[UUID, dict] = {}
            for ev, claim in doc_evidence:
                _bump_claim_entry(claims_map, ev, claim)
            results.append(
                {
                    "document_id": str(doc.id),
                    "title": doc.title or "",
                    "journal": doc.journal or "",
                    "year": doc.year,
                    "authors": list(doc.authors or []),
                    "abstract": doc.abstract or "",
                    "pmid": identifiers.get("pmid", ""),
                    "pmcid": identifiers.get("pmcid", ""),
                    "doi": identifiers.get("doi", ""),
                    "source": doc.versions[0].source if doc.versions else "",
                    "evidence_count": len(doc_evidence),
                    "support_count": polarities.get("SUPPORT", 0),
                    "contradict_count": polarities.get("CONTRADICT", 0),
                    "no_effect_count": polarities.get("NO_EFFECT", 0),
                    "uncertain_count": polarities.get("UNCERTAIN", 0),
                    "claims": list(claims_map.values()),
                }
            )
        results.sort(key=lambda d: -d["evidence_count"])
        return results[:limit]

    def get_document_detail(self, document_id: UUID) -> dict | None:
        """文献详情：metadata + 关联 claims + 证据片段（含 canonical_text 供 span 高亮）。"""
        from collections import Counter

        from pubminer.infrastructure.db.orm_claims import ClaimRow, EvidenceRow

        row = self.session.get(DocumentRow, document_id)
        if row is None:
            return None
        pairs = self.session.execute(
            select(EvidenceRow, ClaimRow)
            .join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
            .where(EvidenceRow.document_id == document_id)
        ).all()

        identifiers = {i.kind: i.value for i in row.identifiers}
        polarities: Counter = Counter(ev.polarity for ev, _ in pairs)
        claims_map: dict[UUID, dict] = {}
        evidence_items: list[dict] = []
        version_texts: dict[UUID, str] = {}
        for ev, claim in pairs:
            _bump_claim_entry(claims_map, ev, claim)
            if ev.document_version_id not in version_texts:
                version_row = self.session.get(DocumentVersionRow, ev.document_version_id)
                version_texts[ev.document_version_id] = version_row.canonical_text if version_row else ""
            evidence_items.append(
                {
                    "evidence_id": str(ev.id),
                    "claim_id": str(claim.id),
                    "claim_signature": claim.canonical_signature,
                    "polarity": ev.polarity,
                    "section_path": ev.section_path or "",
                    "start_char": ev.span_start,
                    "end_char": ev.span_end,
                    "span_text": ev.span_text or "",
                    "review_status": ev.review_status,
                    "canonical_text": version_texts[ev.document_version_id],
                }
            )

        return {
            "document_id": str(row.id),
            "title": row.title or "",
            "journal": row.journal or "",
            "year": row.year,
            "authors": list(row.authors or []),
            "abstract": row.abstract or "",
            "pmid": identifiers.get("pmid", ""),
            "pmcid": identifiers.get("pmcid", ""),
            "doi": identifiers.get("doi", ""),
            "source": row.versions[0].source if row.versions else "",
            "evidence_count": len(pairs),
            "support_count": polarities.get("SUPPORT", 0),
            "contradict_count": polarities.get("CONTRADICT", 0),
            "no_effect_count": polarities.get("NO_EFFECT", 0),
            "uncertain_count": polarities.get("UNCERTAIN", 0),
            "claims": list(claims_map.values()),
            "evidence": evidence_items,
        }

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
