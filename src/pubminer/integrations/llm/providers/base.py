"""LLM provider 基础设施：协议协商错误 + HTTP JSON 补全基类。

协议优先级（用户策略）：Responses API → Anthropic Messages → Chat Completions。
`ProtocolNotSupportedError` 表示"该端点不提供此协议"（404/405/501），
由协商层捕获并降级；其余错误（401/429/500…）原样抛出，不得降级掩盖。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from pubminer.application.ports import LLMError, LLMUsage

logger = logging.getLogger("pubminer.llm.providers")


class ProtocolNotSupportedError(LLMError):
    """端点不支持当前协议（可安全降级到下一优先级协议）。"""


class HttpJsonProvider:
    """同步 HTTP JSON 补全基类。子类定义 path/headers/payload/parse。"""

    name: str = "http"
    model: str = ""
    path: str = ""
    extra_headers: dict[str, str] = {}

    #: 瞬时可重试状态码（限流）；404/405/501 是协议不存在信号，必须快速失败降级
    RETRYABLE_STATUS: frozenset[int] = frozenset({429})
    MAX_ATTEMPTS = 3
    #: 重试退避基数（秒）；测试中置 0 消除等待
    RETRY_BASE_DELAY = 1.5

    def _retry_delay(self, attempt: int) -> float:
        return self.RETRY_BASE_DELAY * attempt

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = 'https://open.bigmodel.cn/api/paas/v4',
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMError(f"{self.__class__.__name__} requires an API key")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}", **self.extra_headers},
            timeout=timeout,
            transport=transport,
        )

    # 子类钩子 ------------------------------------------------------------

    def _payload(self, system: str, user: str, *, temperature: float, max_tokens: int) -> dict[str, Any]:
        raise NotImplementedError

    def _parse(self, payload: dict[str, Any]) -> tuple[str, LLMUsage]:
        raise NotImplementedError

    def _endpoint(self) -> str:
        return f"{self.base_url}{self.path}"

    # 执行 ----------------------------------------------------------------

    def complete(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> tuple[str, LLMUsage]:
        start = time.perf_counter()
        last_error: LLMError | None = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = self._client.post(
                    self._endpoint(),
                    json=self._payload(system, user, temperature=temperature, max_tokens=max_tokens),
                )
            except httpx.HTTPError as exc:
                # 网关断连/超时/连接重置属瞬时故障：短退避后重试，耗尽才上抛
                last_error = LLMError(f"LLM request failed: {exc}")
                if attempt < self.MAX_ATTEMPTS:
                    delay = self._retry_delay(attempt)
                    logger.warning(
                        "LLM transport error (attempt %d/%d), retry in %.1fs: %s",
                        attempt, self.MAX_ATTEMPTS, delay, exc,
                    )
                    time.sleep(delay)
                    continue
                raise last_error
            if response.status_code in (404, 405, 501):
                raise ProtocolNotSupportedError(
                    f"{self.name} protocol not available at {self._endpoint()} (HTTP {response.status_code})"
                )
            if response.status_code in self.RETRYABLE_STATUS and attempt < self.MAX_ATTEMPTS:
                delay = self._retry_delay(attempt)
                logger.warning(
                    "LLM HTTP %d (attempt %d/%d), retry in %.1fs",
                    response.status_code, attempt, self.MAX_ATTEMPTS, delay,
                )
                time.sleep(delay)
                continue
            if response.status_code != 200:
                raise LLMError(
                    f"LLM endpoint returned HTTP {response.status_code}: {response.text[:300]}"
                )
            try:
                text, usage = self._parse(response.json())
            except (KeyError, ValueError, TypeError) as exc:
                raise LLMError(f"unexpected LLM response shape: {exc}") from exc
            logger.debug(
                "%s complete %.0fms tokens=%d",
                self.name,
                (time.perf_counter() - start) * 1000,
                usage.total_tokens,
            )
            return text, usage
        raise last_error if last_error else LLMError("LLM request failed after retries")
