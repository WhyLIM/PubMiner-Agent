"""Chat Completions 兼容 provider（兜底协议：POST {base}/chat/completions）。

用于尚未提供 Responses / Anthropic 协议的端点（Gemini 兼容层、
Qwen 兼容模式、旧版聚合网关等）。
"""
from __future__ import annotations

from typing import Any

from pubminer.application.ports import LLMUsage
from pubminer.integrations.llm.providers.base import HttpJsonProvider


class OpenAICompatibleProvider(HttpJsonProvider):
    name = "completions"
    path = "/chat/completions"

    def _payload(self, system: str, user: str, *, temperature: float, max_tokens: int) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    def _parse(self, payload: dict[str, Any]) -> tuple[str, LLMUsage]:
        text = payload["choices"][0]["message"]["content"] or ""
        usage_raw = payload.get("usage", {}) or {}
        usage = LLMUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
        )
        return text, usage
