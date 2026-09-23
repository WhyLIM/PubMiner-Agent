"""Review 聚合：人审决定与修订。修改追加记录，不覆盖模型输出。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ReviewDecision(str, Enum):
    ACCEPT = "ACCEPT"
    EDIT_ACCEPT = "EDIT_ACCEPT"
    REJECT = "REJECT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReviewTargetType(str, Enum):
    CLAIM = "claim"
    EVIDENCE = "evidence"
    RESOLUTION = "resolution"


class ReviewTarget(BaseModel):
    type: ReviewTargetType
    id: UUID


class Review(BaseModel):
    """一条审核记录。EDIT_ACCEPT 必须带 after（修订后载荷）。

    before 保存模型原输出快照；reason 必填，保证决定可追溯。
    """

    id: UUID = Field(default_factory=uuid4)
    target: ReviewTarget
    decision: ReviewDecision
    reviewer_id: str
    before: dict[str, Any] = Field(default_factory=dict, description="模型原输出快照")
    after: dict[str, Any] | None = Field(None, description="EDIT_ACCEPT 时的修订载荷")
    reason: str
    priority: str = Field("normal", description="low_confidence | conflict | high_impact | random_qa | normal")
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    @model_validator(mode="after")
    def _check(self) -> "Review":
        if not self.reason.strip():
            raise ValueError("review decision requires a reason (traceability)")
        if self.decision == ReviewDecision.EDIT_ACCEPT and not self.after:
            raise ValueError("EDIT_ACCEPT requires the revised payload")
        if self.after is not None and self.decision != ReviewDecision.EDIT_ACCEPT:
            raise ValueError("revision payload only valid with EDIT_ACCEPT")
        return self
