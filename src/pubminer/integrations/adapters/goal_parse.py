"""目标解析适配器：自然语言研究目标 → TaskSpec 字段 + 检索式 + 歧义检测。"""
from __future__ import annotations

import json
import logging

from pubminer.application.ports import LLMError, LLMRequest

logger = logging.getLogger("pubminer.adapters.goal_parse")


class GoalParseError(LLMError):
    pass


class GoalParseAdapter:
    """goal-parse/v1 prompt → 增强解析结果。

    返回 dict 包含：
    - disease/task/year_from/year_to/validation_requirement：TaskSpec 字段
    - search_intents: [{name, query}] 初始检索式（LLM 生成，用户可修改）
    - clarification: {needed: bool, question: str|null} 歧义检测结果
    """

    def __init__(self, llm, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def parse(self, goal: str, *, prior_context: str | None = None) -> dict:
        from pydantic import BaseModel

        class _SearchIntent(BaseModel):
            name: str
            query: str
            explanation: str = ""

        class _Clarification(BaseModel):
            needed: bool = False
            question: str | None = None

        class _GoalFields(BaseModel):
            disease: str | None = None
            task: str | None = None
            year_from: int | None = None
            year_to: int | None = None
            validation_requirement: str | None = None
            search_intents: list[_SearchIntent] = []
            clarification: _Clarification = _Clarification()

        prompt = self.prompts.get("goal-parse", "v1")
        render_vars: dict[str, str] = {"goal": goal}
        if prior_context:
            # 注入先验上下文（需要 prompt.md 支持）
            render_vars["prior_context"] = prior_context
            render_vars["prior_context_block"] = f"PRIOR CONTEXT:\n{prior_context}"
        response = self.llm.structured_generate(
            LLMRequest(
                purpose="goal-parse",
                prompt_version="goal-parse@v1",
                system=prompt.system,
                user=self._render(prompt.text, render_vars),
                temperature=0.0,
                max_tokens=1024,
                metadata={"schema_version": "goal-parse-v1"},
            ),
            _GoalFields,
        )
        raw = response.text
        payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])

        result: dict = {}
        for key in ("disease", "task", "year_from", "year_to", "validation_requirement"):
            value = payload.get(key)
            if value is not None:
                result[key] = value

        result["search_intents"] = [
            {"name": si.get("name", f"intent_{i}"), "query": si.get("query", ""),
             "explanation": si.get("explanation", "")}
            for i, si in enumerate(payload.get("search_intents", []))
            if si.get("query")
        ]
        clarification = payload.get("clarification", {}) or {}
        result["clarification"] = {
            "needed": bool(clarification.get("needed", False)),
            "question": clarification.get("question"),
        }
        return result

    @staticmethod
    def _render(template: str, variables: dict[str, str]) -> str:
        out = template
        for key, value in variables.items():
            out = out.replace("{{" + key + "}}", value)
            out = out.replace("{{#if " + key + "}}", "").replace("{{/if}}", "")
        # 清理未匹配的条件块
        import re

        out = re.sub(r"\{\{#if \w+\}\}.*?\{\{/if\}\}", "", out, flags=re.DOTALL)
        return out
