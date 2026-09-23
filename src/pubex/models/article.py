"""PubMed 文章 typed 模型与 legacy CSV 契约。

`to_legacy_row()` 复刻 legacy PubEx.py `create_record_dict` 的字段映射语义，
作为字段映射 golden test 的契约（PR-003）。差异点均已注明。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from pubex.models.identifiers import ArticleIdentifiers

#: legacy PubEx.py 输出的 32 列 CSV，列顺序即契约，不得变更
LEGACY_CSV_COLUMNS: tuple[str, ...] = (
    "Title",
    "Status",
    "Last Revision Date",
    "ISSN",
    "Type",
    "Year of Publication",
    "Date of Electronic Publication",
    "Publication Date",
    "Place of Publication",
    "F_Author",
    "Author",
    "Affiliation",
    "Abstract",
    "Language",
    "Keywords",
    "PMID",
    "Medline Volume",
    "Medline Issue",
    "Medline Pagination",
    "DOI",
    "PMC",
    "Processing History",
    "Publication Status",
    "Journal Title Abbreviation",
    "Journal Title",
    "Journal ID",
    "Source",
    "Grant List",
    "cited",
    "cited_by",
    "References",
    "References_PMID",
)

_NA = "NA"


def _na(value: str | list[str] | None) -> str | list[str]:
    """缺失值回退为 'NA'（legacy 语义）。空列表视为缺失。"""
    if value is None or value == []:
        return _NA
    return value


class PubMedArticle(BaseModel):
    """一篇 PubMed 文章的规范化元数据。

    所有字段缺失时为 None（或空容器），序列化为 legacy CSV 时统一回退 'NA'。
    """

    identifiers: ArticleIdentifiers = Field(default_factory=ArticleIdentifiers)

    title: str | None = None
    status: str | None = None                    # STAT
    last_revision_date: str | None = None        # LR
    issn: str | None = None                      # IS
    publication_type: str | list[str] | None = None  # PT（MEDLINE 中可为多值）
    year_of_publication: str | None = None       # DP 首个空格前字段
    date_electronic_publication: str | None = None  # DEP
    publication_date: str | None = None          # 由 DP/SO 正则提取（YYYY Mon D）
    place_of_publication: str | None = None      # PL
    full_authors: list[str] | None = None        # FAU
    authors: list[str] | None = None             # AU
    affiliations: list[str] | None = None        # AD
    abstract: str | None = None                  # AB
    languages: list[str] | None = None           # LA
    keywords: list[str] | None = None            # OT
    medline_volume: str | None = None            # VI
    medline_issue: str | None = None             # IP
    medline_pagination: str | None = None        # PG
    processing_history: list[str] | None = None  # PHST
    publication_status: str | None = None        # PST
    journal_title_abbrev: str | None = None      # TA
    journal_title: str | None = None             # JT
    journal_id: str | None = None                # JID
    source: str | None = None                    # SO
    grants: list[str] | None = None              # GR

    # 引用关系（由 CitationClient 提供，非 MEDLINE 原生字段）
    cited_by_pmids: list[str] = Field(default_factory=list, description="引用本文的 PMID 列表")
    reference_pmids: list[str] = Field(default_factory=list, description="本文参考文献 PMID 列表")

    @property
    def pmid(self) -> str | None:
        return self.identifiers.pmid

    @property
    def cited_count(self) -> int:
        return len(self.cited_by_pmids)

    @property
    def reference_count(self) -> int:
        return len(self.reference_pmids)

    def to_legacy_row(self) -> dict[str, str | int | list[str]]:
        """输出与 legacy PubEx.create_record_dict 完全一致的 32 列记录。

        语义差异（有意为之，均在缺失行为上等价）：
        - DOI：legacy 仅取 LID 首个空格前字段；当 LID 为多值列表时 legacy 会
          AttributeError，这里取首个元素再按同样规则切分（更稳健，单值时逐字节一致）。
        """
        doi = self.identifiers.doi
        year = self.year_of_publication
        return {
            "Title": _na(self.title),
            "Status": _na(self.status),
            "Last Revision Date": _na(self.last_revision_date),
            "ISSN": _na(self.issn),
            "Type": _na(self.publication_type),
            "Year of Publication": _na(year),
            "Date of Electronic Publication": _na(self.date_electronic_publication),
            "Publication Date": _na(self.publication_date),
            "Place of Publication": _na(self.place_of_publication),
            "F_Author": _na(self.full_authors),
            "Author": _na(self.authors),
            "Affiliation": _na(self.affiliations),
            "Abstract": _na(self.abstract),
            "Language": _na(self.languages),
            "Keywords": _na(self.keywords),
            "PMID": _na(self.identifiers.pmid),
            "Medline Volume": _na(self.medline_volume),
            "Medline Issue": _na(self.medline_issue),
            "Medline Pagination": _na(self.medline_pagination),
            "DOI": _na(doi),
            "PMC": _na(self.identifiers.pmcid),
            "Processing History": _na(self.processing_history),
            "Publication Status": _na(self.publication_status),
            "Journal Title Abbreviation": _na(self.journal_title_abbrev),
            "Journal Title": _na(self.journal_title),
            "Journal ID": _na(self.journal_id),
            "Source": _na(self.source),
            "Grant List": _na(self.grants),
            "cited": self.cited_count,
            "cited_by": self.cited_by_pmids,
            "References": self.reference_count,
            "References_PMID": self.reference_pmids,
        }
