"""领域与抽取字段 Schema 校验模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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
    def check_non_empty(self) -> "DomainSchemaModel":
        if not self.entity_types:
            raise ValueError("entity_types 不得为空")
        if not self.predicates:
            raise ValueError("predicates 不得为空")
        if not self.directions:
            raise ValueError("directions 不得为空")
        return self


class ExtractionFieldsModel(BaseModel):
    name: str = Field(..., description="schema 标识符", pattern=r"^[a-z][a-z0-9-]*$")
    description: str = Field(..., description="描述")
    version: str = Field("1.0", description="版本号")
    fields: list[FieldSpecModel] = Field(default_factory=list)
    export_mappings: dict[str, dict[str, str]] = Field(default_factory=dict)
