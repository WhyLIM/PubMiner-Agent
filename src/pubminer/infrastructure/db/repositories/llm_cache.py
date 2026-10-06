"""LLM 结果缓存仓储：抽取/验证结果按内容哈希跨 run 复用。

键由调用方构造（kind + 输入内容哈希 + prompt_version），
prompt_version 变更时自然失效，保证可复现性。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from pubminer.infrastructure.db.orm_llm_cache import LLMCacheRow


class ResultCacheRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, kind: str, cache_key: str) -> dict[str, Any] | None:
        row = self.session.get(LLMCacheRow, (cache_key, kind))
        if row is None:
            return None
        return dict(row.value or {})

    def get_many(self, kind: str, cache_keys: list[str]) -> dict[str, dict[str, Any]]:
        """批量读取（用于 embedding 向量缓存）。"""
        out: dict[str, dict[str, Any]] = {}
        for key in cache_keys:
            row = self.session.get(LLMCacheRow, (key, kind))
            if row is not None:
                out[key] = dict(row.value or {})
        return out

    def put(self, kind: str, cache_key: str, value: dict[str, Any], *, prompt_version: str = "") -> None:
        existing = self.session.get(LLMCacheRow, (cache_key, kind))
        if existing is not None:
            existing.value = value
            existing.prompt_version = prompt_version
        else:
            self.session.add(
                LLMCacheRow(
                    cache_key=cache_key,
                    kind=kind,
                    prompt_version=prompt_version,
                    value=value,
                    created_at=datetime.now(timezone.utc),
                )
            )
        self.session.flush()
