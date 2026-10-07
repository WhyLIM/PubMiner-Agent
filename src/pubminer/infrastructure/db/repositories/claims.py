"""Claim 仓储：候选 claim + evidence 事务性写入；signature 唯一。

不变量：创建 claim 必须至少带一条 evidence（No Evidence No Claim）。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pubminer.domain.claims import Claim, ClaimStatus
from pubminer.domain.evidence import Evidence
from pubminer.infrastructure.db.orm_claims import ClaimRow, EvidenceRow


class NoEvidenceError(ValueError):
    """试图创建没有 evidence 的 claim（设计红线）。"""


class ClaimRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_signature(
        self, canonical_signature: str, context_schema_version: str = "biomarker-v1"
    ) -> Claim | None:
        stmt = select(ClaimRow).where(
            ClaimRow.canonical_signature == canonical_signature,
            ClaimRow.context_schema_version == context_schema_version,
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        return self._claim_from_row(row) if row else None

    def create_candidate_claim(self, claim: Claim, evidences: list[Evidence]) -> Claim:
        """事务性创建 CANDIDATE claim + 绑定 evidence。重复 signature 返回已有 claim。"""
        if claim.status != ClaimStatus.CANDIDATE:
            raise ValueError("repository may only create CANDIDATE claims (ADR-008)")
        if not evidences:
            raise NoEvidenceError("no-evidence-no-claim: evidence list is empty")

        existing = self.find_by_signature(
            claim.canonical_signature, claim.context.schema_version
        )
        if existing is not None:
            return existing

        row = ClaimRow(
            id=claim.id,
            subject_entity_id=claim.subject_entity_id,
            object_entity_id=claim.object_entity_id,
            object_value=claim.object_value,
            predicate=claim.predicate.value,
            direction=claim.direction.value,
            context=claim.context.model_dump(mode="json"),
            context_schema_version=claim.context.schema_version,
            canonical_signature=claim.canonical_signature,
            status=claim.status.value,
            version=claim.version,
            created_by=claim.created_by,
            session_id=claim.session_id,
            created_at=claim.created_at,
            updated_at=claim.updated_at,
        )
        for evidence in evidences:
            row.evidence_items.append(self._evidence_row(evidence))
        self.session.add(row)
        self.session.flush()
        return self._claim_from_row(row)

    def add_evidence(self, claim_id: UUID, evidences: list[Evidence]) -> int:
        """为已有 claim 追加证据（新 pipeline 可并存）。"""
        claim_row = self.session.get(ClaimRow, claim_id)
        if claim_row is None:
            raise LookupError(f"claim {claim_id} not found")
        for evidence in evidences:
            claim_row.evidence_items.append(self._evidence_row(evidence))
        self.session.flush()
        return len(evidences)

    def mark_evidence_needs_review(self, claim_id: UUID) -> None:
        """把该 claim 的全部证据标记 needs_review（resolver 未决等场景）。"""
        for row in self.session.execute(
            select(EvidenceRow).where(EvidenceRow.claim_id == claim_id)
        ).scalars():
            row.review_status = "needs_review"
        self.session.flush()

    def get_evidence(self, claim_id: UUID) -> list[Evidence]:
        stmt = select(EvidenceRow).where(EvidenceRow.claim_id == claim_id)
        rows = self.session.execute(stmt).scalars().all()
        return [self._evidence_from_row(r) for r in rows]

    def get(self, claim_id: UUID) -> Claim | None:
        row = self.session.get(ClaimRow, claim_id)
        return self._claim_from_row(row) if row else None

    def list_claims(
        self, statuses: list[str] | None = None, limit: int = 200,
        *, session_id=None,
    ) -> list[Claim]:
        from sqlalchemy import select

        stmt = select(ClaimRow).limit(limit)
        if statuses:
            stmt = stmt.where(ClaimRow.status.in_(statuses))
        if session_id is not None:
            stmt = stmt.where(ClaimRow.session_id == session_id)
        rows = self.session.execute(stmt).scalars().all()
        return [self._claim_from_row(row) for row in rows]

    # ---------------------------------------------------------------- mapping

    @staticmethod
    def _evidence_row(evidence: Evidence) -> EvidenceRow:
        return EvidenceRow(
            id=evidence.id,
            claim_id=evidence.claim_id,
            document_id=evidence.document_id,
            document_version_id=evidence.document_version_id,
            passage_id=evidence.passage_id,
            polarity=evidence.polarity.value,
            span_text=evidence.span.text,
            span_start=evidence.span.start_char,
            span_end=evidence.span.end_char,
            span_text_hash=evidence.span.text_hash,
            section_path=evidence.span.section_path,
            study=evidence.study.model_dump(mode="json"),
            statistics=(
                evidence.statistics.model_dump(mode="json") if evidence.statistics else None
            ),
            extraction_run_id=evidence.extraction_run_id,
            review_status=evidence.review_status,
            created_at=evidence.created_at,
        )

    @staticmethod
    def _evidence_from_row(row: EvidenceRow) -> Evidence:
        from pubminer.domain.documents import EvidenceSpan
        from pubminer.domain.evidence import EvidencePolarity, Statistics, StudyAttributes

        return Evidence(
            id=row.id,
            claim_id=row.claim_id,
            document_id=row.document_id,
            document_version_id=row.document_version_id,
            passage_id=row.passage_id,
            span=EvidenceSpan(
                document_version_id=row.document_version_id,
                passage_id=row.passage_id,
                section_path=row.section_path,
                start_char=row.span_start,
                end_char=row.span_end,
                text=row.span_text,
                text_hash=row.span_text_hash,
            ),
            polarity=EvidencePolarity(row.polarity),
            study=StudyAttributes.model_validate(row.study or {}),
            statistics=Statistics.model_validate(row.statistics) if row.statistics else None,
            extraction_run_id=row.extraction_run_id,
            review_status=row.review_status,
            created_at=row.created_at,
        )

    def _claim_from_row(self, row: ClaimRow) -> Claim:
        from pubminer.domain.claims import ClaimContext, Direction, Predicate

        return Claim(
            id=row.id,
            subject_entity_id=row.subject_entity_id,
            object_entity_id=row.object_entity_id,
            object_value=row.object_value,
            predicate=Predicate(row.predicate),
            direction=Direction(row.direction),
            context=ClaimContext.model_validate(row.context or {}),
            canonical_signature=row.canonical_signature,
            status=ClaimStatus(row.status),
            version=row.version,
            created_by=row.created_by,
            session_id=row.session_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
