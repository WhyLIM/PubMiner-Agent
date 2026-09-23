"""Task/Run 聚合：确定性 workflow 的执行记录。可重放、可恢复。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    SCREENING = "SCREENING"
    EXTRACTING = "EXTRACTING"
    NORMALIZING = "NORMALIZING"
    VERIFYING = "VERIFYING"
    REVIEW_READY = "REVIEW_READY"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunStepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class ToolCallStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DENIED = "DENIED"


class Task(BaseModel):
    """一个研究/重处理任务。状态转换受 workflow 定义约束。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID | None = Field(None, description="来源 Agent 会话")
    kind: str = Field("mining", description="mining | reprocessing | import")
    request: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.CREATED
    priority: int = 0
    owner: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())


class RunStep(BaseModel):
    """run 中的一个 step attempt。"""

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    step_type: str = Field(..., description="PLAN|SEARCH|HYDRATE|SCREEN|EXTRACT|NORMALIZE|VERIFY|AGGREGATE")
    attempt: int = 1
    status: RunStepStatus = RunStepStatus.PENDING
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Run(BaseModel):
    """一次执行：绑定 pipeline release，记录成本与 trace。"""

    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    pipeline_release: str = Field(..., description="model+prompt+schema+rule 组合版本")
    status: str = Field("running", description="running | succeeded | failed | cancelled")
    cost_usd: float = 0.0
    trace_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now())
    ended_at: datetime | None = None
    steps: list[RunStep] = Field(default_factory=list)


class ToolCall(BaseModel):
    """一次 typed tool 调用的审计记录。"""

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID | None = None
    session_id: UUID | None = None
    action_id: UUID | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    result_count: int | None = None
    status: ToolCallStatus = ToolCallStatus.PENDING
    error: str | None = None
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now())
