"""领域 schema 生成/校准适配器。

generate：自然语言描述 → LLM 生成完整领域 JSON + 抽取字段定义；
calibrate：用户粘贴的（可能不完整的）JSON → LLM 解析校准补齐 → 可校验格式。
两者都经 DomainSchemaModel 强校验后返回；LLM 输出不合法时重试一次。
"""
from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from pubminer.application.ports import LLMRequest
from pubminer.workflows.schema_validation import DomainSchemaModel

logger = logging.getLogger("pubminer.schema_generate")

_MAX_REPAIR_ATTEMPTS = 2


def _legal_enums_text() -> str:
    """从 domain 枚举动态生成合法值清单（注入 prompt，避免硬编码漂移）。"""
    from pubminer.domain.claims import Direction, Predicate
    from pubminer.domain.entities import EntityType

    return (
        f"- predicates 值只能取：{[p.value for p in Predicate]}\n"
        f"- entity_types 键只能取：{[e.value for e in EntityType]}\n"
        f"- directions 值只能取：{[d.value for d in Direction]}"
    )


def _extract_json(text: str) -> dict:
    """从 LLM 输出提取 JSON 对象（容忍 ```json 围栏）。"""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("no JSON object in LLM output")


def _validate_domain(payload: dict) -> dict:
    """强校验并规范化领域定义；不合法抛 ValueError（信息可直接给用户）。"""
    model = DomainSchemaModel(**payload)
    data = model.model_dump()
    # object_label 是规范模型之外的可选扩展（驱动图谱图例），校验通过后放回
    if payload.get("object_label"):
        data["object_label"] = str(payload["object_label"])
    return data


class SchemaGenerateAdapter:
    def __init__(self, llm, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def _generate_raw(self, instruction: str, user_payload: str | None = None) -> tuple[dict, dict | None]:
        prompt = self.prompts.get("schema-generate", "v1")
        render_vars: dict[str, str] = {
            "description": instruction,
            "existing_json": "",
            "previous_feedback": "",
            "enums": _legal_enums_text(),
        }
        if user_payload is not None:
            render_vars["existing_json"] = (
                "EXISTING JSON FROM USER (calibrate this):\n" + user_payload
            )
        last_error: Exception | None = None
        for _ in range(_MAX_REPAIR_ATTEMPTS + 1):
            response = self.llm.generate(
                LLMRequest(
                    purpose="schema-generate",
                    prompt_version="schema-generate@v1",
                    system=prompt.system,
                    user=prompt.render(**render_vars),
                    temperature=0.1,
                    max_tokens=4096,
                    metadata={"schema_version": "schema-generate-v1"},
                )
            )
            try:
                raw = _extract_json(response.text or "")
                domain = _validate_domain(raw.get("domain", raw))
                extraction_fields = raw.get("extraction_fields")
                if extraction_fields:
                    from pubminer.workflows.schema_validation import ExtractionFieldsModel

                    extraction_fields = ExtractionFieldsModel(**extraction_fields).model_dump()
                return domain, extraction_fields
            except (ValueError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                render_vars["previous_feedback"] = (
                    "PREVIOUS ATTEMPT FAILED VALIDATION:\n"
                    f"{type(exc).__name__}: {exc}\n"
                    f"PREVIOUS OUTPUT:\n{(response.text or '')[:4000]}"
                )
        raise ValueError(f"LLM 生成的领域定义无法通过校验：{last_error}")

    def generate(self, description: str) -> tuple[dict, dict | None]:
        """自然语言描述 → (领域 JSON, 抽取字段 JSON|None)。"""
        return self._generate_raw(description)

    def calibrate(self, domain_json: dict) -> tuple[dict, dict | None]:
        """用户粘贴的 JSON → LLM 解析校准补齐 → 可校验格式。"""
        instruction = (
            "The user pasted a possibly incomplete or non-conforming domain definition JSON. "
            "Parse it, fix the format to fully conform to the rules (add missing required fields, "
            "normalize naming, add a sensible object_label), keep the user's intent, and output the "
            "calibrated JSON."
        )
        payload = json.dumps(domain_json, ensure_ascii=False)
        return self._generate_raw(instruction, user_payload=payload)

