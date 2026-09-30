"""Embedding 服务：计算、缓存与余弦相似度。

规模场景（数千至万篇文献）：embedding 预筛是 LLM 筛选前的第一级
过滤，用余弦相似度快速跳过明显不相关的摘要，大幅降低 LLM 调用成本。
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

logger = logging.getLogger("pubminer.embedding_service")

DEFAULT_SIMILARITY_THRESHOLD = 0.35


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度（无 numpy 依赖）。"""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


class EmbeddingService:
    """embedding 计算 + 内存缓存 + 余弦相似度。

    Args:
        embed_fn: 批量计算 embedding 的函数（来自 provider 或 gateway）。
        threshold: 余弦相似度阈值，低于此值视为"不相关"。
    """

    def __init__(
        self,
        embed_fn,
        *,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        cache_max: int = 10_000,
    ) -> None:
        self._embed_fn = embed_fn
        self.threshold = threshold
        self._cache: dict[str, list[float]] = {}
        self._cache_max = cache_max

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量计算 embedding，命中缓存的跳过。"""
        uncached: dict[int, str] = {}
        vectors: list[list[float] | None] = [None] * len(texts)

        for i, text in enumerate(texts):
            key = _cache_key(text)
            if key in self._cache:
                vectors[i] = self._cache[key]
            else:
                uncached[i] = key

        if uncached:
            batch_texts = [texts[i] for i in sorted(uncached)]
            batch_vectors = self._embed_fn(batch_texts)
            for j, idx in enumerate(sorted(uncached)):
                vec = batch_vectors[j]
                vectors[idx] = vec
                if len(self._cache) < self._cache_max:
                    self._cache[uncached[idx]] = vec

        return [v for v in vectors if v is not None]

    def similarity_to_profile(self, profile_vector: list[float], texts: list[str]) -> list[float]:
        """计算一批文本与研究目标 profile 的余弦相似度。"""
        vectors = self.embed_texts(texts)
        return [cosine_similarity(profile_vector, v) for v in vectors]

    def build_profile(self, goal_text: str) -> list[float]:
        """从研究目标生成 profile 向量。"""
        return self._embed_fn([goal_text])[0]

    def prefilter(
        self,
        profile: list[float],
        candidates: list[dict[str, Any]],
        *,
        text_key: str = "abstract",
        threshold: float | None = None,
    ) -> tuple[list[dict[str, Any]], list[float]]:
        """embedding 预筛：返回通过阈值的候选及其相似度分数。

        保守策略：阈值设低（默认 0.35），宁可放过不可错杀——
        LLM 筛选才是精确判定层。
        """
        effective_threshold = threshold if threshold is not None else self.threshold
        texts = [str(c.get(text_key, "")) for c in candidates]
        vectors = self.embed_texts(texts)
        passed: list[dict[str, Any]] = []
        scores: list[float] = []
        for candidate, vector in zip(candidates, vectors):
            score = cosine_similarity(profile, vector)
            scores.append(score)
            if score >= effective_threshold:
                passed.append(candidate)
        logger.info(
            "embedding prefilter: %d/%d passed (threshold=%.2f)",
            len(passed), len(candidates), effective_threshold,
        )
        return passed, scores
