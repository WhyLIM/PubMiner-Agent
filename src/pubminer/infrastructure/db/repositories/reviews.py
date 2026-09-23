"""Review 仓储：审核记录追加与队列。"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pubminer.domain.reviews import Review
from pubminer.infrastructure.db.orm_reviews import ReviewRow


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, review: Review) -> Review:
        self.session.add(
            ReviewRow(
                id=review.id,
                target_type=review.target.type.value,
                target_id=review.target.id,
                decision=review.decision.value,
                reviewer_id=review.reviewer_id,
                before=review.before,
                after=review.after,
                reason=review.reason,
                priority=review.priority,
                created_at=review.created_at,
            )
        )
        self.session.flush()
        return review

    def list_for_target(self, target_type: str, target_id: UUID) -> list[Review]:
        rows = self.session.execute(
            select(ReviewRow)
            .where(ReviewRow.target_type == target_type, ReviewRow.target_id == target_id)
            .order_by(ReviewRow.created_at)
        ).scalars().all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: ReviewRow) -> Review:
        return Review(
            id=row.id,
            target=ReviewTargetWithFields(type=row.target_type, id=row.target_id),
            decision=row.decision,
            reviewer_id=row.reviewer_id,
            before=row.before or {},
            after=row.after,
            reason=row.reason,
            priority=row.priority,
            created_at=row.created_at,
        )


def ReviewTargetWithFields(type: str, id: UUID):  # noqa: N802 — 局部映射辅助
    from pubminer.domain.reviews import ReviewTarget

    return ReviewTarget(type=type, id=id)
