"""AgentSession 聚合：目标、TaskSpec、计划版本、行动、覆盖、预算、停止。

不变量（§6.3）：
- 每个 AgentAction 必须指向触发它的 plan step；
- AgentMessage 是交互记录，不是事实源；可发布知识只能来自绑定
  EvidenceSpan 的领域对象；
- 会话状态与停止原因必须显式可重放。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

AGENT_ACTION_TYPES = (
    "PLAN", "SEARCH", "HYDRATE", "SCREEN", "EXTRACT", "NORMALIZE",
    "VERIFY", "EXPAND_QUERY", "ASK_HUMAN", "SYNTHESIZE", "STOP",
)


class AgentStatus(str, Enum):
    DRAFT = "DRAFT"
    CLARIFYING = "CLARIFYING"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    PAUSED = "PAUSED"
    SYNTHESIZING = "SYNTHESIZING"
    COMPLETED = "COMPLETED"
    LIMITED = "LIMITED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StopReasonKind(str, Enum):
    NORMAL = "NORMAL"          # 覆盖充分 / 边际收益低
    LIMIT_TURNS = "LIMIT_TURNS"
    LIMIT_COST = "LIMIT_COST"
    LIMIT_SOURCES = "LIMIT_SOURCES"
    LIMIT_TIME = "LIMIT_TIME"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SCHEMA_UNSATISFIABLE = "SCHEMA_UNSATISFIABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    USER_CANCELLED = "USER_CANCELLED"


class StopReason(BaseModel):
    kind: StopReasonKind
    message: str = ""
    finished_at: datetime = Field(default_factory=lambda: datetime.now())

    @property
    def is_normal(self) -> bool:
        return self.kind == StopReasonKind.NORMAL

    @property
    def is_limited(self) -> bool:
        return self.kind in {
            StopReasonKind.LIMIT_TURNS,
            StopReasonKind.LIMIT_COST,
            StopReasonKind.LIMIT_SOURCES,
            StopReasonKind.LIMIT_TIME,
        }


class Budget(BaseModel):
    """会话预算上限（用户可设）。"""

    max_turns: int = Field(30, ge=1)
    max_articles: int = Field(200, ge=1)
    max_cost_usd: float = Field(20.0, ge=0)
    max_search_runs: int = Field(20, ge=1)


class BudgetState(BaseModel):
    """已消耗预算。"""

    turns: int = 0
    articles_considered: int = 0
    cost_usd: float = 0.0
    search_runs: int = 0

    def add(self, delta: "BudgetDelta") -> "BudgetState":
        self.turns += delta.turns
        self.articles_considered += delta.articles
        self.cost_usd = round(self.cost_usd + delta.cost_usd, 6)
        self.search_runs += delta.search_runs
        return self


class BudgetDelta(BaseModel):
    turns: int = 1
    articles: int = 0
    cost_usd: float = 0.0
    search_runs: int = 0


class TaskSpec(BaseModel):
    """结构化研究目标（澄清完成后的契约）。schema_version 绑定 TaskSchema。"""

    schema_name: str = "biomarker_evidence"
    schema_version: str = "biomarker-v1"
    goal_text: str = Field(..., description="用户原始目标")
    disease: str | None = None
    task: str | None = Field(None, description="如 prognostic_biomarker")
    biomarker_subject: str | None = None
    validation_requirement: str | None = Field(None, description="如 independent_validation")
    publication_types: list[str] = Field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    language: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)

    def missing_required_fields(self) -> list[str]:
        """biomarker-v1 必填约束：disease、task；其余按需澄清。"""
        missing = []
        if not self.disease:
            missing.append("disease")
        if not self.task:
            missing.append("task")
        return missing


class PlanStep(BaseModel):
    id: str
    action_type: str = Field(..., description="AGENT_ACTION_TYPES 之一")
    description: str = ""
    search_intent: str | None = Field(None, description="SEARCH 步骤的检索意图描述")
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_information_gain: str = ""
    status: str = Field("pending", description="pending | done | failed | skipped")

    @model_validator(mode="after")
    def _check_action_type(self) -> "PlanStep":
        if self.action_type not in AGENT_ACTION_TYPES:
            raise ValueError(f"unknown action type: {self.action_type}")
        return self


class Plan(BaseModel):
    """版本化研究计划。用户可修改/批准。"""

    version: int = 1
    steps: list[PlanStep] = Field(default_factory=list)
    rationale: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    approved_by_human: bool = False


class AgentAction(BaseModel):
    """一次受控行动（附录 A 契约的持久化形态）。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    turn: int = Field(..., ge=0)
    plan_version: int
    step_id: str | None = Field(None, description="触发的 plan step；STOP/ASK_HUMAN 可为空")
    action_type: str
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_information_gain: str = ""
    result_summary: str = ""
    budget_delta: BudgetDelta = Field(default_factory=BudgetDelta)
    status: str = Field("pending", description="pending | succeeded | failed | rejected_by_policy")
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    @model_validator(mode="after")
    def _check_action_type(self) -> "AgentAction":
        if self.action_type not in AGENT_ACTION_TYPES:
            raise ValueError(f"unknown action type: {self.action_type}")
        return self


class AgentMessage(BaseModel):
    """会话交互记录（非事实源）。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    role: Literal["user", "agent", "system"]
    content: str
    kind: str = Field("text", description="text | clarification | plan | report")
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class CoverageItem(BaseModel):
    """一个关键问题的覆盖状态。"""

    question: str
    support_count: int = 0
    contradict_count: int = 0
    no_effect_count: int = 0
    uncertain_count: int = 0
    independent_validation_found: bool = False
    covered: bool = False
    note: str = ""


class CoverageSnapshot(BaseModel):
    """附录 A 契约。"""

    session_id: UUID
    turn: int = 0
    questions: list[CoverageItem] = Field(default_factory=list)
    support_count: int = 0
    contradict_count: int = 0
    no_effect_count: int = 0
    independent_validation_found: bool = False
    unresolved_gaps: list[str] = Field(default_factory=list)
    recommended_next_action: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class AgentSession(BaseModel):
    """聚合根。状态机见附录 B。"""

    id: UUID = Field(default_factory=uuid4)
    user_id: str = "anonymous"
    goal: str
    task_spec: TaskSpec | None = None
    status: AgentStatus = AgentStatus.DRAFT
    budget: Budget = Field(default_factory=Budget)
    budget_state: BudgetState = Field(default_factory=BudgetState)
    plans: list[Plan] = Field(default_factory=list, description="按 version 追加，不覆盖")
    actions: list[AgentAction] = Field(default_factory=list)
    stop_reason: StopReason | None = None
    current_plan_version: int = 0
    turn: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

    @property
    def latest_plan(self) -> Plan | None:
        return self.plans[-1] if self.plans else None

    @model_validator(mode="after")
    def _check(self) -> "AgentSession":
        if not self.goal.strip():
            raise ValueError("session goal must be non-empty")
        return self
