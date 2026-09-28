"""目标解析适配器：自然语言研究目标 → TaskSpec 字段（LLM 结构化输出）。"""
from __future__ import annotations

import logging

from pubminer.application.ports import LLMError, LLMRequest

logger = logging.getLogger("pubminer.adapters.goal_parse")


class GoalParseError(LLMError):
    pass


class GoalParseAdapter:
    """goal-parse/v1 prompt → {disease, task, year_from, year_to, validation_requirement}。"""

    def __init__(self, llm, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def parse(self, goal: str) -> dict:
        from pydantic import BaseModel

        class _GoalFields(BaseModel):
            disease: str | None = None
            task: str | None = None
            year_from: int | None = None
            year_to: int | None = None
            validation_requirement: str | None = None

        prompt = self.prompts.get("goal-parse", "v1")
        response = self.llm.structured_generate(
            LLMRequest(
                purpose="goal-parse",
                prompt_version="goal-parse@v1",
                system=prompt.system,
                user=prompt.render(goal=goal),
                temperature=0.0,
                max_tokens=512,
                metadata={"schema_version": "goal-parse-v1"},
            ),
            _GoalFields,
        )
        import json

        payload = json.loads(response.text[response.text.find("{") : response.text.rfind("}") + 1])
        fields: dict = {}
        for key in ("disease", "task", "year_from", "year_to", "validation_requirement"):
            value = payload.get(key)
            if value is not None:
                fields[key] = value
        if not fields:
            raise GoalParseError("goal did not yield any structured fields")
        return fields
