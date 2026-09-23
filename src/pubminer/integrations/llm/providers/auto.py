"""协议协商 provider：Responses API → Anthropic Messages → Chat Completions。

策略（默认 auto）：
1. 按优先级依次尝试候选协议（base URL 取自厂商注册表或显式覆盖）；
2. `ProtocolNotSupportedError`（404/405/501）→ 降级到下一协议并记录原因；
3. 首个成功协议被粘住（后续调用直达，不再重复探测）；
4. 其他错误（401/429/500 等）不属于"协议不支持"，直接抛出，不掩盖。
可用 `PUBMINER_LLM_PROTOCOL=responses|anthropic|completions` 固定协议。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

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
PROTOCOL_PRIORITY_FALLBACK = PROTOCOL_PRIORITY


class AutoProtocolProvider(LLMProvider):
    """按优先级协商协议并粘住首个可用协议。

    Args:
        base_url: 所有协议共用的 base（与 base_urls 二选一）。
        base_urls: 协议 -> base url（厂商注册表形态，各协议端点不同时使用）。
        extras: 协议 -> 需要合并进该协议 provider 构造参数的字典
            （如 {"completions": {"extra_body": ...}, "responses": {"reasoning": ...},
              "anthropic": {"thinking_mode": "on", "thinking_budget": 4096}}）。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str | None = None,
        base_urls: Mapping[str, str] | None = None,
        protocol: str = "auto",
        transport: Callable[[str], Any] | None = None,
        extras: Mapping[str, dict] | None = None,
    ) -> None:
        self.requested = protocol.strip().lower()
        if self.requested not in ("auto", *PROTOCOL_PRIORITY):
            raise LLMError(
                f"unknown PUBMINER_LLM_PROTOCOL: {protocol} (use auto|responses|anthropic|completions)"
            )
        order = [self.requested] if self.requested != "auto" else list(PROTOCOL_PRIORITY)
        base_urls = base_urls or {}
        extras = extras or {}
        self._transport_for = transport or (lambda _name: None)

        self._candidates: list[Any] = []
        self._candidate_names: list[str] = []
        for p in order:
            base = base_urls.get(p) or base_url
            if not base:
                continue  # 该协议没有可用端点，跳过
            ctor_kwargs: dict[str, Any] = {"base_url": base, "transport": self._transport_for(p)}
            ctor_kwargs.update(extras.get(p, {}))
            self._candidates.append(PROTOCOL_CLASSES[p](api_key, model, **ctor_kwargs))
            self._candidate_names.append(p)
        if not self._candidates:
            raise LLMError("no LLM protocol candidate has a base URL")
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
        for candidate, name in zip(self._candidates, self._candidate_names):
            try:
                result = candidate.complete(system, user, temperature=temperature, max_tokens=max_tokens)
            except ProtocolNotSupportedError as exc:
                self.downgrade_log.append(f"{name}: {exc}")
                logger.info("protocol %s unavailable, downgrading: %s", name, exc)
                last_error = exc
                continue
            self._active = candidate
            logger.info("LLM protocol negotiated: %s", candidate.name)
            return result
        raise last_error or LLMError("no LLM protocol candidate available")


def build_llm_provider(
    api_key: str,
    model: str | None = None,
    *,
    vendor: str | None = None,
    base_url: str | None = None,
    protocol: str = "auto",
    thinking: str = "default",
    thinking_budget: int = 4096,
    transport: Callable[[str], Any] | None = None,
):
    """按厂商注册表构造 provider。

    base 解析优先级：显式 base_url > 厂商注册表按协议的默认端点。
    vendor/base_url 都未提供时默认厂商 zhipu。thinking: default|off|on。
    """
    from pubminer.integrations.llm.vendors import VENDORS, thinking_payload

    vendor_key = vendor or ("custom" if base_url else "zhipu")
    spec = VENDORS.get(vendor_key)
    if spec is None:
        raise LLMError(f"unknown PUBMINER_LLM_VENDOR: {vendor_key} "
                       f"(available: {', '.join(sorted(VENDORS))})")
    model = model or spec.default_model
    if not model:
        raise LLMError(f"vendor {vendor_key} requires an explicit model")

    # base 解析：厂商注册表按协议默认；显式 base_url 覆盖全部协议
    base_urls = dict(spec.base_urls)
    if base_url:
        base_urls = {p: base_url for p in (base_urls or PROTOCOL_PRIORITY)}

    extras: dict[str, dict] = {}
    payload = thinking_payload(spec.thinking_style, thinking)
    if payload:
        if "thinking" in payload and spec.thinking_style == "zhipu" and protocol in ("auto", "completions"):
            extras.setdefault("completions", {})["extra_body"] = payload
        if spec.thinking_style == "openai":
            if protocol in ("auto", "responses"):
                extras.setdefault("responses", {}).update(
                    {k: v for k, v in payload.items() if k == "reasoning"}
                )
            if protocol in ("auto", "completions"):
                extras.setdefault("completions", {}).update(
                    {k: v for k, v in payload.items() if k == "reasoning_effort"}
                )
    if spec.thinking_style == "anthropic" and thinking in ("default", "on"):
        extras["anthropic"] = {"thinking_mode": "on", "thinking_budget": thinking_budget}

    if protocol != "auto":
        # 固定协议：直接返回对应 provider（无需协商包装）
        base = base_urls.get(protocol) or base_url
        if not base:
            raise LLMError(f"vendor {vendor_key} does not provide a {protocol} endpoint")
        return PROTOCOL_CLASSES[protocol](
            api_key, model, base_url=base, transport=transport, **extras.get(protocol, {})
        )

    if len(base_urls) == 1:
        # 单协议厂商：直接返回对应 provider
        p, base = next(iter(base_urls.items()))
        return PROTOCOL_CLASSES[p](api_key, model, base_url=base, transport=transport, **extras.get(p, {}))

    return AutoProtocolProvider(
        api_key, model, base_urls=base_urls, protocol=protocol,
        transport=transport, extras=extras,
    )
