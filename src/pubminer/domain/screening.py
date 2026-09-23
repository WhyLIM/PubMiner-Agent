"""Screening 决策模型（设计文档 §8.3）。

Screening 优先降低 false negative；模型 confidence 只用于队列优先级，
不用于事实判断。RELEVANT 进入抽取；UNCERTAIN 请求全文或人工复核。
"""
from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ScreeningLabel(str, Enum):
    RELEVANT = "RELEVANT"
    IRRELEVANT = "IRRELEVANT"
    UNCERTAIN = "UNCERTAIN"


class ScreeningDecision(BaseModel):
    document_id: UUID
    label: ScreeningLabel
    confidence: float = Field(0.5, ge=0, le=1, description="仅用于排序，不是事实真值")
    reasons: list[str] = Field(default_factory=list)
    study_type: str | None = None
    needs_fulltext: bool = False
    screener: str = Field("llm@screening-v1", description="screener 名称@prompt 版本")
