"""MEDLINE 记录 → PubMedArticle 解析器。

字段映射以 legacy PubEx.py `create_record_dict` 为契约（golden test 保证一致）。
`record` 通常是 `Bio.Medline.parse` 的条目（str 键、str/str 列表值）。
"""
from __future__ import annotations

from typing import Mapping

from pubex.models.article import PubMedArticle
from pubex.models.identifiers import ArticleIdentifiers
from pubex.parsers.dates import extract_publication_date


def _first_lid_doi(record: Mapping[str, object]) -> str | None:
    """提取 DOI：LID 首个空格前字段（如 "10.1000/x [doi]" → "10.1000/x"）。

    LID 在 MEDLINE 中可为多值；legacy 仅处理单值，这里取首个元素保持等价且更稳健。
    优先 [doi] 类型标注，其次 [pmc-ref] 之外的首个 LID。
    """
    lid = record.get("LID")
    if lid is None:
        return None
    candidates = lid if isinstance(lid, list) else [lid]
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        if candidate.endswith(" [doi]"):
            return candidate.split(" ")[0]
    first = candidates[0]
    return first.split(" ")[0] if isinstance(first, str) and first else None


def _str(record: Mapping[str, object], key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) and value else None


def _list(record: Mapping[str, object], key: str) -> list[str] | None:
    value = record.get(key)
    if isinstance(value, list):
        items = [v for v in value if isinstance(v, str) and v]
        return items or None
    if isinstance(value, str) and value:
        return [value]
    return None


def medline_record_to_article(
    record: Mapping[str, object],
    *,
    cited_by_pmids: list[str] | None = None,
    reference_pmids: list[str] | None = None,
) -> PubMedArticle:
    """把一条 MEDLINE 记录解析为 PubMedArticle。

    Args:
        record: Bio.Medline.parse 的条目。
        cited_by_pmids: elink 得到的引用本文 PMID 列表。
        reference_pmids: elink 得到的参考文献 PMID 列表。
    """
    year = _str(record, "DP")
    if year is not None:
        year = year.split(" ")[0]

    return PubMedArticle(
        identifiers=ArticleIdentifiers(
            pmid=_str(record, "PMID"),
            pmcid=_str(record, "PMC"),
            doi=_first_lid_doi(record),
        ),
        title=_str(record, "TI"),
        status=_str(record, "STAT"),
        last_revision_date=_str(record, "LR"),
        issn=_str(record, "IS"),
        publication_type=record.get("PT") if isinstance(record.get("PT"), (str, list)) else None,
        year_of_publication=year,
        date_electronic_publication=_str(record, "DEP"),
        publication_date=extract_publication_date(record),
        place_of_publication=_str(record, "PL"),
        full_authors=_list(record, "FAU"),
        authors=_list(record, "AU"),
        affiliations=_list(record, "AD"),
        abstract=_str(record, "AB"),
        languages=_list(record, "LA"),
        keywords=_list(record, "OT"),
        medline_volume=_str(record, "VI"),
        medline_issue=_str(record, "IP"),
        medline_pagination=_str(record, "PG"),
        processing_history=_list(record, "PHST"),
        publication_status=_str(record, "PST"),
        journal_title_abbrev=_str(record, "TA"),
        journal_title=_str(record, "JT"),
        journal_id=_str(record, "JID"),
        source=_str(record, "SO"),
        grants=_list(record, "GR"),
        cited_by_pmids=cited_by_pmids or [],
        reference_pmids=reference_pmids or [],
    )
