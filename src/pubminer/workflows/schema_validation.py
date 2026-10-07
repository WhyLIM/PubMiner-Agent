"""领域与抽取字段 Schema 校验模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from pubminer.domain.claims import Direction, Predicate
from pubminer.domain.entities import EntityType

#: 领域定义中的枚举合法值（与 domain 模型强一致；生成/校准/保存共用同一门禁）
LEGAL_PREDICATES = sorted(p.value for p in Predicate)
LEGAL_ENTITY_TYPES = sorted(e.value for e in EntityType)
LEGAL_DIRECTIONS = sorted(d.value for d in Direction)


class FieldSpecModel(BaseModel):
    key: str = Field(..., description="字段键（存入 JSON 的键名）", pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., description="中文展示名")
    type: str = Field("string", description="string | text | boolean | number")
    hint: str = Field("", description="LLM 抽取提示")


class DomainSchemaModel(BaseModel):
    name: str = Field(..., description="唯一标识（小写+连字符）", pattern=r"^[a-z][a-z0-9-]*$")
    display: str = Field(..., description="展示名称")
    entity_label: str = Field(..., description="抽取对象统称")
    default_task: str = Field("", description="默认任务类型")
    entity_types: dict[str, str] = Field(default_factory=dict, description="类型键 → 展示名")
    predicates: dict[str, str] = Field(default_factory=dict, description="role_key → 谓词值")
    directions: list[str] = Field(default_factory=list)
    outcome_hints: list[str] = Field(default_factory=list)
    signature_template: str = Field(
        "{subject} | {predicate} | {object} | {direction}",
        description="签名模板，必须含 {subject} {predicate} {object}",
    )
    verification: dict[str, Any] = Field(default_factory=dict)
    screen_hints: str = Field("")
    extraction_fields_schema: str | None = None
    export_mappings: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("name 不得含空格")
        return v

    @field_validator("signature_template")
    @classmethod
    def template_has_required_placeholders(cls, v: str) -> str:
        for p in ("{subject}", "{predicate}", "{object}"):
            if p not in v:
                raise ValueError(f"signature_template 缺少 {p}")
        return v

    @model_validator(mode="after")
    def check_enum_mappings(self) -> "DomainSchemaModel":
        """领域值必须能映射到 domain 枚举，否则管线使用时会崩溃。"""
        if not self.entity_types:
            raise ValueError("entity_types 不得为空")
        if not self.predicates:
            raise ValueError("predicates 不得为空")
        if not self.directions:
            raise ValueError("directions 不得为空")

        bad_types = [k for k in self.entity_types if k not in LEGAL_ENTITY_TYPES]
        if bad_types:
            raise ValueError(
                f"entity_types 含非法键 {bad_types}；合法值：{LEGAL_ENTITY_TYPES}"
            )
        bad_preds = sorted({v for v in self.predicates.values() if v not in LEGAL_PREDICATES})
        if bad_preds:
            raise ValueError(
                f"predicates 含非法值 {bad_preds}；合法值：{LEGAL_PREDICATES}"
            )
        bad_dirs = sorted({d for d in self.directions if d not in LEGAL_DIRECTIONS})
        if bad_dirs:
            raise ValueError(
                f"directions 含非法值 {bad_dirs}；合法值：{LEGAL_DIRECTIONS}"
            )
        return self


class ExtractionFieldsModel(BaseModel):
    name: str = Field(..., description="schema 标识符", pattern=r"^[a-z][a-z0-9-]*$")
    description: str = Field(..., description="描述")
    version: str = Field("1.0", description="版本号")
    fields: list[FieldSpecModel] = Field(default_factory=list)
    export_mappings: dict[str, dict[str, str]] = Field(default_factory=dict)
