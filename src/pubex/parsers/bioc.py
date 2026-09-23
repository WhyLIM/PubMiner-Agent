"""BioC 文档解析：section 分类 + 稳定 passage 定位。

迁移自 PubMiner-webui `pubminer/downloader/section_parser.py`（保留分类词典与
启发式），新增：
- 逐 passage 的稳定 offset（相对 canonical text）与 text_hash；
- DocumentVersion 组装，供 EvidenceSpan grounding 使用（设计文档 §6.1）。
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Mapping

from pubex.models.document import DocumentVersion, LicenseRecord

__all__ = [
    "SectionType",
    "SECTION_TITLE_MAP",
    "DEFAULT_KEEP_SECTIONS",
    "BiocSectionParser",
]


class SectionType(Enum):
    """文献 section 类型（值与 webui 版本一致，作跨系统契约）。"""

    ABSTRACT = "ABSTRACT"
    INTRODUCTION = "INTRO"
    METHODS = "METHODS"
    RESULTS = "RESULTS"
    DISCUSSION = "DISCUSSION"
    CONCLUSION = "CONCLUSION"
    REFERENCES = "REFERENCES"
    ACKNOWLEDGMENTS = "ACK"
    SUPPLEMENT = "SUPPL"
    OTHER = "OTHER"


SECTION_TITLE_MAP: dict[str, SectionType] = {
    "abstract": SectionType.ABSTRACT,
    "summary": SectionType.ABSTRACT,
    "background abstract": SectionType.ABSTRACT,
    "author summary": SectionType.ABSTRACT,
    "structured abstract": SectionType.ABSTRACT,
    "plain language summary": SectionType.ABSTRACT,
    "introduction": SectionType.INTRODUCTION,
    "background": SectionType.INTRODUCTION,
    "background and objectives": SectionType.INTRODUCTION,
    "objectives": SectionType.INTRODUCTION,
    "introduction and background": SectionType.INTRODUCTION,
    "research in context": SectionType.INTRODUCTION,
    "overview": SectionType.INTRODUCTION,
    "methods": SectionType.METHODS,
    "methodology": SectionType.METHODS,
    "materials and methods": SectionType.METHODS,
    "materials & methods": SectionType.METHODS,
    "patients and methods": SectionType.METHODS,
    "study design and methods": SectionType.METHODS,
    "experimental procedures": SectionType.METHODS,
    "study population": SectionType.METHODS,
    "participants": SectionType.METHODS,
    "data and methods": SectionType.METHODS,
    "method": SectionType.METHODS,
    "statistical analysis": SectionType.METHODS,
    "statistical methods": SectionType.METHODS,
    "results": SectionType.RESULTS,
    "findings": SectionType.RESULTS,
    "outcomes": SectionType.RESULTS,
    "main results": SectionType.RESULTS,
    "key results": SectionType.RESULTS,
    "observations": SectionType.RESULTS,
    "discussion": SectionType.DISCUSSION,
    "comments": SectionType.DISCUSSION,
    "interpretation": SectionType.DISCUSSION,
    "discussion and conclusion": SectionType.DISCUSSION,
    "general discussion": SectionType.DISCUSSION,
    "conclusion": SectionType.CONCLUSION,
    "conclusions": SectionType.CONCLUSION,
    "concluding remarks": SectionType.CONCLUSION,
    "final remarks": SectionType.CONCLUSION,
    "conclusion and future directions": SectionType.CONCLUSION,
    "key messages": SectionType.CONCLUSION,
    "references": SectionType.REFERENCES,
    "bibliography": SectionType.REFERENCES,
    "literature cited": SectionType.REFERENCES,
    "notes": SectionType.REFERENCES,
    "acknowledgments": SectionType.ACKNOWLEDGMENTS,
    "acknowledgements": SectionType.ACKNOWLEDGMENTS,
    "funding": SectionType.ACKNOWLEDGMENTS,
    "author contributions": SectionType.ACKNOWLEDGMENTS,
    "competing interests": SectionType.ACKNOWLEDGMENTS,
    "conflict of interest": SectionType.ACKNOWLEDGMENTS,
    "ethics statement": SectionType.ACKNOWLEDGMENTS,
    "supplementary": SectionType.SUPPLEMENT,
    "supplementary material": SectionType.SUPPLEMENT,
    "supplementary data": SectionType.SUPPLEMENT,
    "appendix": SectionType.SUPPLEMENT,
    "supporting information": SectionType.SUPPLEMENT,
}

DEFAULT_KEEP_SECTIONS = [
    SectionType.ABSTRACT,
    SectionType.INTRODUCTION,
    SectionType.METHODS,
    SectionType.RESULTS,
    SectionType.DISCUSSION,
    SectionType.CONCLUSION,
]

_METHOD_PATTERNS = [
    "we used", "we performed", "was measured", "statistical analysis",
    "participants were", "study design", "inclusion criteria", "data collection",
    "retrospective cohort", "prospective cohort", "randomized", "cross-sectional",
    "logistic regression", "multivariable",
]
_RESULT_PATTERNS = [
    "we found", "results showed", "significantly", "p <", "p=", "table 1",
    "figure 1", "odds ratio", "hazard ratio", "confidence interval",
    "was associated with",
]
_DISCUSSION_PATTERNS = [
    "our findings", "this study", "previous studies", "consistent with",
    "in contrast to", "limitations", "these findings suggest", "in summary",
    "the present study",
]
_INTRO_PATTERNS = [
    "little is known", "remains unclear", "we aimed to",
    "the purpose of this study", "the aim of this study", "background",
]
_CONCLUSION_PATTERNS = [
    "in conclusion", "we conclude", "our results suggest", "taken together",
    "future studies",
]


class BiocSectionParser:
    """BioC JSON → 分类 sections / 带 offset 的 DocumentVersion。"""

    def __init__(
        self,
        keep_sections: list[SectionType] | None = None,
        min_section_length: int = 50,
    ):
        self.keep_sections = keep_sections or DEFAULT_KEEP_SECTIONS
        self.min_section_length = min_section_length

    # ------------------------------------------------------------------ parsing

    def normalize_heading(self, text: str) -> str:
        normalized = text.lower().strip()
        normalized = re.sub(r"^[\d\W_]+", "", normalized)
        normalized = re.sub(r"[\d\W_]+$", "", normalized)
        normalized = normalized.replace("&", " and ")
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"^(section|sec)\s+\d+[:.]?\s*", "", normalized)
        normalized = re.sub(r"^\d+(\.\d+)*\s+", "", normalized)
        return normalized.strip(" :.-")

    def classify_section(self, passage: Mapping[str, Any]) -> SectionType:
        infons = passage.get("infons", {}) or {}
        for candidate in (
            infons.get("section_type", ""), infons.get("type", ""),
            infons.get("section", ""), infons.get("title", ""),
            infons.get("heading", ""), infons.get("subtitle", ""),
            infons.get("label", ""),
        ):
            if not candidate:
                continue
            section_type = self.match_section_type(str(candidate))
            if section_type != SectionType.OTHER:
                return section_type

        passage_type = str(infons.get("type", "")).lower()
        if passage_type in {"abstract", "title_abstract"}:
            return SectionType.ABSTRACT

        section_type = self._infer_from_content(str(passage.get("text", "")))
        if section_type != SectionType.OTHER:
            return section_type
        return SectionType.OTHER

    def match_section_type(self, text: str) -> SectionType:
        text_lower = self.normalize_heading(text)
        if text_lower in SECTION_TITLE_MAP:
            return SECTION_TITLE_MAP[text_lower]
        for key, section_type in SECTION_TITLE_MAP.items():
            if key in text_lower or text_lower in key:
                return section_type
        if any(term in text_lower for term in ["method", "materials", "participant", "protocol"]):
            return SectionType.METHODS
        if any(term in text_lower for term in ["result", "finding", "outcome", "observation"]):
            return SectionType.RESULTS
        if any(term in text_lower for term in ["discussion", "interpretation", "implication"]):
            return SectionType.DISCUSSION
        if any(term in text_lower for term in ["conclusion", "concluding", "summary"]):
            return SectionType.CONCLUSION
        if any(term in text_lower for term in ["reference", "bibliography", "works cited"]):
            return SectionType.REFERENCES
        if re.match(r"^\d+\.", text_lower) or "et al" in text_lower[:100]:
            return SectionType.REFERENCES
        return SectionType.OTHER

    def _infer_from_content(self, text: str) -> SectionType:
        text_lower = text.lower()[:500]
        scores = {
            SectionType.INTRODUCTION: sum(1 for p in _INTRO_PATTERNS if p in text_lower),
            SectionType.METHODS: sum(1 for p in _METHOD_PATTERNS if p in text_lower),
            SectionType.RESULTS: sum(1 for p in _RESULT_PATTERNS if p in text_lower),
            SectionType.DISCUSSION: sum(1 for p in _DISCUSSION_PATTERNS if p in text_lower),
            SectionType.CONCLUSION: sum(1 for p in _CONCLUSION_PATTERNS if p in text_lower),
        }
        max_score = max(scores.values())
        if max_score == 0:
            return SectionType.OTHER
        return next(section for section, score in scores.items() if score == max_score)

    # ------------------------------------------------------------------ payloads

    @staticmethod
    def get_passages(bioc_data: Any) -> list[dict[str, Any]]:
        """从 BioC JSON（dict 或 [collection]）取文档 passages。"""
        if not bioc_data:
            return []
        if isinstance(bioc_data, list):
            if not bioc_data:
                return []
            bioc_data = bioc_data[0]
        if not isinstance(bioc_data, dict):
            return []
        documents = bioc_data.get("documents", [])
        if not documents:
            return []
        return documents[0].get("passages", [])

    @staticmethod
    def extract_title(bioc_data: Any) -> str:
        for passage in BiocSectionParser.get_passages(bioc_data):
            infons = passage.get("infons", {}) or {}
            if infons.get("type") == "title":
                return str(passage.get("text", ""))
        return ""

    def parse_sections(self, bioc_data: Any) -> dict[SectionType, str]:
        """分类聚合 section 文本（min_section_length 过滤），供浏览与诊断。"""
        sections: dict[SectionType, str] = {}
        for passage in self.get_passages(bioc_data):
            text = str(passage.get("text", "")).strip()
            if len(text) < self.min_section_length:
                continue
            section_type = self.classify_section(passage)
            if section_type in sections:
                sections[section_type] += "\n\n" + text
            else:
                sections[section_type] = text
        return sections

    def section_summary(self, bioc_data: Any) -> dict[str, int]:
        return {
            section_type.value: len(text)
            for section_type, text in self.parse_sections(bioc_data).items()
        }

    def build_document_version(
        self,
        bioc_data: Any,
        *,
        pmid: str | None = None,
        pmcid: str | None = None,
        license_record: LicenseRecord | None = None,
        keep_raw: bool = False,
    ) -> DocumentVersion:
        """把 BioC 文档组装为带稳定 passage offset 的 DocumentVersion。

        每个非 body passage（title/references/ack 等）也保留定位，但 canonical text
        只包含 keep_sections + OTHER 的正文（与 filtered_text 语义一致）。
        offset 相对 canonical text，text_hash 校验内容一致性。
        """
        sections: list[tuple[str, str]] = []
        for passage in self.get_passages(bioc_data):
            infons = passage.get("infons", {}) or {}
            if str(infons.get("type", "")).lower() == "title":
                continue  # title 单独存于 DocumentVersion.title，不入正文
            text = str(passage.get("text", "")).strip()
            if len(text) < self.min_section_length:
                continue
            section_type = self.classify_section(passage)
            if section_type in {SectionType.REFERENCES, SectionType.ACKNOWLEDGMENTS, SectionType.SUPPLEMENT}:
                continue
            label = section_type.value if section_type != SectionType.OTHER else "OTHER"
            sections.append((label, text))

        doc = DocumentVersion.from_sections(
            pmid=pmid,
            pmcid=pmcid,
            title=self.extract_title(bioc_data),
            sections=sections,
            license_record=license_record,
            raw_bioc=bioc_data if keep_raw else None,
        )
        return doc

    # -------------------------------------------------- legacy-compatible API

    def get_filtered_text(self, bioc_data: Any, include_section_headers: bool = True) -> str:
        """兼容 webui：按 keep_sections 顺序输出带 [SECTION] 头的筛选文本。"""
        sections = self.parse_sections(bioc_data)
        order = [
            SectionType.ABSTRACT, SectionType.INTRODUCTION, SectionType.METHODS,
            SectionType.RESULTS, SectionType.DISCUSSION, SectionType.CONCLUSION,
        ]
        parts = []
        for section_type in order:
            if section_type in self.keep_sections and section_type in sections:
                text = sections[section_type].strip()
                if text:
                    if include_section_headers:
                        parts.append(f"[{section_type.value}]\n{text}")
                    else:
                        parts.append(text)
        return "\n\n".join(parts)

    def get_fallback_text(self, bioc_data: Any, include_section_headers: bool = True) -> str:
        passages = self.get_passages(bioc_data)
        parts: list[str] = []
        for passage in passages:
            text = str(passage.get("text", "")).strip()
            if len(text) < self.min_section_length:
                continue
            section_type = self.classify_section(passage)
            if section_type in {SectionType.REFERENCES, SectionType.ACKNOWLEDGMENTS, SectionType.SUPPLEMENT}:
                continue
            if include_section_headers and section_type != SectionType.OTHER:
                parts.append(f"[{section_type.value}]\n{text}")
            else:
                parts.append(text)
        return "\n\n".join(parts)
