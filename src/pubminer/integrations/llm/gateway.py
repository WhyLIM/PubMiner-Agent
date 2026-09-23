"""LLM Gateway：实现 LLMPort；负责计量、重试、schema 校验、审计元数据。

业务代码只 import application.ports；本 Gateway 通过构造注入 provider。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable

from pydantic import BaseModel, ValidationError

from pubminer.application.ports import (
    LLMPort,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    SchemaValidationError,
)

logger = logging.getLogger("pubminer.llm")


class LLMGateway(LLMPort):
    """组合任意 LLMProvider，输出带完整元数据的 LLMResponse。

    Args:
        provider: 底层 provider adapter（zhipu/fake/...）。
        cost_per_1k_tokens: 计费函数输入（可注入真实价目）。
        usage_sink: 每次调用后的审计回调（写 DB/日志），不阻塞主流程。
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        cost_per_1k_tokens: float = 0.0,
        usage_sink: Callable[[LLMResponse], None] | None = None,
    ) -> None:
        self.provider = provider
        self.cost_per_1k_tokens = cost_per_1k_tokens
        self.usage_sink = usage_sink

    # ------------------------------------------------------------------ generate

    def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        try:
            text, usage = self.provider.complete(
                request.system,
                request.user,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as exc:
            logger.error("LLM generate failed (purpose=%s): %s", request.purpose, exc)
            raise
        response = LLMResponse(
            text=text,
            provider=self.provider.name,
            model=self.provider.model,
            purpose=request.purpose,
            prompt_version=request.prompt_version,
            temperature=request.temperature,
            usage=usage,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
        self._record(response, request)
        return response

    # -------------------------------------------------------- structured_generate

    def structured_generate(
        self,
        request: LLMRequest,
        schema: type[BaseModel],
        *,
        max_validation_attempts: int = 2,
    ) -> LLMResponse:
        """schema 约束输出：解析 + pydantic 校验 + 带错误反馈的重试。"""
        attempts = 0
        last_error = ""
        feedback = ""
        response: LLMResponse | None = None
        while attempts <= max_validation_attempts:
            attempts += 1
            user_prompt = request.user
            if feedback:
                user_prompt = (
                    f"{request.user}\n\n上一次输出未通过 schema 校验：{feedback}\n"
                    f"请严格按 JSON schema 重新输出，只输出 JSON。"
                )
            response = self.generate(
                LLMRequest(
                    purpose=request.purpose,
                    prompt_version=request.prompt_version,
                    system=request.system or "You are a careful biomedical information extractor.",
                    user=user_prompt,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    metadata=request.metadata,
                )
            )
            try:
                payload = _extract_json(response.text)
                schema.model_validate(payload)
                response.validation_attempts = attempts
                response.schema_version = str(request.metadata.get("schema_version", ""))
                return response
            except (json.JSONDecodeError, ValueError, ValidationError) as exc:
                last_error = str(exc)
                feedback = last_error[:500]
                logger.warning(
                    "structured output failed schema (attempt %d/%d): %s",
                    attempts, max_validation_attempts + 1, last_error[:200],
                )
        raise SchemaValidationError(
            f"structured_generate failed after {attempts} attempts", attempts, last_error
        )

    # ------------------------------------------------------------------ embed

    def embed(self, texts: list[str]) -> list[list[float]]:
        """embedding 走 provider 可选接口；未实现时显式失败。"""
        embed_fn = getattr(self.provider, "embed", None)
        if embed_fn is None:
            raise NotImplementedError(f"provider {self.provider.name} does not support embedding")
        return embed_fn(texts)

    # ------------------------------------------------------------------ cost

    def cost_of(self, response: LLMResponse) -> float:
        return round(response.usage.total_tokens / 1000 * self.cost_per_1k_tokens, 6)

    def _record(self, response: LLMResponse, request: LLMRequest) -> None:
        logger.info(
            "llm call purpose=%s provider=%s model=%s prompt_version=%s tokens=%d latency=%dms",
            request.purpose, response.provider, response.model,
            response.prompt_version, response.usage.total_tokens, response.latency_ms,
        )
        if self.usage_sink is not None:
            try:
                self.usage_sink(response)
            except Exception:  # 审计失败不影响主流程
                logger.exception("usage sink failed")


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """从模型输出提取 JSON 对象：裸 JSON / ```json 围栏 / 首个大括号块。"""
    text = text.strip()
    fence = _JSON_BLOCK.search(text)
    if fence:
        return json.loads(fence.group(1))
    if text.startswith("{"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in model output")
