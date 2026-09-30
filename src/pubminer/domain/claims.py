"""Claim 聚合：规范化命题 + canonical signature + 发布状态机。

不变量（ADR-003 / §6.4）：
- Claim 不等同某篇论文的结论；同一 claim 可有支持/反对/无效应/不确定证据；
- canonical_signature 是语义聚类键（唯一索引在 DB 层）；
- Agent 只能创建 CANDIDATE；APPROVED/PUBLISHED 需要显式角色；
- 已发布记录的修订通过新 version 完成。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

CLAIM_CONTEXT_SCHEMA_VERSION = "biomarker-v1"


class Predicate(str, Enum):
    PROGNOSTIC = "PROGNOSTIC"
    DIAGNOSTIC = "DIAGNOSTIC"
    PREDICTIVE = "PREDICTIVE"
    THERAPEUTIC = "THERAPEUTIC"
    ASSOCIATED = "ASSOCIATED"
    CAUSATIVE = "CAUSATIVE"


class Direction(str, Enum):
    """表达方向（对预后类：高/低表达对应更差/更好结局）。"""

    HIGH = "HIGH"
    LOW = "LOW"
    OVEREXPRESSION = "OVEREXPRESSION"
    UNDEREXPRESSION = "UNDEREXPRESSION"
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    AMPLIFICATION = "AMPLIFICATION"
    DELETION = "DELETION"
    MUTATION = "MUTATION"
    UNSPECIFIED = "UNSPECIFIED"


class ClaimStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


class ClaimContext(BaseModel):
    """限定 claim 适用的疾病/亚型/结局等上下文。"""

    disease_entity_id: UUID | None = None
    disease_name: str = ""
    disease_mesh_id: str | None = Field(None, description="resolver 返回的 MeSH id（如 D010190），用于跨库聚类")
    outcome: str | None = Field(None, description="如 overall_survival / progression_free_survival")
    subtype: str | None = None
    assay: str | None = Field(None, description="如 IHC / qPCR")
    threshold: str | None = None
    schema_version: str = CLAIM_CONTEXT_SCHEMA_VERSION

    def signature_parts(self) -> list[str]:
        parts = [
            self.disease_name.upper().replace(" ", "_") if self.disease_name else "DISEASE:UNSPECIFIED",
        ]
        if self.outcome:
            parts.append(self.outcome.upper().replace(" ", "_"))
        if self.subtype:
            parts.append(self.subtype.upper().replace(" ", "_"))
        return parts


def build_canonical_signature(
    *,
    subject_identifier: str,
    predicate: Predicate | str,
    object_identifier: str | None = None,
    object_value: str | None = None,
    direction: Direction | str | None = None,
    context: ClaimContext | None = None,
) -> str:
    """构造 canonical signature：稳定、可复算的语义聚类键。

    subject 优先用 entity identifier（NAMESPACE:VALUE），不依赖表面名称。
    """
    subject = subject_identifier.strip().upper()
    predicate_token = (predicate.value if isinstance(predicate, Predicate) else str(predicate)).upper()
    if object_identifier:
        object_token = object_identifier.strip().upper()
    elif object_value:
        object_token = object_value.strip().upper().replace(" ", "_")
    else:
        object_token = "UNSPECIFIED"
    direction_token = (
        (direction.value if isinstance(direction, Direction) else str(direction)).upper()
        if direction
        else "UNSPECIFIED"
    )
    context_token = "|".join(context.signature_parts()) if context else ""
    tokens = [subject, predicate_token, object_token, direction_token]
    if context_token:
        tokens.append(context_token)
    return " | ".join(t for t in tokens if t)


class Claim(BaseModel):
    """一条规范化命题。创建时必须为 CANDIDATE 且绑定证据（由应用层校验）。"""

    id: UUID = Field(default_factory=uuid4)
    subject_entity_id: UUID
    predicate: Predicate
    object_entity_id: UUID | None = None
    object_value: str | None = None
    direction: Direction = Direction.UNSPECIFIED
    context: ClaimContext = Field(default_factory=ClaimContext)
    canonical_signature: str = ""
    status: ClaimStatus = ClaimStatus.CANDIDATE
    version: int = Field(1, description="业务版本；published 后修订产生新 version")
    created_by: str = Field("agent", description="agent | curator:user_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

    @model_validator(mode="after")
    def _check(self) -> "Claim":
        if self.object_entity_id is None and not self.object_value:
            raise ValueError("claim requires object entity or object value")
        if not self.canonical_signature:
            subject = f"ENTITY:{self.subject_entity_id}"
            object_id = f"ENTITY:{self.object_entity_id}" if self.object_entity_id else None
            self.canonical_signature = build_canonical_signature(
                subject_identifier=subject,
                predicate=self.predicate,
                object_identifier=object_id,
                object_value=self.object_value,
                direction=self.direction,
                context=self.context,
            )
        return self

    def transition(self, target: ClaimStatus, *, actor: str) -> "Claim":
        """状态机迁移（§6.4）：

            CANDIDATE -> REVIEWED -> APPROVED -> PUBLISHED -> DEPRECATED
                 |            |
                 +-> REJECTED +-> REJECTED / 回退 CANDIDATE（需修订）
        Agent 只能产生 CANDIDATE；APPROVED/PUBLISHED 迁移必须由具备权限的
        人工角色触发（由应用层校验角色）。
        """
        allowed: dict[ClaimStatus, set[ClaimStatus]] = {
            ClaimStatus.CANDIDATE: {ClaimStatus.REVIEWED, ClaimStatus.REJECTED},
            ClaimStatus.REVIEWED: {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.CANDIDATE},
            ClaimStatus.APPROVED: {ClaimStatus.PUBLISHED, ClaimStatus.REVIEWED},
            ClaimStatus.PUBLISHED: {ClaimStatus.DEPRECATED},
            ClaimStatus.REJECTED: set(),
            ClaimStatus.DEPRECATED: set(),
        }
        if target not in allowed[self.status]:
            raise ValueError(f"illegal claim transition {self.status.value} -> {target.value}")
        self.status = target
        self.updated_at = datetime.now()
        return self
