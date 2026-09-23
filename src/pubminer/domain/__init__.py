"""领域层：纯 Pydantic v2 模型与枚举（设计文档 §6 领域模型、附录 A/B）。

不变量在此层强制：
- No Evidence No Claim：Claim 必须至少绑定一条 passage 级 Evidence；
- Evidence 必须指向固定 document version 的 passage（offset + text_hash）；
- canonical identifier 只能带 resolver 来源（ADR-006）；
- 审核修改追加记录，不覆盖模型输出。
"""
from pubminer.domain.agents import (
    AGENT_ACTION_TYPES,
    AgentAction,
    AgentMessage,
    AgentSession,
    AgentStatus,
    Budget,
    BudgetDelta,
    BudgetState,
    CoverageItem,
    CoverageSnapshot,
    Plan,
    PlanStep,
    StopReason,
    StopReasonKind,
    TaskSpec,
)
from pubminer.domain.claims import (
    CLAIM_CONTEXT_SCHEMA_VERSION,
    Claim,
    ClaimContext,
    ClaimStatus,
    Direction,
    Predicate,
    build_canonical_signature,
)
from pubminer.domain.documents import (
    Document,
    DocumentIdentifier,
    DocumentVersion,
    EvidenceSpan,
    PassageRef,
)
from pubminer.domain.entities import (
    EntityType,
    Entity,
    EntityAlias,
    EntityIdentifier,
    IdentifierSource,
    Mention,
    Resolution,
)
from pubminer.domain.evidence import (
    AnalysisType,
    BiomarkerEvidence,
    Evidence,
    EvidencePolarity,
    Population,
    Statistics,
    StudyDesign,
    VerificationResult,
)
from pubminer.domain.reviews import Review, ReviewDecision, ReviewTarget, ReviewTargetType
from pubminer.domain.tasks import (
    Run,
    RunStep,
    RunStepStatus,
    Task,
    TaskStatus,
    ToolCall,
    ToolCallStatus,
)

__all__ = [
    "AGENT_ACTION_TYPES", "AgentAction", "AgentMessage", "AgentSession", "AgentStatus",
    "Budget", "BudgetDelta", "BudgetState", "CoverageItem", "CoverageSnapshot",
    "Plan", "PlanStep", "StopReason", "StopReasonKind", "TaskSpec",
    "CLAIM_CONTEXT_SCHEMA_VERSION", "Claim", "ClaimContext", "ClaimStatus",
    "Direction", "Predicate", "build_canonical_signature",
    "Document", "DocumentIdentifier", "DocumentVersion", "EvidenceSpan", "PassageRef",
    "EntityType", "Entity", "EntityAlias", "EntityIdentifier", "IdentifierSource",
    "Mention", "Resolution",
    "AnalysisType", "BiomarkerEvidence", "Evidence", "EvidencePolarity", "Population",
    "Statistics", "StudyDesign", "VerificationResult",
    "Review", "ReviewDecision", "ReviewTarget", "ReviewTargetType",
    "Run", "RunStep", "RunStepStatus", "Task", "TaskStatus", "ToolCall", "ToolCallStatus",
]
