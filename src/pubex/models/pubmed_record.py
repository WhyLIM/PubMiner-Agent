"""PubMed XML 记录的富元数据模型（迁移自 PubMiner-webui LiteratureMetadata）。"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class PubMedRecord(BaseModel):
    """从 PubMed XML（efetch rettype=xml）解析的文献元数据。

    兼容别名：`LiteratureMetadata = PubMedRecord`（见 models/__init__.py）。
    """

    pmid: str = Field(..., description="PubMed ID")
    pmcid: str | None = Field(None, description="PMC ID（存在时）")
    doi: str | None = Field(None, description="DOI")

    title: str = Field(..., description="标题")
    authors: list[str] = Field(default_factory=list)
    first_author: str = Field("", description="第一作者")
    affiliation: str = Field("", description="第一作者机构")

    journal: str = ""
    journal_abbrev: str = ""
    issn: str = ""
    journal_id: str = ""

    pub_date: str | None = None
    year: int | None = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publication_status: str = ""
    article_type: str = ""

    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    language: str = ""

    cited_count: int = 0
    cited_by: list[str] = Field(default_factory=list)
    references_count: int = 0
    references: list[str] = Field(default_factory=list)

    status: str = ""
    last_revision_date: str = ""
    grant_list: str = ""

    has_pmc_fulltext: bool = False

    @field_validator("pmid")
    @classmethod
    def _validate_pmid(cls, v: str) -> str:
        if not re.match(r"^\d+$", str(v)):
            raise ValueError(f"Invalid PMID format: {v}")
        return str(v)

    @field_validator("pmcid")
    @classmethod
    def _validate_pmcid(cls, v: str | None) -> str | None:
        if v and not re.match(r"^PMC\d+$", str(v)):
            raise ValueError(f"Invalid PMCID format: {v}")
        return v

    def get_author_string(self, max_authors: int = 3) -> str:
        if not self.authors:
            return ""
        if len(self.authors) <= max_authors:
            return ", ".join(self.authors)
        return ", ".join(self.authors[:max_authors]) + " et al."

    def get_citation(self) -> str:
        parts: list[str] = []
        if self.authors:
            parts.append(self.get_author_string())
        parts.append(self.title)
        if self.journal:
            journal_part = self.journal_abbrev or self.journal
            if self.year:
                journal_part += f" {self.year}"
            if self.volume:
                journal_part += f";{self.volume}"
            if self.pages:
                journal_part += f":{self.pages}"
            parts.append(journal_part)
        return ". ".join(parts) + "."
