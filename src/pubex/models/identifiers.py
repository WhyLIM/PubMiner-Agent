"""文献标识符模型。

不变量（设计文档 ADR-006）：identifier 只能由解析器/resolver 从数据源原文提取，
不由模型生成。这里的字段全部来自 MEDLINE/PMC 记录的原始内容。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ArticleIdentifiers(BaseModel):
    """一篇文章的三类主标识符，均允许缺失（用 None 表达，不得自造占位值）。"""

    pmid: str | None = Field(default=None, description="PubMed ID，来自记录 PMID 字段")
    pmcid: str | None = Field(default=None, description="PMC ID，来自记录 PMC 字段（形如 PMC1234567）")
    doi: str | None = Field(default=None, description="DOI，来自记录 LID/AID 字段的规范化部分")

    def identity_key(self) -> str:
        """用于去重的稳定键：优先 PMID，其次 PMCID，最后 DOI。"""
        if self.pmid:
            return f"pmid:{self.pmid}"
        if self.pmcid:
            return f"pmcid:{self.pmcid}"
        if self.doi:
            return f"doi:{self.doi.lower()}"
        raise ValueError("article has no identifier; manual confirmation required")
