"""PubMed XML record → PubMedRecord 纯解析函数（离线可测，迁移自 webui `_parse_pubmed_record`）。"""
from __future__ import annotations

import re
from typing import Any, Mapping

from pubex.models.pubmed_record import PubMedRecord


def coerce_value(value: Any) -> str:
    """Bio.Entrez 解析对象 → 干净字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        direct = value.get("_")
        if direct:
            return str(direct).strip()
    text = str(value).strip()
    return "" if text in {"None", "{}"} else text


def element_attr(value: Any, name: str) -> str:
    """读取 Bio.Entrez 元素的 XML 属性。

    DTD 校验模式下属性在元素的 `.attributes`；个别无 DTD 路径可能在 dict 键
    （含 "@" 前缀）。三种形态都兼容，保证对真实 API 响应与 fixture 一致。
    """
    attrs = getattr(value, "attributes", None)
    if isinstance(attrs, dict) and name in attrs:
        return str(attrs[name])
    if isinstance(value, dict):
        for key in (name, f"@{name}"):
            if key in value:
                return str(value[key])
    return ""


def extract_pmid(record: Mapping[str, Any]) -> str:
    pmid = (record.get("MedlineCitation") or {}).get("PMID", "")
    if pmid:
        return str(pmid)
    for aid in (record.get("PubmedData") or {}).get("ArticleIdList", []):
        if element_attr(aid, "IdType") == "pubmed":
            return str(aid)
    return ""


def _extract_numeric_component(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"\d{1,2}", value)
    return match.group(0).zfill(2) if match else ""


def normalize_month(month_value: str) -> str:
    if not month_value:
        return ""
    month_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
        "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    lowered = month_value.lower()
    if lowered[:3] in month_map:
        return month_map[lowered[:3]]
    return _extract_numeric_component(month_value)


def format_history_date(date_entry: Mapping[str, Any]) -> str:
    year = coerce_value(date_entry.get("Year", ""))
    month = normalize_month(coerce_value(date_entry.get("Month", "")))
    day = _extract_numeric_component(coerce_value(date_entry.get("Day", "")))
    if not year:
        return ""
    if month and day:
        return f"{year}-{month}-{day}"
    if month:
        return f"{year}-{month}"
    return year


def extract_last_revision_date(history: Any) -> str:
    if not isinstance(history, list) or not history:
        return ""
    normalized: list[tuple[str, str]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        pub_status = (element_attr(entry, "PubStatus") or str(entry.get("PubStatus", "") or "")).lower()
        formatted = format_history_date(entry)
        if formatted:
            normalized.append((pub_status, formatted))
    if not normalized:
        return ""
    for pub_status, formatted in normalized:
        if pub_status == "revised":
            return formatted
    return normalized[-1][1]


def parse_pubmed_record(record: Mapping[str, Any]) -> PubMedRecord:
    """Bio.Entrez.read 的 PubmedArticle 条目 → PubMedRecord。"""
    citation = record.get("MedlineCitation", {}) or {}
    article = citation.get("Article", {}) or {}
    pmid = extract_pmid(record)

    title = article.get("ArticleTitle", "")
    if isinstance(title, list):
        title = " ".join(str(t) for t in title)

    authors: list[str] = []
    first_author = ""
    affiliation = ""
    author_list = article.get("AuthorList", []) or []
    for idx, author in enumerate(author_list):
        if not isinstance(author, dict):
            continue
        last = author.get("LastName", "")
        fore = author.get("ForeName", "") or author.get("Initials", "")
        if last:
            name = f"{last} {fore}".strip()
            authors.append(name)
            if idx == 0:
                first_author = name
                aff_info = author.get("AffiliationInfo", []) or []
                if aff_info and isinstance(aff_info[0], dict):
                    affiliation = aff_info[0].get("Affiliation", "")

    journal_info = article.get("Journal", {}) or {}
    journal_issue = journal_info.get("JournalIssue", {}) or {}
    pub_date_obj = journal_issue.get("PubDate", {}) or {}

    year = int(pub_date_obj.get("Year", 0)) or None
    pub_date = f"{year}" if year else None
    medline_date = pub_date_obj.get("MedlineDate", "")
    if medline_date:
        pub_date = str(medline_date)

    pagination = article.get("Pagination", {}) or {}

    abstract_parts: list[str] = []
    abstract = article.get("Abstract", {}) or {}
    for text in abstract.get("AbstractText", []) or []:
        if isinstance(text, str):
            label = element_attr(text, "Label")
            content = str(text).strip()
            if label and content:
                abstract_parts.append(f"{label}: {content}")
            else:
                abstract_parts.append(content)
        elif isinstance(text, dict):
            label = element_attr(text, "Label")
            content = text.get("_", "")
            if label and content:
                abstract_parts.append(f"{label}: {content}")
            elif content:
                abstract_parts.append(content)

    keywords: list[str] = []
    for kw_list in citation.get("KeywordList", []) or []:
        for kw in kw_list:
            if isinstance(kw, str):
                keywords.append(kw)

    mesh_terms: list[str] = []
    for mesh in citation.get("MeshHeadingList", []) or []:
        descriptor = mesh.get("DescriptorName", "")
        if isinstance(descriptor, dict):
            mesh_terms.append(descriptor.get("_", str(descriptor)))
        elif descriptor:
            mesh_terms.append(str(descriptor))

    language_list = article.get("Language", []) or []
    publication_types = article.get("PublicationTypeList", []) or []

    medline_status = coerce_value(citation.get("Status", ""))
    pubmed_data = record.get("PubmedData", {}) or {}
    publication_status = coerce_value(pubmed_data.get("PublicationStatus", ""))

    grant_strs: list[str] = []
    for grant in article.get("GrantList", []) or []:
        if isinstance(grant, dict):
            agency = grant.get("Agency", "")
            grant_id = grant.get("GrantID", "")
            if agency or grant_id:
                grant_strs.append(f"{agency}: {grant_id}".strip(": "))

    doi = None
    pmcid = None
    has_pmc_fulltext = False
    for aid in pubmed_data.get("ArticleIdList", []) or []:
        aid_type = element_attr(aid, "IdType") or getattr(aid, "attributes", {}).get("IdType", "")
        aid_value = str(aid)
        if aid_type == "doi":
            doi = aid_value
        elif aid_type == "pmc":
            pmcid = aid_value
            has_pmc_fulltext = True
    for other_id in pubmed_data.get("OtherID", []) or []:
        if str(other_id).startswith("PMC"):
            pmcid = str(other_id)
            has_pmc_fulltext = True

    return PubMedRecord(
        pmid=pmid,
        pmcid=pmcid,
        doi=doi,
        title=title,
        authors=authors,
        first_author=first_author,
        affiliation=affiliation,
        journal=journal_info.get("Title", ""),
        journal_abbrev=journal_info.get("ISOAbbreviation", ""),
        issn=journal_info.get("ISSN", ""),
        journal_id=journal_issue.get("Issue", ""),
        pub_date=pub_date,
        year=year,
        volume=journal_issue.get("Volume", ""),
        issue=journal_issue.get("Issue", ""),
        pages=pagination.get("MedlinePgn", ""),
        publication_status=publication_status,
        article_type=coerce_value(publication_types[0]) if publication_types else "",
        abstract=" ".join(abstract_parts),
        keywords=keywords,
        mesh_terms=mesh_terms,
        language=coerce_value(language_list[0]) if language_list else "",
        status=publication_status or medline_status,
        last_revision_date=extract_last_revision_date(pubmed_data.get("History", [])),
        grant_list="; ".join(grant_strs),
        has_pmc_fulltext=has_pmc_fulltext,
    )
