"""LLM 端口（ADR-011）：业务只依赖本协议，不依赖任何厂商 SDK。

每次调用必须返回可追溯元数据：provider、model、token usage、latency、
schema version 与校验尝试次数（设计文档 §9）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class LLMRequest:
    """一次 LLM 请求的完整描述。prompt_version 由调用方绑定。"""

    purpose: str
    prompt_version: str = "unversioned"
    system: str = ""
    user: str = ""
    temperature: float = 0.1
    max_tokens: int = 2048
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    purpose: str
    prompt_version: str
    temperature: float
    usage: LLMUsage
    latency_ms: int
    validation_attempts: int = 0
    schema_version: str | None = None
    created_at: datetime = field(default_factory=datetime.now)


class LLMError(RuntimeError):
    """LLM 调用失败（provider 异常、超时、schema 校验失败等）。"""


class SchemaValidationError(LLMError):
    """structured_generate 输出未通过 schema 校验。"""

    def __init__(self, message: str, attempts: int, last_error: str) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class ToolExecutionResult:
    """一次 typed tool / workflow command 执行的应用层结果。"""

    tool_name: str
    ok: bool
    summary: str
    result_count: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """provider adapter 必须实现的底层接口。"""

    name: str
    model: str

    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int) -> tuple[str, LLMUsage]:
        """同步补全；返回 (text, usage)。由 Gateway 负责计量与重试。"""
        ...


@runtime_checkable
class LLMPort(Protocol):
    """业务面向的高层端口。"""

    def generate(self, request: LLMRequest) -> LLMResponse: ...

    def structured_generate(
        self,
        request: LLMRequest,
        schema: type[BaseModel],
        *,
        max_validation_attempts: int = 2,
    ) -> LLMResponse: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
