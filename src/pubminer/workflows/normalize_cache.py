"""解析缓存包装器：命中缓存的 mention 不再调用外部 resolver。

包装任何实现 resolve(mention, entity_type) 的 resolver；缓存读写
复用调用方当前事务中的 session（避免 SQLite 锁冲突）。
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from pubminer.infrastructure.db.repositories.normalize_cache import (
    ResolutionCacheRepository,
    normalize_mention_key,
)
from pubminer.workflows.ports import ResolutionCandidate

logger = logging.getLogger("pubminer.normalize.cache")


class CachedEntityResolver:
    """resolve 时从调用方的 ORM session 读写缓存。

    session_getter: 一个 callable，返回当前活跃的 Session（或 None）。
    当 session_getter 返回 None 时，跳过缓存直接调用 inner resolver。
    """

    def __init__(self, inner, session_factory, *, resolver_name: str = "composite") -> None:
        self.inner = inner
        self.session_factory = session_factory
        self.resolver_name = resolver_name
        self.cache_hits = 0

    def _get_repo(self, session) -> ResolutionCacheRepository:
        return ResolutionCacheRepository(session)

    def resolve(self, mention: str, entity_type: str, *, session=None):
        key = normalize_mention_key(mention)
        if session is not None:
            cached = self._get_repo(session).get_candidates(key, entity_type)
            if cached is not None:
                self.cache_hits += 1
                candidates = [ResolutionCandidate(**c) for c in cached]
                return candidates, len(candidates) != 1

        candidates, needs_review = self.inner.resolve(mention, entity_type)
        if session is not None:
            self._get_repo(session).put_candidates(
                key, entity_type, [asdict(c) for c in candidates],
                resolver=self.resolver_name,
            )
        return candidates, needs_review
