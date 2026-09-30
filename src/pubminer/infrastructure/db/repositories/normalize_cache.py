"""解析缓存仓储：mention → 候选列表，跨 run 免重复外部调用。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from pubminer.infrastructure.db.orm_cache import ResolutionCacheRow


def normalize_mention_key(mention: str) -> str:
    """缓存键：小写并去除全部非字母数字（与 span 归一化口径一致）。"""
    return re.sub(r"[^a-z0-9]", "", mention.lower())


class ResolutionCacheRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_candidates(self, mention: str, entity_type: str) -> list[dict[str, Any]] | None:
        """命中返回候选（dict 列表），未命中返回 None。"""
        key = normalize_mention_key(mention)
        row = self.session.get(ResolutionCacheRow, (key, entity_type))
        if row is None:
            return None
        return [dict(c) for c in (row.candidates or [])]

    def put_candidates(
        self,
        mention: str,
        entity_type: str,
        candidates: list[dict[str, Any]],
        *,
        resolver: str = "composite",
    ) -> None:
        key = normalize_mention_key(mention)
        self.session.execute(
            delete(ResolutionCacheRow).where(
                ResolutionCacheRow.mention_key == key,
                ResolutionCacheRow.entity_type == entity_type,
            )
        )
        self.session.add(
            ResolutionCacheRow(
                mention_key=key,
                entity_type=entity_type,
                resolver=resolver,
                candidates=candidates,
                created_at=datetime.now(timezone.utc),
            )
        )
        self.session.flush()
