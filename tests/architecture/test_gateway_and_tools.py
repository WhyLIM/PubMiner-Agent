"""PR-007 测试：LLM Gateway（fake provider）、prompt registry、tool registry。

验收：Agent/workflow 单测可完全用 fake provider 与 fake tools；业务层不接触厂商 SDK。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from pubminer.application.ports import LLMRequest, SchemaValidationError
from pubminer.integrations.llm import FakeLLMProvider, LLMGateway, PromptRegistry
from pubminer.integrations.llm.providers.zhipu import ZhipuProvider
from pubminer.integrations.tools import (
    ToolPermissionError,
    ToolRegistry,
    ToolResult,
    ToolRole,
    builtin_tool_specs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class ScreeningOut(BaseModel):
    relevant: bool
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = []


def _gateway_with(responder):
    provider = FakeLLMProvider(responder=responder)
    sink_calls: list = []
    gateway = LLMGateway(provider, cost_per_1k_tokens=0.001, usage_sink=sink_calls.append)
    return gateway, provider, sink_calls


class TestLLMGateway:
    def test_generate_records_metadata(self):
        gateway, provider, sink = _gateway_with(
            lambda s, u, t: ("answer text", 10, 5)
        )
        response = gateway.generate(
            LLMRequest(purpose="test", prompt_version="p@v1", system="sys", user="usr")
        )
        assert response.text == "answer text"
        assert response.provider == "fake" and response.model == "fake-model-v1"
        assert response.prompt_version == "p@v1"
        assert response.usage.total_tokens == 15
        assert response.latency_ms >= 0
        assert len(provider.calls) == 1
        assert len(sink) == 1, "usage sink must receive audit record"

    def test_structured_generate_valid_payload(self):
        payload = json.dumps({"relevant": True, "confidence": 0.9, "reasons": ["PDAC cohort"]})
        gateway, _, _ = _gateway_with(lambda s, u, t: (payload, 10, 10))
        response = gateway.structured_generate(
            LLMRequest(purpose="screening", user="classify"),
            ScreeningOut,
        )
        assert response.validation_attempts == 1
        assert response.schema_version == ""

    def test_structured_generate_survives_markdown_fence(self):
        payload = '```json\n{"relevant": false, "confidence": 0.8, "reasons": []}\n```'
        gateway, _, _ = _gateway_with(lambda s, u, t: (payload, 5, 5))
        response = gateway.structured_generate(LLMRequest(purpose="screening", user="x"), ScreeningOut)
        assert response.text

    def test_structured_generate_retries_with_feedback(self):
        attempts = {"n": 0}

        def responder(system, user, temperature):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return "not json at all", 5, 5
            return json.dumps({"relevant": True, "confidence": 0.5, "reasons": []}), 5, 5

        gateway, provider, _ = _gateway_with(responder)
        response = gateway.structured_generate(
            LLMRequest(purpose="screening", user="classify"), ScreeningOut
        )
        assert response.validation_attempts == 2
        # 第二次请求带上了校验失败反馈
        assert "未通过 schema 校验" in provider.calls[1][1]

    def test_structured_generate_gives_up_after_max_attempts(self):
        gateway, _, _ = _gateway_with(lambda s, u, t: ("garbage", 1, 1))
        with pytest.raises(SchemaValidationError) as exc_info:
            gateway.structured_generate(
                LLMRequest(purpose="screening", user="x"), ScreeningOut, max_validation_attempts=1
            )
        assert exc_info.value.attempts == 2

    def test_embed_uses_provider_embedder(self):
        gateway, provider, _ = _gateway_with(None)
        provider.embedder = lambda texts: [[0.1, 0.2] for _ in texts]
        assert gateway.embed(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]

    def test_cost_calculation(self):
        gateway, _, _ = _gateway_with(lambda s, u, t: ("x", 1000, 1000))
        response = gateway.generate(LLMRequest(purpose="t", user="u"))
        assert gateway.cost_of(response) == 0.002  # 2000 tokens @ $0.001/1k


class TestZhipuAdapterBoundary:
    def test_adapter_requires_key_without_network(self):
        import os

        saved = os.environ.pop("ZHIPU_API_KEY", None)
        try:
            with pytest.raises(Exception, match="API key"):
                ZhipuProvider()
        finally:
            if saved:
                os.environ["ZHIPU_API_KEY"] = saved

    def test_business_layer_imports_no_zhipuai(self):
        # 业务模块（application/domain）源码中不得出现 zhipuai
        for tree in ("src/pubminer/application", "src/pubminer/domain"):
            for path in (REPO_ROOT / tree).rglob("*.py"):
                assert "zhipuai" not in path.read_text(encoding="utf-8"), path


class TestPromptRegistry:
    def test_load_versioned_prompt(self):
        registry = PromptRegistry(REPO_ROOT / "prompts")
        prompt = registry.get("screening", "v1")
        assert "{{research_question}}" in prompt.text
        assert prompt.schema_version == "screening-v1"
        assert prompt.system

    def test_render_variables(self):
        registry = PromptRegistry(REPO_ROOT / "prompts")
        rendered = registry.get("screening", "v1").render(
            research_question="PDAC prognostic biomarkers", criteria="independent cohort"
        )
        assert "PDAC prognostic biomarkers" in rendered
        assert "{{" not in rendered

    def test_same_version_is_immutable(self):
        registry = PromptRegistry(REPO_ROOT / "prompts")
        a = registry.get("verification", "v1")
        b = registry.get("verification", "v1")
        assert a is b and a.text == b.text

    def test_missing_version_raises(self):
        registry = PromptRegistry(REPO_ROOT / "prompts")
        with pytest.raises(Exception, match="not found"):
            registry.get("screening", "v99")

    def test_builtin_prompts_present(self):
        registry = PromptRegistry(REPO_ROOT / "prompts")
        for name in ("agent-policy", "screening", "verification"):
            assert registry.versions(name), f"{name} prompts missing"


class TestToolRegistry:
    def _registry(self):
        registry = ToolRegistry()
        for spec in builtin_tool_specs():
            handler = lambda **kwargs: ToolResult(  # noqa: E731
                tool_name=spec.name, ok=True, summary="ok", result_count=1
            )
            registry.register(spec, handler)
        return registry

    def test_builtin_tools_registered(self):
        registry = self._registry()
        agent_tools = {spec.name for spec in registry.tools_for_role(ToolRole.AGENT)}
        expected = {
            "PubMedSearchTool", "PMCFulltextTool", "PubTatorTool", "EntityResolverTool",
            "ExtractionTool", "CreateCandidateClaimTool", "SubmitReviewTool", "AskHumanTool",
        }
        assert expected <= agent_tools
        # Agent 的工具面永远不含发布类工具
        assert "PublishClaimTool" not in agent_tools

    def test_unregistered_tool_denied(self):
        registry = self._registry()
        with pytest.raises(ToolPermissionError, match="not registered"):
            registry.call("ArbitraryShellTool", ToolRole.AGENT)

    def test_agent_cannot_publish(self):
        registry = self._registry()
        with pytest.raises(ToolPermissionError, match="not allowed"):
            registry.call("PublishClaimTool", ToolRole.AGENT)

    def test_senior_reviewer_can_publish_and_is_audited(self):
        registry = self._registry()
        result = registry.call("PublishClaimTool", ToolRole.SENIOR_REVIEWER, claim_id="c1")
        assert result.ok
        assert registry.audit_log[-1]["tool"] == "PublishClaimTool"
        assert registry.audit_log[-1]["requires_confirmation"] is True

    def test_handler_error_becomes_failed_result(self):
        registry = ToolRegistry()
        from pubminer.integrations.tools import ToolSpec

        spec = ToolSpec(
            name="PubMedSearchTool", description="d",
            allowed_roles=frozenset({ToolRole.AGENT}),
        )
        registry.register(spec, lambda **kw: (_ for _ in ()).throw(RuntimeError("ncbi down")))
        result = registry.call("PubMedSearchTool", ToolRole.AGENT, query="x")
        assert not result.ok and "ncbi down" in result.error
