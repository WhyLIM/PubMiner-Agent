"""API schemas：请求/响应模型（前端生成 client 的契约源）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    goal: str = Field(min_length=1, description="自然语言研究目标")
    user_id: str = "anonymous"
    limits: dict[str, Any] = Field(default_factory=dict)


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    next: str


class PostMessageRequest(BaseModel):
    role: str = Field("user", description="user | agent | system")
    content: str = Field(min_length=1)
    kind: str = "text"
    payload: dict[str, Any] = Field(default_factory=dict)


class PostMessageResponse(BaseModel):
    message_id: str
    ok: bool = True


class BindTaskSpecRequest(BaseModel):
    disease: str | None = None
    task: str | None = None
    validation_requirement: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    publication_types: list[str] = Field(default_factory=list)


class TaskSpecResponse(BaseModel):
    schema_name: str
    schema_version: str
    disease: str | None = None
    task: str | None = None
    validation_requirement: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    missing_required_fields: list[str] = Field(default_factory=list)


class PlanStepResponse(BaseModel):
    id: str
    action_type: str
    description: str = ""
    search_intent: str | None = None
    status: str = "pending"


class PlanResponse(BaseModel):
    version: int
    rationale: str = ""
    steps: list[PlanStepResponse] = Field(default_factory=list)
    approved_by_human: bool = False


class ActionResponse(BaseModel):
    id: str
    turn: int
    action_type: str
    tool_name: str | None = None
    status: str
    result_summary: str = ""
    created_at: str


class SessionResponse(BaseModel):
    session_id: str
    goal: str
    status: str
    task_spec: TaskSpecResponse | None = None
    plans: list[PlanResponse] = Field(default_factory=list)
    current_plan_version: int = 0
    budget: dict[str, Any] = Field(default_factory=dict)
    budget_state: dict[str, Any] = Field(default_factory=dict)
    stop_reason: dict[str, Any] | None = None
    actions: list[ActionResponse] = Field(default_factory=list)
    turn: int = 0


class SubmitPlanRequest(BaseModel):
    rationale: str = ""
    steps: list[PlanStepResponse] = Field(default_factory=list)


class ApprovePlanRequest(BaseModel):
    plan_version: int


class CreateTaskRequest(BaseModel):
    session_id: str | None = None
    intents: list[dict[str, Any]] = Field(
        default_factory=lambda: [{"name": "discovery", "query": "", "max_results": 50}]
    )


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str


class TaskStepResponse(BaseModel):
    index: int
    type: str
    status: str
    error: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    session_id: str | None = None
    status: str
    steps: list[TaskStepResponse] = Field(default_factory=list)


class ClaimResponse(BaseModel):
    claim_id: str
    canonical_signature: str
    status: str
    predicate: str
    direction: str
    evidence_count: int = 0
    polarities: dict[str, int] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: dict[str, Any]
    request_id: str


class AgentEventItem(BaseModel):
    seq: int
    turn: int
    action_type: str
    tool_name: str | None = None
    status: str
    summary: str = ""


class SessionEventsResponse(BaseModel):
    events: list[AgentEventItem] = Field(default_factory=list)
    next_since: int = 0


class ClaimsResponse(BaseModel):
    claims: list[ClaimResponse] = Field(default_factory=list)


class ClaimEvidenceSpan(BaseModel):
    document_version_id: str
    passage_id: str
    section_path: str = ""
    start_char: int
    end_char: int
    text: str


class ClaimEvidenceItem(BaseModel):
    evidence_id: str
    polarity: str
    span: ClaimEvidenceSpan
    study: dict[str, Any] = Field(default_factory=dict)
    statistics: dict[str, Any] | None = None
    review_status: str = "pending"
    document_version_id: str = ""
    document_title: str = ""
    canonical_text: str = Field("", description="span 所在的固定 canonical text，用于 UI 高亮定位")


class ClaimEvidenceResponse(BaseModel):
    claim_id: str
    canonical_signature: str
    evidence: list[ClaimEvidenceItem] = Field(default_factory=list)


class AggregationItem(BaseModel):
    claim_id: str
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
    reasons: list[str] = Field(default_factory=list)


class CoverageQuestionItem(BaseModel):
    question: str
    support_count: int = 0
    contradict_count: int = 0
    no_effect_count: int = 0
    uncertain_count: int = 0
    independent_validation_found: bool = False
    covered: bool = False


class CoverageResponse(BaseModel):
    session_id: str
    questions: list[CoverageQuestionItem] = Field(default_factory=list)
    support_count: int = 0
    contradict_count: int = 0
    no_effect_count: int = 0
    independent_validation_found: bool = False
    unresolved_gaps: list[str] = Field(default_factory=list)
    recommended_next_action: str | None = None


class ReviewQueueItem(BaseModel):
    claim_id: str
    canonical_signature: str
    status: str
    version: int = 1
    priority: str
    reasons: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    polarities: dict[str, int] = Field(default_factory=dict)


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem] = Field(default_factory=list)


class ReviewDecisionRequest(BaseModel):
    claim_id: str
    decision: str = Field(..., description="ACCEPT | EDIT_ACCEPT | REJECT | NEEDS_REVIEW")
    reviewer_id: str
    reason: str = Field(min_length=1)
    expected_version: int = Field(..., description="乐观锁：审核者看到的 claim 版本")
    revision: dict[str, Any] = Field(default_factory=dict, description="EDIT_ACCEPT 的修订字段")


class ReviewRecordItem(BaseModel):
    review_id: str
    target_id: str
    decision: str
    reviewer_id: str
    reason: str
    created_at: str


class ReviewDecisionResponse(BaseModel):
    ok: bool
    claim_status: str
    claim_version: int
    review_id: str


class AggregationsResponse(BaseModel):
    aggregations: list[AggregationItem] = Field(default_factory=list)


class TaskListItem(BaseModel):
    task_id: str
    session_id: str | None = None
    kind: str = "mining"
    status: str
    created_at: str


class TaskListResponse(BaseModel):
    tasks: list[TaskListItem] = Field(default_factory=list)


class SessionListItem(BaseModel):
    session_id: str
    goal: str
    status: str
    created_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem] = Field(default_factory=list)


class RunSessionRequest(BaseModel):
    disease: str | None = None
    task: str = "prognostic_biomarker"
    year_from: int | None = None
    max_results: int = Field(5, ge=1, le=100)
    screen_criteria: str | None = None


class RunSessionResponse(BaseModel):
    task_id: str
    status: str
    plan_version: int


class SearchIntentItem(BaseModel):
    name: str
    query: str
    explanation: str = ""


class ParseGoalResponse(BaseModel):
    bound: bool = False
    fields: dict[str, Any] = Field(default_factory=dict)
    search_intents: list[SearchIntentItem] = Field(default_factory=list)
    clarification: dict[str, Any] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, description="用户对澄清问题的回答")


class SaveSearchIntentsRequest(BaseModel):
    search_intents: list[SearchIntentItem] = Field(min_length=1)
