"""Anthropic Messages API provider（POST {base}/v1/messages）。

支持：Anthropic 原生（base=https://api.anthropic.com）及各厂商的
Anthropic 兼容端点（智谱 /api/anthropic、Moonshot、MiniMax /anthropic）。
max_tokens 在该协议中必填；鉴权用 x-api-key 而非 Bearer。
"""
from __future__ import annotations

from typing import Any

from pubminer.application.ports import LLMUsage
from pubminer.integrations.llm.providers.base import HttpJsonProvider


class AnthropicProvider(HttpJsonProvider):
    name = "anthropic"
    path = "/v1/messages"
    extra_headers = {"anthropic-version": "2023-06-01"}

    def __init__(self, api_key: str, model: str, *, base_url: str, thinking_mode: str = "default",
                 thinking_budget: int = 4096, **kwargs) -> None:
        super().__init__(api_key, model, base_url=base_url, **kwargs)
        # Anthropic 鉴权头：x-api-key（移除基类默认的 Bearer 头）
        self._client.headers["x-api-key"] = api_key
        self._client.headers.pop("Authorization", None)
        # 官方约束：thinking.enabled 时 temperature 必须为 1（或省略），
        # 且 budget_tokens < max_tokens
        self.thinking_mode = thinking_mode
        self.thinking_budget = max(1024, int(thinking_budget))

    def _payload(self, system: str, user: str, *, temperature: float, max_tokens: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max(1, max_tokens),
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            payload["system"] = system
        if self.thinking_mode == "on":
            payload["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
            payload["max_tokens"] = max(payload["max_tokens"], self.thinking_budget + 1024)
            # 启用思考时不得携带 temperature
        elif temperature is not None:
            payload["temperature"] = temperature
        return payload

    def _parse(self, payload: dict[str, Any]) -> tuple[str, LLMUsage]:
        parts = [
            block.get("text", "")
            for block in payload.get("content", []) or []
            if block.get("type") == "text"
        ]
        text = "".join(parts)
        usage_raw = payload.get("usage", {}) or {}
        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("input_tokens", 0) or 0),
            completion_tokens=int(usage_raw.get("output_tokens", 0) or 0),
        )
        return text, usage
