"""协议协商 provider：Responses API → Anthropic Messages → Chat Completions。

策略（默认 auto）：
1. 按优先级依次尝试候选协议；
2. `ProtocolNotSupportedError`（404/405/501）→ 降级到下一协议并记录原因；
3. 首个成功协议被粘住（后续调用直达，不再重复探测）；
4. 其他错误（401/429/500 等）不属于"协议不支持"，直接抛出，不掩盖。
可用 `PUBMINER_LLM_PROTOCOL=responses|anthropic|completions` 固定协议。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from pubminer.application.ports import LLMError, LLMProvider
from pubminer.integrations.llm.providers.anthropic import AnthropicProvider
from pubminer.integrations.llm.providers.base import ProtocolNotSupportedError
from pubminer.integrations.llm.providers.openai_compat import OpenAICompatibleProvider
from pubminer.integrations.llm.providers.responses_api import ResponsesApiProvider

logger = logging.getLogger("pubminer.llm.auto")

PROTOCOL_CLASSES: dict[str, type] = {
    "responses": ResponsesApiProvider,
    "anthropic": AnthropicProvider,
    "completions": OpenAICompatibleProvider,
}
PROTOCOL_PRIORITY = ("responses", "anthropic", "completions")


class AutoProtocolProvider(LLMProvider):
    """按优先级协商协议并粘住首个可用协议。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str,
        protocol: str = "auto",
        transport: Callable[[str], Any] | None = None,
    ) -> None:
        self.requested = protocol.strip().lower()
        if self.requested not in ("auto", *PROTOCOL_PRIORITY):
            raise LLMError(
                f"unknown PUBMINER_LLM_PROTOCOL: {protocol} (use auto|responses|anthropic|completions)"
            )
        order = (
            [self.requested]
            if self.requested != "auto"
            else list(PROTOCOL_PRIORITY)
        )
        # transport 工厂：每个候选协议独立注入（测试用 MockTransport）
        self._transport_for = transport or (lambda _name: None)
        self._candidates = [
            PROTOCOL_CLASSES[p](api_key, model, base_url=base_url, transport=self._transport_for(p))
            for p in order
        ]
        self._active = None
        self.downgrade_log: list[str] = []

    @property
    def name(self) -> str:
        return self._active.name if self._active else "auto-negotiating"

    @property
    def model(self) -> str:
        return self._candidates[0].model

    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int):
        if self._active is not None:
            return self._active.complete(system, user, temperature=temperature, max_tokens=max_tokens)
        last_error: LLMError | None = None
        for candidate in self._candidates:
            try:
                result = candidate.complete(system, user, temperature=temperature, max_tokens=max_tokens)
            except ProtocolNotSupportedError as exc:
                self.downgrade_log.append(f"{candidate.name}: {exc}")
                logger.info("protocol %s unavailable, downgrading: %s", candidate.name, exc)
                last_error = exc
                continue
            self._active = candidate
            logger.info("LLM protocol negotiated: %s", candidate.name)
            return result
        raise last_error or LLMError("no LLM protocol candidate available")


def build_llm_provider(
    api_key: str,
    model: str,
    *,
    base_url: str,
    protocol: str = "auto",
    transport: Callable[[str], Any] | None = None,
):
    """按配置构造 provider；auto = Responses → Anthropic → completions。"""
    if protocol == "auto":
        return AutoProtocolProvider(api_key, model, base_url=base_url, protocol="auto", transport=transport)
    return PROTOCOL_CLASSES[protocol](api_key, model, base_url=base_url, transport=transport)
