"""PubMed 字段标签注册表与查询校验器。

LLM 生成的检索式可能包含不存在的字段标签（如 [biomarker]），
校验器在 SEARCH 执行前剥离非法标签，防止检索失败或结果偏差。
"""
from __future__ import annotations

import re

# NCBI E-utilities 支持的全部 PubMed 字段标签（qualified heading）
# 来源：https://pubmed.ncbi.nlm.nih.gov/help/#search-field-descriptions-and-tags
PUBMED_FIELD_TAGS: dict[str, str] = {
    # 常用
    "mesh": "MeSH Major Topic",
    "mesh terms": "MeSH Subheading",
    "tiab": "Title/Abstract",
    "ti": "Title",
    "ab": "Abstract",
    "tw": "Text Word",
    # 作者/期刊
    "au": "Author",
    "ta": "Journal Title Abbreviation",
    "ta all": "Journal Title (All)",
    # 日期
    "pdat": "Publication Date",
    "dp": "Date of Publication",
    "edat": "Entrez Date",
    # 类型
    "pt": "Publication Type",
    # 补充
    "nm": "Substance Name",
    "rn": "CAS Registry/EC Number",
    "cn": "Corporate Name",
    "cp": "Chemical Process",
    # 其他
    "ad": "Affiliation",
    "aid": "Article Identifier (DOI/PII)",
    "ci": "Correction/Retraction",
    "cr": "Corporate/Research Support",
    "gr": "Grant Number",
    "ip": "Issue",
    "is": "ISSN",
    "la": "Language",
    "loall": "Location (All)",
    "pg": "Pagination",
    "ps": "Personal Name as Subject",
    "sb": "Subset",
    "sh": "MeSH Subheading",
    "vi": "Volume",
    "vr": "Version",
}

# 常见合法标签别名（帮助 LLM 常见输出映射到正式标签）
_ALIASES: dict[str, str] = {
    "mesh terms": "mesh",
    "mesh major topic": "mesh",
    "title/abstract": "tiab",
    "text word": "tw",
    "abstract": "ab",
    "title": "ti",
    "author": "au",
    "publication type": "pt",
    "publication date": "pdat",
    "doi": "aid",
}

# 正则：匹配 [xxx] 形式的字段标签（在检索式中）
_TAG_PATTERN = re.compile(r"\[([^\[\]]+)\]", re.IGNORECASE)


def is_valid_tag(tag: str) -> bool:
    """检查字段标签是否在白名单中（大小写不敏感）。"""
    return tag.strip().lower() in PUBMED_FIELD_TAGS


def normalize_tag(tag: str) -> str:
    """将别名或大小写变体归一为白名单键。"""
    lower = tag.strip().lower()
    if lower in PUBMED_FIELD_TAGS:
        return lower
    if lower in _ALIASES:
        return _ALIASES[lower]
    return lower


def validate_query(query: str) -> tuple[str, list[str]]:
    """校验并修正检索式。

    返回 (cleaned_query, removed_tags)：
    - 非法标签被剥离（保留正文关键词），并报告被移除的标签
    - 合法标签保留原样
    """
    removed: list[str] = []

    def _replace(match: re.Match) -> str:
        tag_content = match.group(1).strip()
        if is_valid_tag(tag_content):
            return match.group(0)  # 合法，保留
        removed.append(tag_content)
        return ""  # 非法，剥离

    cleaned = _TAG_PATTERN.sub(_replace, query)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\b(?:AND|OR|NOT)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned, removed


def format_available_tags() -> str:
    """格式化白名单，供 prompt 注入。"""
    lines = []
    for tag, desc in sorted(PUBMED_FIELD_TAGS.items(), key=lambda x: x[0]):
        lines.append(f"  [{tag}] = {desc}")
    return "\n".join(lines)
