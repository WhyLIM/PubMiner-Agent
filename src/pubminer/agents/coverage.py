"""覆盖评估：从 evidence 统计更新 CoverageSnapshot 与边际收益判断。"""
from __future__ import annotations

from dataclasses import dataclass

from pubminer.domain.agents import CoverageItem, CoverageSnapshot
from pubminer.domain.evidence import Evidence, EvidencePolarity


@dataclass
class MarginalGain:
    """边际收益启发式：新增证据相对已有证据的增量比例。"""

    previous_total: int
    current_total: int

    @property
    def ratio(self) -> float:
        if self.previous_total <= 0:
            return 1.0
        return max(0.0, (self.current_total - self.previous_total) / self.previous_total)

    def is_low(self, threshold: float = 0.05) -> bool:
        return self.ratio < threshold


class CoverageEvaluator:
    """维护关键问题覆盖矩阵（MVP：单问题 = TaskSpec 的核心问题）。"""

    def __init__(self, questions: list[str] | None = None) -> None:
        self.questions = questions or []

    def snapshot(
        self,
        session_id,  # UUID
        turn: int,
        evidences: list[Evidence],
        *,
        independent_validation_found: bool | None = None,
        unresolved_gaps: list[str] | None = None,
    ) -> CoverageSnapshot:
        """按极性统计证据，生成覆盖快照。

        单问题覆盖判定：至少 1 条 SUPPORT 且（无未决缺口）；
        independent_validation 未显式给出时，从证据属性推断。
        """
        per_question: dict[str, CoverageItem] = {
            q: CoverageItem(question=q) for q in self.questions
        }
        if self.questions:
            item = per_question[self.questions[0]]
        else:
            item = CoverageItem(question="(implicit research question)")
            per_question[item.question] = item

        for evidence in evidences:
            if evidence.polarity == EvidencePolarity.SUPPORT:
                item.support_count += 1
            elif evidence.polarity == EvidencePolarity.CONTRADICT:
                item.contradict_count += 1
            elif evidence.polarity == EvidencePolarity.NO_EFFECT:
                item.no_effect_count += 1
            else:
                item.uncertain_count += 1
            if evidence.study.independent_validation or evidence.study.independent_cohort:
                item.independent_validation_found = True

        if independent_validation_found is not None:
            item.independent_validation_found = independent_validation_found
        item.covered = item.support_count > 0 and not item.contradict_count > 0

        totals = CoverageSnapshot(
            session_id=session_id,
            turn=turn,
            questions=list(per_question.values()),
            support_count=sum(i.support_count for i in per_question.values()),
            contradict_count=sum(i.contradict_count for i in per_question.values()),
            no_effect_count=sum(i.no_effect_count for i in per_question.values()),
            independent_validation_found=any(
                i.independent_validation_found for i in per_question.values()
            ),
            unresolved_gaps=unresolved_gaps or [],
        )
        if not totals.independent_validation_found and totals.support_count > 0:
            totals.unresolved_gaps.append("independent validation not yet found")
        totals.recommended_next_action = (
            None if not totals.unresolved_gaps else "EXPAND_QUERY"
        )
        return totals
