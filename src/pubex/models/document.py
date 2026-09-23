"""Document Model：文档版本、passage、许可记录（设计文档 §6.1）。

稳定定位不变量：passage offset 相对已保存且 content-hash 固定的 canonical text；
清洗算法变化必须产生新 content_version，而不是静默改变 offset。
"""
from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field


def content_hash(text: str) -> str:
    """canonical text 的 sha256，作为 offset/引用稳定性的锚。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LicenseRecord(BaseModel):
    """来源与许可记录：PMC 可访问不等于可自由再分发。"""

    source: str = Field(..., description="获取来源，如 pmc-oa / europepmc / publisher-oa")
    license: str | None = Field(None, description="许可标识，如 cc-by-nc；未知为 None")
    retrieval_method: str = Field("bioc-api", description="获取方式")
    url: str | None = None
    retrieved_at: str | None = None
    allows_redistribution: bool | None = Field(
        None, description="是否允许再分发；未知必须为 None，不得默认 true"
    )


class Passage(BaseModel):
    """带稳定定位的 passage。offset 相对 document_version 的 canonical text。"""

    passage_id: str = Field(..., description="稳定 ID：{content_version}:{start}:{end}")
    section_path: str = Field(..., description="如 ABSTRACT / RESULTS.2")
    text: str
    start_char: int
    end_char: int
    text_hash: str = Field(..., description="sha256(text)")

    @staticmethod
    def build(section_path: str, text: str, start_char: int) -> "Passage":
        return Passage(
            passage_id=f"{start_char}:{start_char + len(text)}",
            section_path=section_path,
            text=text,
            start_char=start_char,
            end_char=start_char + len(text),
            text_hash=content_hash(text),
        )


class DocumentVersion(BaseModel):
    """不可变文档版本：新内容产生新版本，不覆盖。"""

    pmid: str | None = None
    pmcid: str | None = None
    content_version: str = Field("1", description="内容版本号")
    title: str = ""
    canonical_text: str = Field("", description="offset 的基准文本")
    text_hash: str = Field("", description="sha256(canonical_text)")
    passages: list[Passage] = Field(default_factory=list)
    license: LicenseRecord | None = None
    raw_bioc: dict[str, Any] | list[Any] | None = Field(
        None, description="原始 BioC 数据（不入库时为 None）"
    )

    @classmethod
    def from_sections(
        cls,
        *,
        pmid: str | None,
        pmcid: str | None,
        title: str,
        sections: list[tuple[str, str]],
        license_record: LicenseRecord | None = None,
        raw_bioc: dict[str, Any] | list[Any] | None = None,
    ) -> "DocumentVersion":
        """按 section 顺序拼装 canonical text 并生成带稳定 offset 的 passages。

        Args:
            sections: (section_path, text) 列表，顺序即文档顺序。
        """
        parts: list[str] = []
        passages: list[Passage] = []
        offset = 0
        for section_path, text in sections:
            stripped = text.strip()
            if not stripped:
                continue
            start = offset
            parts.append(stripped)
            passages.append(Passage.build(section_path, stripped, start))
            offset = start + len(stripped) + 2  # 段间以 "\n\n" 连接
        canonical = "\n\n".join(parts)
        return cls(
            pmid=pmid,
            pmcid=pmcid,
            title=title,
            canonical_text=canonical,
            text_hash=content_hash(canonical),
            passages=passages,
            license=license_record,
            raw_bioc=raw_bioc,
        )

    def total_chars(self) -> int:
        return len(self.canonical_text)

    def estimate_tokens(self, chars_per_token: float = 4.0) -> int:
        return int(self.total_chars() / chars_per_token)


#: 与 PubMiner-webui FullTextDocument 兼容的轻量视图（迁移期 convenience）
class FullTextDocument(BaseModel):
    pmid: str
    pmcid: str
    title: str = ""
    filtered_text: str = ""
    sections: dict[str, str] = Field(default_factory=dict)
    total_chars: int = 0
    total_tokens_estimate: int = 0

    @classmethod
    def from_document_version(cls, doc: DocumentVersion) -> "FullTextDocument":
        sections = {p.section_path: p.text for p in doc.passages}
        return cls(
            pmid=doc.pmid or "",
            pmcid=doc.pmcid or "",
            title=doc.title,
            filtered_text=doc.canonical_text,
            sections=sections,
            total_chars=doc.total_chars(),
            total_tokens_estimate=doc.estimate_tokens(),
        )
