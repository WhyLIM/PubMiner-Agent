"""OpenAI 兼容 chat provider：GLM/DeepSeek/OpenAI 等统一走 /chat/completions。

红线：只用 httpx 且始终校验证书；厂商协议细节不越过 integrations 边界。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from pubminer.application.ports import LLMError, LLMUsage

logger = logging.getLogger("pubminer.llm.openai-compat")


class OpenAICompatibleProvider:
    name = "openai-compat"

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4-flash",
        *,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("OpenAICompatibleProvider requires an API key")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def complete(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> tuple[str, LLMUsage]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        start = time.perf_counter()
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(
                f"LLM endpoint returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload: dict[str, Any] = response.json()
            text = payload["choices"][0]["message"]["content"] or ""
            usage_raw = payload.get("usage", {}) or {}
            usage = LLMUsage(
                prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise LLMError(f"unexpected LLM response shape: {exc}") from exc

        logger.debug(
            "openai-compat complete %.0fms tokens=%d",
            (time.perf_counter() - start) * 1000,
            usage.total_tokens,
        )
        return text, usage
