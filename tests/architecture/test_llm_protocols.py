"""LLM 协议协商测试（离线）：Responses API 解析、Anthropic Messages、
自动降级与粘性、非协议错误不降级。
"""
from __future__ import annotations

import json

import httpx
import pytest

from pubminer.application.ports import LLMError
from pubminer.integrations.llm.providers import (
    AnthropicProvider,
    AutoProtocolProvider,
    ProtocolNotSupportedError,
    ResponsesApiProvider,
    build_llm_provider,
)


def _mock(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


class TestResponsesApiProvider:
    def test_parses_output_array_and_usage(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "status": "completed",
                "output": [
                    {"type": "reasoning", "content": []},
                    {"type": "message", "role": "assistant", "content": [
                        {"type": "output_text", "text": "answer part "},
                        {"type": "output_text", "text": "two"},
                    ]},
                ],
                "usage": {"input_tokens": 12, "output_tokens": 5},
            })

        provider = ResponsesApiProvider("k", "glm-4-flash", base_url="https://llm.example/v4", transport=_mock(handler))
        text, usage = provider.complete("be careful", "question", temperature=0.1, max_tokens=512)

        assert text == "answer part two"
        assert usage.prompt_tokens == 12 and usage.completion_tokens == 5
        assert seen["url"].endswith("/v4/responses")
        assert seen["body"]["instructions"] == "be careful"
        assert seen["body"]["input"] == "question"
        assert seen["body"]["max_output_tokens"] == 512

    def test_404_means_protocol_not_supported(self):
        provider = ResponsesApiProvider(
            "k", "m", base_url="https://llm.example/v4",
            transport=_mock(lambda request: httpx.Response(404, text="not found")),
        )
        with pytest.raises(ProtocolNotSupportedError):
            provider.complete("s", "u", temperature=0, max_tokens=16)

    def test_output_text_convenience_field(self):
        provider = ResponsesApiProvider(
            "k", "m", base_url="https://x/v4",
            transport=_mock(lambda request: httpx.Response(200, json={"output_text": "quick", "usage": {}})),
        )
        text, _ = provider.complete("s", "u", temperature=0, max_tokens=8)
        assert text == "quick"


class TestAnthropicProvider:
    def test_request_shape_and_parse(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "content": [{"type": "text", "text": "claude says"}],
                "usage": {"input_tokens": 9, "output_tokens": 4},
            })

        provider = AnthropicProvider("sk-key", "claude-x", base_url="https://api.anthropic.com", transport=_mock(handler))
        text, usage = provider.complete("system prompt", "user prompt", temperature=0.1, max_tokens=700)

        assert text == "claude says"
        assert usage.prompt_tokens == 9 and usage.completion_tokens == 4
        assert seen["url"].endswith("/v1/messages")
        assert seen["headers"].get("x-api-key") == "sk-key"
        assert seen["headers"].get("anthropic-version") == "2023-06-01"
        assert "Authorization" not in seen["headers"]
        assert seen["body"]["system"] == "system prompt"
        assert seen["body"]["max_tokens"] == 700

    def test_404_means_protocol_not_supported(self):
        provider = AnthropicProvider(
            "k", "m", base_url="https://x",
            transport=_mock(lambda request: httpx.Response(404, text="nope")),
        )
        with pytest.raises(ProtocolNotSupportedError):
            provider.complete("s", "u", temperature=0, max_tokens=16)


class TestAutoNegotiation:
    def _router(self, calls: list, *, responses_status: int, anthropic_status: int = 200, completions_status: int = 200):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            calls.append(url)
            if url.endswith("/responses"):
                if responses_status != 200:
                    return httpx.Response(responses_status, text="no responses here")
                return httpx.Response(200, json={
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "via responses"}]}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                })
            if url.endswith("/v1/messages"):
                if anthropic_status != 200:
                    return httpx.Response(anthropic_status, text="no anthropic here")
                return httpx.Response(200, json={
                    "content": [{"type": "text", "text": "via anthropic"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                })
            if url.endswith("/chat/completions"):
                if completions_status != 200:
                    return httpx.Response(completions_status, text="no completions")
                return httpx.Response(200, json={
                    "choices": [{"message": {"content": "via completions"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                })
            return httpx.Response(404, text="unknown path")

        return _mock(handler)

    def test_downgrades_responses_to_anthropic_and_sticks(self):
        calls: list = []
        provider = AutoProtocolProvider(
            "k", "m", base_url="https://gw.example",
            protocol="auto", transport=lambda name: self._router(calls, responses_status=404),
        )
        text = provider.complete("s", "u", temperature=0, max_tokens=32)[0]
        assert text == "via anthropic"
        assert provider.name == "anthropic"

        # 第二次调用直达 anthropic，不再探测 responses
        before = len(calls)
        provider.complete("s", "u2", temperature=0, max_tokens=32)
        assert len(calls) == before + 1
        assert calls[-1].endswith("/v1/messages")

    def test_full_downgrade_chain_to_completions(self):
        calls: list = []
        provider = AutoProtocolProvider(
            "k", "m", base_url="https://gw.example",
            protocol="auto",
            transport=lambda name: self._router(calls, responses_status=404, anthropic_status=404),
        )
        text = provider.complete("s", "u", temperature=0, max_tokens=32)[0]
        assert text == "via completions"
        assert provider.name == "completions"
        assert [u.split("?")[0].rsplit("/", 1)[-1] for u in calls[:3]] == [
            "responses", "messages", "completions",
        ]

    def test_rate_limit_error_does_not_downgrade(self):
        calls: list = []
        provider = AutoProtocolProvider(
            "k", "m", base_url="https://gw.example",
            protocol="auto",
            transport=lambda name: self._router(calls, responses_status=429),
        )
        with pytest.raises(LLMError, match="429"):
            provider.complete("s", "u", temperature=0, max_tokens=8)
        # 429 不是协议问题：只打了一个端点，没有降级
        assert len(calls) == 1 and calls[0].endswith("/responses")

    def test_forced_protocol_skips_probes(self):
        calls: list = []
        provider = AutoProtocolProvider(
            "k", "m", base_url="https://gw.example",
            protocol="anthropic",
            transport=lambda name: self._router(calls, responses_status=200),
        )
        text = provider.complete("s", "u", temperature=0, max_tokens=16)[0]
        assert text == "via anthropic"
        assert calls == [c for c in calls if c.endswith("/v1/messages")]

    def test_unknown_protocol_rejected(self):
        with pytest.raises(LLMError, match="unknown PUBMINER_LLM_PROTOCOL"):
            AutoProtocolProvider("k", "m", base_url="https://x", protocol="grpc")


class TestFactory:
    def test_build_auto_returns_negotiator(self):
        provider = build_llm_provider("k", "m", base_url="https://x", protocol="auto")
        assert isinstance(provider, AutoProtocolProvider)

    def test_build_fixed_responses(self):
        provider = build_llm_provider("k", "m", base_url="https://x", protocol="responses")
        assert isinstance(provider, ResponsesApiProvider)
