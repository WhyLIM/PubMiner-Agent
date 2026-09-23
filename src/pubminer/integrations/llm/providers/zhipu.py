"""Zhipu GLM provider adapter（迁移自 webui ZhipuExtractor 的调用方式）。

红线：厂商 SDK 只能在这里懒加载；业务层只依赖 application.ports.LLMPort。
"""
from __future__ import annotations

import logging
import os
import time

from pubminer.application.ports import LLMError, LLMUsage

logger = logging.getLogger("pubminer.llm.zhipu")

_SDK_IMPORT_ERROR = (
    "zhipuai SDK 未安装；请 `pip install 'pubminer-ea[zhipu]'` 或安装 zhipuai>=2.0"
)


class ZhipuProvider:
    """智谱 GLM chat.completions adapter（同步）。"""

    name = "zhipu"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "glm-4-flash",
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY", "")
        if not self.api_key:
            raise LLMError("ZhipuProvider requires an API key (env ZHIPU_API_KEY)")
        self.model = model
        self.base_url = base_url or os.environ.get("ZHIPU_BASE_URL")
        self.timeout = timeout
        self._client = None  # 懒加载

    def _get_client(self):
        if self._client is None:
            try:
                from zhipuai import ZhipuAI  # 延迟导入：只有 adapter 触达厂商 SDK
            except ImportError as exc:
                raise LLMError(_SDK_IMPORT_ERROR) from exc
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = ZhipuAI(**kwargs)
        return self._client

    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int) -> tuple[str, LLMUsage]:
        client = self._get_client()
        start = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system} if system else None,
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise LLMError(f"zhipu chat failed: {exc}") from exc
        usage = getattr(response, "usage", None)
        llm_usage = LLMUsage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        text = response.choices[0].message.content or ""
        logger.debug("zhipu complete %.0fms tokens=%d", (time.perf_counter() - start) * 1000, llm_usage.total_tokens)
        return text, llm_usage
