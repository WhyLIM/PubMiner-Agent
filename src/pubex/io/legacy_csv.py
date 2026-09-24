"""Legacy CSV 读写器与导入器。

- `write_legacy_csv`：按 legacy 32 列契约写出（含备份文件语义），用于与旧流程互操作；
- `read_legacy_pmids` / `iter_legacy_articles`：把历史 CSV 断点数据或存量导入为 typed
  rows（设计文档 §2.3 "Legacy CSV Importer"；导入仅生成候选数据，不进入任何发布状态）。

注意：列表单元格沿用 legacy 的 pandas 序列化行为（str(list)），保证与历史文件逐字节可比。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from pubex.models.article import LEGACY_CSV_COLUMNS, PubMedArticle

_NA = "NA"


def _cell_to_value(raw: object) -> str | list[str]:
    """CSV 单元格 → legacy 行值。列表单元格在 CSV 中是 str(list) 形式。"""
    text = "" if raw is None else str(raw)
    if text == _NA or text == "":
        return _NA
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text.replace("'", '"'))
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
    return text


def write_legacy_csv(
    articles: list[PubMedArticle],
    fname: str | Path,
    *,
    overwrite_backup: bool = True,
) -> Path:
    """把 PubMedArticle 列表写出为 legacy 契约 CSV，并写备份文件。"""
    rows = [article.to_legacy_row() for article in articles]
    df = pd.DataFrame(rows, columns=LEGACY_CSV_COLUMNS)
    df = df.fillna(_NA)

    fname = Path(fname)
    fname.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(fname, index=False, na_rep=_NA)

    if overwrite_backup:
        backup = fname.with_name(f"{fname.stem}_backup{fname.suffix}")
    else:
        backup = fname.with_name(f"{fname.stem}_backup_{datetime.now():%Y%m%d%H%M%S}{fname.suffix}")
    df.to_csv(backup, index=False, na_rep=_NA)
    return fname


def read_legacy_pmids(fname: str | Path) -> set[str]:
    """读取 legacy CSV 已处理 PMID 集合（断点续传语义，与 legacy check_existing_data 一致）。"""
    fname = Path(fname)
    if not fname.exists() or fname.stat().st_size == 0:
        return set()
    df = pd.read_csv(fname, keep_default_na=False, na_values=[""])
    valid = df["PMID"].dropna().astype(str)
    return {pmid for pmid in valid if pmid.strip() and pmid != "nan"}


def iter_legacy_articles(fname: str | Path) -> Iterator[dict[str, str | list[str] | int]]:
    """逐行读取 legacy CSV 为规范化记录字典（列名 → 清洗后的值）。

    该入口用于把历史数据导入证据平台（documents / legacy_import_batches）；
    调用方负责来源标注，导入结果永远是候选状态。
    """
    fname = Path(fname)
    if not fname.exists() or fname.stat().st_size == 0:
        return
    df = pd.read_csv(fname, keep_default_na=False, na_values=[""])
    for _, row in df.iterrows():
        record: dict[str, str | list[str] | int] = {}
        for column in LEGACY_CSV_COLUMNS:
            if column not in df.columns:
                continue
            raw = row[column]
            if column in ("cited", "References"):
                record[column] = int(raw) if str(raw).strip().isdigit() else 0
            elif column in ("cited_by", "References_PMID"):
                value = _cell_to_value(raw)
                record[column] = value if isinstance(value, list) else []
            else:
                record[column] = _cell_to_value(raw)
        yield record


def legacy_row_to_article(row: dict[str, object]) -> PubMedArticle:
    """把 legacy 行（或 iter_legacy_articles 的输出）还原为 PubMedArticle。"""
    from pubex.models.identifiers import ArticleIdentifiers

    def text(column: str) -> str | None:
        value = row.get(column, _NA)
        if value is None:
            return None
        value = str(value)
        return None if value in (_NA, "") else value

    def text_list(column: str) -> list[str] | None:
        value = row.get(column, _NA)
        if isinstance(value, list):
            return value or None
        return None if value in (_NA, "", None) else [str(value)]

    return PubMedArticle(
        identifiers=ArticleIdentifiers(
            pmid=text("PMID"),
            pmcid=text("PMC"),
            doi=text("DOI"),
        ),
        title=text("Title"),
        status=text("Status"),
        last_revision_date=text("Last Revision Date"),
        issn=text("ISSN"),
        publication_type=text_list("Type"),
        year_of_publication=text("Year of Publication"),
        date_electronic_publication=text("Date of Electronic Publication"),
        publication_date=text("Publication Date"),
        place_of_publication=text("Place of Publication"),
        full_authors=text_list("F_Author"),
        authors=text_list("Author"),
        affiliations=text_list("Affiliation"),
        abstract=text("Abstract"),
        languages=text_list("Language"),
        keywords=text_list("Keywords"),
        medline_volume=text("Medline Volume"),
        medline_issue=text("Medline Issue"),
        medline_pagination=text("Medline Pagination"),
        processing_history=text_list("Processing History"),
        publication_status=text("Publication Status"),
        journal_title_abbrev=text("Journal Title Abbreviation"),
        journal_title=text("Journal Title"),
        journal_id=text("Journal ID"),
        source=text("Source"),
        grants=text_list("Grant List"),
        cited_by_pmids=text_list("cited_by") or [],
        reference_pmids=text_list("References_PMID") or [],
    )
