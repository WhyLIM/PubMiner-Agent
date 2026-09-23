"""PMID 规范化：清洗、去重、保序。

复刻 legacy 断点续传对已存在 PMID 的判定语义
（strip 后非空且不等于 'nan'）。
"""
from __future__ import annotations

_INVALID = {"", "nan", "NA", "none", "None", "0"}


def normalize_pmids(pmids: list[str | int | None]) -> list[str]:
    """清洗 PMID 列表：转字符串、去空白、丢弃无效项、保序去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in pmids:
        if raw is None:
            continue
        pmid = str(raw).strip()
        if pmid.lower() in _INVALID:
            continue
        if not pmid.isdigit():
            continue
        if pmid in seen:
            continue
        seen.add(pmid)
        result.append(pmid)
    return result
