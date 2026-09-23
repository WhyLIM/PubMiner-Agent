"""OpenAI Responses API provider（POST {base}/responses）。

支持：OpenAI、Azure OpenAI、DeepSeek(V4+)、智谱 GLM(/api/paas/v4/responses)、
Moonshot Kimi(/v1) 等已接入 Responses 协议的端点。
"""
from __future__ import annotations

from typing import Any


from pubminer.application.ports import LLMUsage
from pubminer.integrations.llm.providers.base import HttpJsonProvider


class ResponsesApiProvider(HttpJsonProvider):
    name = "responses"
    path = "/responses"

    def __init__(self, api_key: str, model: str, *, base_url: str = "https://open.bigmodel.cn/api/paas/v4",
                 timeout: float = 60.0, transport: Any = None,
                 reasoning: dict[str, Any] | None = None) -> None:
        super().__init__(api_key, model, base_url=base_url, timeout=timeout, transport=transport)
        # OpenAI 风格思考控制：{"effort": "minimal"|"low"|"medium"|"high"}；其余厂商留空
        self.reasoning = reasoning or {}

    def _payload(self, system: str, user: str, *, temperature: float, max_tokens: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": user,
            "max_output_tokens": max_tokens,
        }
        if system:
            payload["instructions"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        payload.update(self.reasoning)
        return payload

    def _parse(self, payload: dict[str, Any]) -> tuple[str, LLMUsage]:
        # 兼容便捷字段与完整 output 数组两种形态
        if isinstance(payload.get("output_text"), str):
            text = payload["output_text"]
        else:
            parts: list[str] = []
            for item in payload.get("output", []) or []:
                if item.get("type") not in ("message", "reasoning"):
                    continue
                for block in item.get("content", []) or []:
                    if block.get("type") == "output_text" and block.get("text"):
                        parts.append(block["text"])
            text = "".join(parts)
        if payload.get("status") not in (None, "completed"):
            raise ValueError(f"response status={payload.get('status')}")
        usage_raw = payload.get("usage", {}) or {}
        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("input_tokens", 0) or 0),
            completion_tokens=int(usage_raw.get("output_tokens", 0) or 0),
        )
        return text, usage
