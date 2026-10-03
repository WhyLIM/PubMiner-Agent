"""跨论文验证与聚合（PR-013）。

按 canonical signature 聚类已验证证据，输出每条 claim 的极性聚合、
独立验证判定与冲突标记；覆盖矩阵按 TaskSpec 关键问题汇总。
LLM confidence 不参与聚合（只统计极性）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from pubminer.domain.agents import CoverageItem, CoverageSnapshot
from pubminer.domain.claims import Claim
from pubminer.domain.evidence import Evidence, EvidencePolarity
from pubminer.infrastructure.db.repositories.claims import ClaimRepository


@dataclass
class ClaimAggregation:
    claim_id: UUID
    canonical_signature: str
    status: str
    support_count: int = 0
    contradict_count: int = 0
    no_effect_count: int = 0
    uncertain_count: int = 0
    independent_validation: bool = False
    has_conflict: bool = False
    needs_review: bool = False
    distinct_documents: int = 0
    reasons: list[str] = field(default_factory=list)
    subject_name: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_id": str(self.claim_id),
            "canonical_signature": self.canonical_signature,
            "status": self.status,
            "support_count": self.support_count,
            "contradict_count": self.contradict_count,
            "no_effect_count": self.no_effect_count,
            "uncertain_count": self.uncertain_count,
            "independent_validation": self.independent_validation,
            "has_conflict": self.has_conflict,
            "needs_review": self.needs_review,
            "distinct_documents": self.distinct_documents,
            "reasons": self.reasons,
            "subject_name": self.subject_name,
        }


class CrossPaperVerifier:
    """对 CANDIDATE/REVIEWED claims 做跨论文极性聚合与冲突检测。"""

    def __init__(self, claim_repo: ClaimRepository) -> None:
        self.claim_repo = claim_repo

    def aggregate(self, session: Session, limit: int = 200) -> list[ClaimAggregation]:
        claims = self.claim_repo.list_claims(limit=limit)
        result = [
            self.aggregate_one(claim, self.claim_repo.get_evidence(claim.id))
            for claim in claims
        ]
        # 冲突优先，其后按证据数排序
        result.sort(key=lambda a: (not a.has_conflict, -len(a.reasons)))
        return result

    def aggregate_one(self, claim: Claim, evidences: list[Evidence]) -> ClaimAggregation:
        agg = ClaimAggregation(
            claim_id=claim.id,
            canonical_signature=claim.canonical_signature,
            status=claim.status.value,
        )
        documents: set[UUID] = set()
        for evidence in evidences:
            documents.add(evidence.document_id)
            if evidence.polarity == EvidencePolarity.SUPPORT:
                agg.support_count += 1
            elif evidence.polarity == EvidencePolarity.CONTRADICT:
                agg.contradict_count += 1
            elif evidence.polarity == EvidencePolarity.NO_EFFECT:
                agg.no_effect_count += 1
            else:
                agg.uncertain_count += 1
            if evidence.study.independent_validation or evidence.study.independent_cohort:
                agg.independent_validation = True
            if evidence.review_status == "needs_review":
                agg.needs_review = True
        agg.distinct_documents = len(documents)
        agg.has_conflict = agg.contradict_count > 0 and (agg.support_count > 0 or agg.no_effect_count > 0)
        if agg.has_conflict:
            agg.reasons.append("同一 claim 同时存在支持与相反/无效应证据")
        if not agg.independent_validation and agg.support_count > 0:
            agg.reasons.append("缺少独立队列验证")
        if agg.uncertain_count > 0:
            agg.reasons.append("存在不确定证据，需要人工复核")
        return agg

    def coverage_snapshot(self, session: Session, session_id: UUID, turn: int = 0) -> CoverageSnapshot:
        """关键问题覆盖矩阵（MVP：把聚合结果映射为单一研究问题）。"""
        aggregations = self.aggregate(session)
        item = CoverageItem(
            question=session_spec_question(session_id),
            support_count=sum(a.support_count for a in aggregations),
            contradict_count=sum(a.contradict_count for a in aggregations),
            no_effect_count=sum(a.no_effect_count for a in aggregations),
            uncertain_count=sum(a.uncertain_count for a in aggregations),
            independent_validation_found=any(a.independent_validation for a in aggregations),
        )
        item.covered = item.support_count > 0 and item.independent_validation_found
        gaps: list[str] = []
        for agg in aggregations:
            gaps.extend(agg.reasons)
        return CoverageSnapshot(
            session_id=session_id,
            turn=turn,
            questions=[item],
            support_count=item.support_count,
            contradict_count=item.contradict_count,
            no_effect_count=item.no_effect_count,
            independent_validation_found=item.independent_validation_found,
            unresolved_gaps=gaps,
            recommended_next_action=None if item.covered else "EXPAND_QUERY",
        )


def session_spec_question(session_id: UUID) -> str:
    return "核心问题：目标疾病下 biomarker 的预后作用及其独立验证"
