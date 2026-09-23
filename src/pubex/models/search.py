"""检索与引用关系的 typed 结果模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SearchResultPage(BaseModel):
    """一次 esearch 的结果页。History 字段支持后续 efetch 分页。"""

    query: str
    pmids: list[str] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    returned_count: int = 0
    webenv: str | None = None
    query_key: str | None = None


class CitationEntry(BaseModel):
    """单篇文献的引用关系。"""

    pmid: str
    cited_by: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    @property
    def cited_count(self) -> int:
        return len(self.cited_by)

    @property
    def references_count(self) -> int:
        return len(self.references)
