"""Document 聚合：原文分层存储、稳定定位（设计文档 §6.1、ADR-004）。

不变量：
- 每个 passage 有稳定位置与 source text；offset 相对已保存且 content-hash
  固定的 canonical text；
- 清洗算法变化产生新 content_version，不静默改变 offset；
- 原文不可覆盖：新内容产生新 DocumentVersion。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_id() -> UUID:
    return uuid4()


class DocumentIdentifier(BaseModel):
    """外部标识（PMID/PMCID/DOI…）。去重依据（§7.2）。"""

    kind: str = Field(..., description="pmid | pmcid | doi")
    value: str

    def normalized(self) -> "DocumentIdentifier":
        if self.kind == "doi":
            return DocumentIdentifier(kind="doi", value=self.value.lower().strip())
        return self


class PassageRef(BaseModel):
    """指向固定 document version 中一段文本的稳定定位。"""

    document_version_id: UUID
    passage_id: str
    section_path: str = ""
    start_char: int
    end_char: int

    @model_validator(mode="after")
    def _check_range(self) -> "PassageRef":
        if self.start_char < 0 or self.end_char <= self.start_char:
            raise ValueError(f"invalid passage range [{self.start_char}, {self.end_char})")
        return self


class EvidenceSpan(BaseModel):
    """附录 A 契约： grounding 的最小单元。

    text_hash 用于校验 span 与保存的 canonical text 的一致性；不匹配即
    grounding violation，禁止生成 claim。
    """

    document_version_id: UUID
    passage_id: UUID
    section_path: str = ""
    start_char: int
    end_char: int
    text: str
    text_hash: str

    @model_validator(mode="after")
    def _check(self) -> "EvidenceSpan":
        if self.text_hash != content_hash(self.text):
            raise ValueError("evidence span text_hash mismatch (grounding violation)")
        if self.end_char <= self.start_char:
            raise ValueError("evidence span must be non-empty")
        return self

    @classmethod
    def from_text(
        cls,
        document_version_id: UUID,
        passage_id: UUID,
        text: str,
        start_char: int,
        section_path: str = "",
    ) -> "EvidenceSpan":
        return cls(
            document_version_id=document_version_id,
            passage_id=passage_id,
            section_path=section_path,
            start_char=start_char,
            end_char=start_char + len(text),
            text=text,
            text_hash=content_hash(text),
        )


class DocumentVersion(BaseModel):
    """不可变文档版本：offset 的基准。"""

    id: UUID = Field(default_factory=new_id)
    document_id: UUID
    content_version: str = "1"
    title: str = ""
    canonical_text: str = ""
    text_hash: str = ""
    license: str | None = Field(None, description="许可标识；未知保持 None")
    source: str = Field("pubmed", description="获取来源")
    retrieved_at: datetime | None = None
    sections: list[str] = Field(default_factory=list, description="section path 列表")

    def model_post_init(self, __context) -> None:
        if not self.text_hash and self.canonical_text:
            self.text_hash = content_hash(self.canonical_text)

    @model_validator(mode="after")
    def _check_hash(self) -> "DocumentVersion":
        if self.canonical_text and self.text_hash != content_hash(self.canonical_text):
            raise ValueError("canonical_text/text_hash mismatch")
        return self


class Document(BaseModel):
    """文献聚合根：标识符去重 + 元数据 + 版本列表。"""

    id: UUID = Field(default_factory=new_id)
    identifiers: list[DocumentIdentifier] = Field(default_factory=list)
    title: str = ""
    journal: str = ""
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    publication_types: list[str] = Field(default_factory=list)
    versions: list[DocumentVersion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    def identity_key(self) -> str:
        """PMID > PMCID > DOI 去重键；缺失时由应用层走标题指纹+人工确认。"""
        by_kind = {i.kind: i.normalized().value for i in self.identifiers}
        for kind in ("pmid", "pmcid", "doi"):
            if by_kind.get(kind):
                return f"{kind}:{by_kind[kind]}"
        raise ValueError("document has no identifier; title-fingerprint needs manual confirmation")

    def latest_version(self) -> DocumentVersion | None:
        return self.versions[-1] if self.versions else None
