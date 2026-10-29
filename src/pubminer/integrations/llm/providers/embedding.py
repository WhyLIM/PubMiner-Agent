"""Embedding provider：OpenAI 兼容格式（智谱 embedding-3 / OpenAI text-embedding-3 等）。

POST {base}/embeddings
Body: {"model": ..., "input": [...], "dimensions": ...}
Response: {"data": [{"embedding": [...], "index": 0}], "usage": {...}}
"""
from __future__ import annotations

import logging
import time

import httpx

from pubminer.application.ports import LLMError

logger = logging.getLogger("pubminer.embedding")


class EmbeddingProvider:
    """OpenAI 兼容 embedding 端点适配器。"""

    MAX_ATTEMPTS = 3
    #: 重试退避基数（秒）；测试中置 0 消除等待
    RETRY_BASE_DELAY = 1.5

    def __init__(
        self,
        api_key: str,
        model: str = "embedding-3",
        *,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        dimensions: int = 2048,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("EmbeddingProvider requires an API key")
        self.model = model
        self.dimensions = dimensions
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量计算 embedding。单次最多 64 条（Zhipu 限制）。"""
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for batch_start in range(0, len(texts), 64):
            batch = texts[batch_start : batch_start + 64]
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                try:
                    response = self._client.post(
                        f"{self.base_url}/embeddings",
                        json={
                            "model": self.model,
                            "input": batch,
                            "dimensions": self.dimensions,
                        },
                    )
                except httpx.HTTPError as exc:
                    # 与补全 provider 同口径：瞬时传输故障退避重试
                    last_error = LLMError(f"embedding request failed: {exc}")
                    if attempt < self.MAX_ATTEMPTS:
                        delay = self.RETRY_BASE_DELAY * attempt
                        logger.warning(
                            "embedding transport error (attempt %d/%d), retry in %.1fs: %s",
                            attempt, self.MAX_ATTEMPTS, delay, exc,
                        )
                        time.sleep(delay)
                        continue
                    raise last_error
                if response.status_code in (429,) and attempt < self.MAX_ATTEMPTS:
                    delay = self.RETRY_BASE_DELAY * attempt
                    logger.warning(
                        "embedding HTTP %d (attempt %d/%d), retry in %.1fs",
                        response.status_code, attempt, self.MAX_ATTEMPTS, delay,
                    )
                    time.sleep(delay)
                    continue
                if response.status_code != 200:
                    raise LLMError(
                        f"embedding endpoint returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                break
            try:
                data = sorted(response.json()["data"], key=lambda d: d["index"])
                all_vectors.extend(item["embedding"] for item in data)
            except (KeyError, TypeError) as exc:
                raise LLMError(f"unexpected embedding response shape: {exc}") from exc
        logger.debug("embedded %d texts (model=%s, dim=%d)", len(texts), self.model, len(all_vectors[0]) if all_vectors else 0)
        return all_vectors
