"""厂商注册表与 thinking 参数映射测试（按官方文档核对，2026-09）。"""
from __future__ import annotations

import pytest

from pubminer.integrations.llm.providers import (
    AnthropicProvider,
    ResponsesApiProvider,
    build_llm_provider,
)
from pubminer.integrations.llm.vendors import VENDORS, thinking_payload


class TestVendorRegistry:
    def test_all_vendors_present(self):
        for key in ("zhipu", "zhipu-coding", "zai", "deepseek", "openai",
                    "anthropic", "moonshot", "minimax", "qwen", "custom"):
            assert key in VENDORS, key

    def test_zhipu_bases_per_protocol(self):
        spec = VENDORS["zhipu"]
        assert spec.base_urls["responses"] == "https://open.bigmodel.cn/api/paas/v4"
        assert spec.base_urls["anthropic"] == "https://open.bigmodel.cn/api/anthropic"

    def test_anthropic_vendor_has_only_anthropic_base(self):
        spec = VENDORS["anthropic"]
        assert set(spec.base_urls) == {"anthropic"}

    def test_unknown_vendor_rejected(self):
        with pytest.raises(Exception, match="unknown PUBMINER_LLM_VENDOR"):
            build_llm_provider("k", vendor="nope")


class TestThinkingPayload:
    def test_zhipu_style(self):
        assert thinking_payload("zhipu", "off") == {"thinking": {"type": "disabled"}}
        assert thinking_payload("zhipu", "on") == {"thinking": {"type": "enabled"}}
        assert thinking_payload("zhipu", "default") == {}

    def test_qwen_style(self):
        assert thinking_payload("qwen", "off") == {"enable_thinking": False}
        assert thinking_payload("qwen", "on") == {"enable_thinking": True}

    def test_openai_style_per_protocol(self):
        assert thinking_payload("openai", "off", protocol="completions") == {"reasoning_effort": "minimal"}
        assert thinking_payload("openai", "on", protocol="completions") == {"reasoning_effort": "medium"}
        assert thinking_payload("openai", "on", protocol="responses") == {"reasoning": {"effort": "medium"}}
        assert thinking_payload("openai", "default") == {}

    def test_none_style(self):
        assert thinking_payload("none", "off") == {}


class TestBuildWithVendor:
    def test_zhipu_thinking_off_wires_completions_extra_body(self):
        from pubminer.integrations.llm.providers.auto import AutoProtocolProvider

        provider = build_llm_provider("k", vendor="zhipu", thinking="off")
        assert isinstance(provider, AutoProtocolProvider)
        completions = next(c for c in provider._candidates if c.name == "completions")
        assert completions.extra_body == {"thinking": {"type": "disabled"}}
        # responses 候选不注入 zhipu thinking（形态未定义）
        responses = next(c for c in provider._candidates if c.name == "responses")
        assert responses.reasoning == {}

    def test_zhipu_uses_vendor_default_model_when_unset(self):
        provider = build_llm_provider("k", vendor="zhipu", thinking="off")
        assert provider.model == "glm-4-flash"

    def test_anthropic_thinking_on_adjusts_payload(self):
        provider = build_llm_provider("k", vendor="anthropic", thinking="on", thinking_budget=2048)
        assert isinstance(provider, AnthropicProvider)
        assert provider.thinking_mode == "on"
        payload = provider._payload("sys", "user", temperature=0.3, max_tokens=1024)
        assert payload["thinking"] == {"type": "enabled", "budget_tokens": 2048}
        assert "temperature" not in payload, "启用思考时必须移除 temperature"
        assert payload["max_tokens"] >= 2048 + 1024

    def test_base_url_override_beats_registry(self):
        provider = build_llm_provider(
            "k", vendor="zhipu", base_url="https://my-gateway.example/v4", thinking="off"
        )
        for candidate in provider._candidates:
            assert candidate.base_url == "https://my-gateway.example/v4"

    def test_fixed_protocol_returns_direct_provider(self):
        provider = build_llm_provider("k", vendor="zhipu", protocol="responses")
        assert isinstance(provider, ResponsesApiProvider)
        assert provider.base_url == "https://open.bigmodel.cn/api/paas/v4"
