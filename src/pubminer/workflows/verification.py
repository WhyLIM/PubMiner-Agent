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
    member_count: int = 1

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
            "member_count": self.member_count,
        }


def claim_cluster_key(claim: Claim) -> tuple:
    """聚簇键：subject 实体（未解析退回签名首段）+ predicate + object 归一化。

    direction 不参与——HIGH/LOW 是语义不同的结论。
    """
    subject = (
        f"ent:{claim.subject_entity_id}"
        if claim.subject_entity_id
        else f"sig:{(claim.canonical_signature.split(' | ')[0] or '').lower()}"
    )
    obj = (
        f"ent:{claim.object_entity_id}"
        if claim.object_entity_id
        else f"val:{(claim.object_value or '').strip().upper()}"
    )
    return (subject, claim.predicate.value if hasattr(claim.predicate, 'value') else str(claim.predicate), obj)


class CrossPaperVerifier:
    """对 CANDIDATE/REVIEWED claims 做跨论文极性聚合与冲突检测。"""

    def __init__(self, claim_repo: ClaimRepository) -> None:
        self.claim_repo = claim_repo

    def aggregate(self, session: Session, limit: int = 200, *, cluster: bool = True) -> list[ClaimAggregation]:
        claims = self.claim_repo.list_claims(limit=limit)
        if not cluster:
            result = [
                self.aggregate_one(claim, self.claim_repo.get_evidence(claim.id))
                for claim in claims
            ]
        else:
            groups: dict[tuple, list[Claim]] = {}
            for claim in claims:
                groups.setdefault(claim_cluster_key(claim), []).append(claim)
            result = [self.aggregate_group(members) for members in groups.values()]
        # 冲突优先，其后按证据数排序
        result.sort(key=lambda a: (not a.has_conflict, -len(a.reasons)))
        return result

    def aggregate_group(self, members: list[Claim]) -> ClaimAggregation:
        """聚合同一簇（同 subject 实体 + predicate + object 归一化）的命题。

        代表 claim 优先取 subject 已解析的（签名含真实本体编号）；
        证据计数合并，独立验证/冲突/需复核按簇内任一成立。
        """
        evidences: list[Evidence] = []
        for claim in members:
            evidences.extend(self.claim_repo.get_evidence(claim.id))
        representative = next((c for c in members if c.subject_entity_id), members[0])
        agg = self.aggregate_one(representative, evidences)
        agg.member_count = len(members)
        if len(members) > 1:
            agg.reasons = list(dict.fromkeys(agg.reasons))
            agg.reasons.insert(0, f"由 {len(members)} 条同义命题合并")
        return agg

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
        """关键问题覆盖矩阵：由会话 TaskSpec 生成多行问题（疾病/任务/验证/冲突/不确定）。"""
        aggregations = self.aggregate(session, limit=1000)
        spec = _session_task_spec(session, session_id)
        questions = self._coverage_questions(aggregations, spec)
        gaps: list[str] = []
        for agg in aggregations:
            gaps.extend(agg.reasons)
        primary = questions[0]
        return CoverageSnapshot(
            session_id=session_id,
            turn=turn,
            questions=questions,
            support_count=primary.support_count,
            contradict_count=primary.contradict_count,
            no_effect_count=primary.no_effect_count,
            independent_validation_found=primary.independent_validation_found,
            unresolved_gaps=gaps,
            recommended_next_action=None if primary.covered else "EXPAND_QUERY",
        )

    def _coverage_questions(self, aggregations, spec: dict | None) -> list[CoverageItem]:
        disease = (spec or {}).get("disease") or "目标疾病"
        task = (spec or {}).get("task") or "prognostic_biomarker"
        task_label = {"prognostic_biomarker": "预后", "diagnostic_biomarker": "诊断",
                      "predictive_biomarker": "疗效预测"}.get(str(task), "相关结局")

        def counts(items):
            return (
                sum(a.support_count for a in items),
                sum(a.contradict_count for a in items),
                sum(a.no_effect_count for a in items),
                sum(a.uncertain_count for a in items),
            )

        validated = [a for a in aggregations if a.independent_validation]
        conflicted = [a for a in aggregations if a.has_conflict]
        uncertain = [a for a in aggregations if a.uncertain_count > 0]

        s, c, n, u = counts(aggregations)
        primary = CoverageItem(
            question=f"{disease} 中标志物的{task_label}证据是否已检索并聚合",
            support_count=s, contradict_count=c, no_effect_count=n, uncertain_count=u,
            independent_validation_found=bool(validated),
        )
        primary.covered = primary.support_count > 0 and primary.independent_validation_found
        primary.note = f"共 {len(aggregations)} 条聚合命题"

        s, c, n, u = counts(validated)
        q2 = CoverageItem(
            question="是否存在独立队列验证（≥3 篇同向）",
            support_count=s, contradict_count=c, no_effect_count=n, uncertain_count=u,
            independent_validation_found=bool(validated),
        )
        q2.covered = bool(validated)
        q2.note = f"{len(validated)} 条命题达标"

        s, c, n, u = counts(conflicted)
        q3 = CoverageItem(
            question="冲突证据是否已识别并送人工复核",
            support_count=s, contradict_count=c, no_effect_count=n, uncertain_count=u,
            independent_validation_found=False,
        )
        q3.covered = all(a.needs_review for a in conflicted) if conflicted else True
        q3.note = f"{len(conflicted)} 条冲突命题" if conflicted else "未发现冲突"

        s, c, n, u = counts(uncertain)
        q4 = CoverageItem(
            question="不确定证据是否已进入人工复核队列",
            support_count=s, contradict_count=c, no_effect_count=n, uncertain_count=u,
            independent_validation_found=False,
        )
        q4.covered = all(a.needs_review for a in uncertain) if uncertain else True
        q4.note = f"{len(uncertain)} 条含不确定证据"

        return [primary, q2, q3, q4]


def _session_task_spec(session: Session, session_id: UUID) -> dict | None:
    """读取会话 TaskSpec（AskHuman 解析结果），无则返回 None。"""
    from sqlalchemy import select

    from pubminer.infrastructure.db.orm_agents import AgentSessionRow

    row = session.execute(
        select(AgentSessionRow).where(AgentSessionRow.id == session_id)
    ).scalars().first()
    return row.task_spec if row is not None else None
