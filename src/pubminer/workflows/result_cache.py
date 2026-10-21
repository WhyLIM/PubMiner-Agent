"""LLM 结果缓存包装器：抽取/验证命中缓存的不再调用 LLM。

与 normalize_cache 同一模式：缓存读写复用调用方当前事务中的 session
（session=None 时跳过缓存直调内层），避免 SQLite 锁冲突。
prompt_version 参与 key，prompt 升级即自动失效。
"""
from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger("pubminer.result_cache")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:64]


class CachedExtractPort:
    """包装 extract(hydrated) → (evidences, study_ctx|None)。

    key = version.text_hash（固定 canonical text 的内容哈希）。
    命中时由 JSON 重建 Evidence 模型列表。
    """

    def __init__(self, inner, *, prompt_version: str = "extraction/biomarker@v1") -> None:
        self.inner = inner
        self.prompt_version = prompt_version
        self.cache_hits = 0

    def extract(self, hydrated, *, session=None):
        # state 反序列化后 version 可能是 dict（HydratedDocument 非 pydantic 模型），统一转模型
        from pubminer.domain.documents import DocumentVersion

        version = hydrated.version
        if isinstance(version, dict):
            version = DocumentVersion.model_validate(version)
        key = _sha(f"{self.prompt_version}|{version.text_hash}")
        if session is not None:
            from pubminer.infrastructure.db.repositories.llm_cache import ResultCacheRepository

            cached = ResultCacheRepository(session).get("extract", key)
            if cached is not None:
                self.cache_hits += 1
                from pubminer.domain.evidence import BiomarkerEvidence

                # 抽取阶段产出的是 BiomarkerEvidence（claim 尚未创建），勿用 Evidence 校验
                evidences = [BiomarkerEvidence.model_validate(e) for e in cached.get("evidences", [])]
                study_ctx = cached.get("study_context")
                return evidences, study_ctx

        result = self.inner.extract(hydrated)
        evidence_items, study_ctx = result if isinstance(result, tuple) else (result, None)

        if session is not None:
            from pubminer.infrastructure.db.repositories.llm_cache import ResultCacheRepository

            ResultCacheRepository(session).put(
                "extract",
                key,
                {
                    "evidences": [e.model_dump(mode="json") for e in evidence_items],
                    "study_context": study_ctx.model_dump(mode="json") if study_ctx is not None and hasattr(study_ctx, "model_dump") else study_ctx,
                },
                prompt_version=self.prompt_version,
            )
            # 逐篇提交：释放 SQLite 写锁，避免管线长事务阻塞轮询/其它请求
            session.commit()
        return evidence_items, study_ctx


class CachedVerifyPort:
    """包装 verify(signature, evidence) → VerificationResult。

    key = signature + span 文本 + 统计量 JSON。
    """

    def __init__(self, inner, *, prompt_version: str = "verification@v1") -> None:
        self.inner = inner
        self.prompt_version = prompt_version
        self.cache_hits = 0

    def verify(self, signature: str, evidence, *, session=None):
        stats_json = evidence.statistics.model_dump(mode="json") if evidence.statistics else ""
        key = _sha(
            f"{self.prompt_version}|{signature}|{evidence.span.text}|{stats_json}"
        )
        if session is not None:
            from pubminer.infrastructure.db.repositories.llm_cache import ResultCacheRepository

            cached = ResultCacheRepository(session).get("verify", key)
            if cached is not None:
                self.cache_hits += 1
                from pubminer.domain.evidence import VerificationResult

                return VerificationResult.model_validate(cached)

        result = self.inner.verify(signature, evidence)
        if session is not None:
            from pubminer.infrastructure.db.repositories.llm_cache import ResultCacheRepository

            ResultCacheRepository(session).put(
                "verify", key, result.model_dump(mode="json"), prompt_version=self.prompt_version,
            )
            # 逐条提交：释放写锁（VERIFY 阶段 LLM 调用密集，同 extract）
            session.commit()
        return result
