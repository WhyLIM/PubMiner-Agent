"""解析缓存包装器：命中缓存的 mention 不再调用外部 resolver。

包装任何实现 resolve(mention, entity_type) 的 resolver；缓存读写经
ResolutionCacheRepository（与调用方同一 session/session_factory）。
"""
from __future__ import annotations

import logging

from pubminer.infrastructure.db.repositories.normalize_cache import (
    ResolutionCacheRepository,
    normalize_mention_key,
)
from pubminer.workflows.ports import ResolutionCandidate

logger = logging.getLogger("pubminer.normalize.cache")


class CachedEntityResolver:
    def __init__(self, inner, session_factory, *, resolver_name: str = "composite") -> None:
        self.inner = inner
        self.session_factory = session_factory
        self.resolver_name = resolver_name
        self.cache_hits = 0

    def resolve(self, mention: str, entity_type: str):
        from pubminer.infrastructure.db.base import session_scope

        key = normalize_mention_key(mention)
        with session_scope(self.session_factory) as session:
            cached = ResolutionCacheRepository(session).get_candidates(key, entity_type)
        if cached is not None:
            self.cache_hits += 1
            candidates = [ResolutionCandidate(**c) for c in cached]
            return candidates, len(candidates) != 1

        candidates, needs_review = self.inner.resolve(mention, entity_type)
        from dataclasses import asdict

        with session_scope(self.session_factory) as session:
            ResolutionCacheRepository(session).put_candidates(
                key, entity_type, [asdict(c) for c in candidates],
                resolver=self.resolver_name,
            )
        return candidates, needs_review
