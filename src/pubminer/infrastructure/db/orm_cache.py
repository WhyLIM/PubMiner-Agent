"""ORM：resolution_cache（migration 0007）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from pubminer.infrastructure.db.base import Base, JSONVariant
from pubminer.infrastructure.db.orm_documents import utcnow


class ResolutionCacheRow(Base):
    __tablename__ = "resolution_cache"

    mention_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    resolver: Mapped[str] = mapped_column(String(128), nullable=False, default="composite")
    candidates: Mapped[list] = mapped_column(JSONVariant, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
