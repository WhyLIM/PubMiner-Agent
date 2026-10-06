"""真实数据端口适配器：把 pubex SDK 接到 MiningWorkflow 的 Search/Hydrate 端口。

pubex 客户端是 asyncio 风格；通过 LoopRunner 暴露同步接口。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pubminer.domain.documents import Document, DocumentIdentifier, DocumentVersion
from pubminer.workflows.ports import HydratedDocument, SearchIntent
from pubminer.integrations.loop_runner import LoopRunner

logger = logging.getLogger("pubminer.adapters.pubmed")

_MAX_ABSTRACT_CHARS = 8000


class PubexSearchAdapter:
    """PubMed esearch → workflow SEARCH 端口。"""

    def __init__(self, search_client: Any, loop: LoopRunner) -> None:
        self.search_client = search_client
        self.loop = loop

    def search(self, intent: SearchIntent) -> list[dict]:
        date_range = None
        if intent.date_range:
            date_range = (str(intent.date_range[0]), str(intent.date_range[1]))
        page = self.loop.run(
            self.search_client.search(
                intent.query,
                max_results=intent.max_results,
                date_range=date_range,
            )
        )
        return [{"pmid": pmid} for pmid in page.pmids]


class PubexHydrateAdapter:
    """PMID → 元数据 + （可得时）PMC OA 全文，否则降级为 title+abstract。

    输出的 domain Document/DocumentVersion 与 MiningWorkflow 的序列化
    契约对齐：canonical_text 为 offset 基准，section_spans 相对其计算。
    """

    def __init__(
        self,
        metadata_client: Any,
        pmc_client: Any | None,
        loop: LoopRunner,
        *,
        include_fulltext: bool = True,
    ) -> None:
        self.metadata_client = metadata_client
        self.pmc_client = pmc_client
        self.loop = loop
        self.include_fulltext = include_fulltext

    PMC_FETCH_WORKERS = 6  # PMC OA 无 key 限流宽松；元数据仍走批量 efetch

    def hydrate_many(self, pmids: list[str]) -> list[HydratedDocument | None]:
        """批量水合：一次 efetch 取全部元数据，PMC 全文抓取有限并发。

        LoopRunner 通过 run_coroutine_threadsafe 提交到专用事件循环，
        多线程调用安全；单篇失败（含 PMC 瞬断）返回 None 不阻断。
        """
        if not pmids:
            return []
        records = self.loop.run(self.metadata_client.fetch_batch(pmids, batch_size=max(len(pmids), 1)))
        by_pmid = {r.pmid: r for r in records}
        results: list[HydratedDocument | None] = [None] * len(pmids)
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=self.PMC_FETCH_WORKERS) as pool:
            futures = {
                idx: pool.submit(self._hydrate_one_safe, by_pmid.get(pmid), pmid)
                for idx, pmid in enumerate(pmids)
            }
            for idx, future in futures.items():
                results[idx] = future.result()
        return results

    def _hydrate_one_safe(self, record, pmid: str) -> HydratedDocument | None:
        if record is None:
            return None
        try:
            return self._build_hydrated(record, pmid)
        except Exception as exc:
            logger.warning("hydrate failed for %s: %s", pmid, exc)
            return None

    def hydrate(self, pmid: str) -> HydratedDocument | None:
        records = self.loop.run(self.metadata_client.fetch_batch([pmid], batch_size=1))
        if not records:
            return None
        return self._build_hydrated(records[0], pmid)

    def _build_hydrated(self, record, pmid: str) -> HydratedDocument:

        identifiers = [DocumentIdentifier(kind="pmid", value=record.pmid)]
        if record.pmcid:
            identifiers.append(DocumentIdentifier(kind="pmcid", value=record.pmcid))
        if record.doi:
            identifiers.append(DocumentIdentifier(kind="doi", value=record.doi))

        document = Document(
            identifiers=identifiers, title=record.title or "",
            journal=record.journal, year=record.year,
            authors=list(record.authors), abstract=record.abstract or "",
        )

        fulltext = self._try_pmc_fulltext(record) if self.include_fulltext else None
        if fulltext is not None:
            pubex_version, license_name = fulltext
            domain_version = DocumentVersion(
                document_id=document.id, title=document.title,
                canonical_text=pubex_version.canonical_text,
                license=license_name, source="pmc-oa",
                retrieved_at=datetime.now(timezone.utc),
            )
            spans = [(p.section_path, p.start_char, p.end_char) for p in pubex_version.passages]
            return HydratedDocument(
                document=document, version=domain_version,
                section_spans=spans, fulltext_available=True,
            )

        sections = self._abstract_sections(document.title, document.abstract)
        version = DocumentVersion(
            document_id=document.id, title=document.title,
            canonical_text="\n\n".join(text for _, text in sections),
            source="pubmed-abstract", retrieved_at=datetime.now(timezone.utc),
        )
        spans = self._spans_for_sections(version.canonical_text, sections)
        return HydratedDocument(
            document=document, version=version,
            section_spans=spans, fulltext_available=False,
        )

    @staticmethod
    def _abstract_sections(title: str, abstract: str) -> list[tuple[str, str]]:
        sections = []
        if title:
            sections.append(("TITLE", title))
        if abstract:
            sections.append(("ABSTRACT", abstract[:8000]))
        return sections

    @staticmethod
    def _spans_for_sections(canonical: str, sections):
        spans = []
        offset = 0
        for path, text in sections:
            start = offset
            offset = start + len(text) + 2
            spans.append((path, start, start + len(text)))
        return spans


    def _try_pmc_fulltext(self, record) -> tuple[Any, str | None] | None:
        if not record.pmcid or self.pmc_client is None:
            return None

        async def _fetch():
            import aiohttp

            async with aiohttp.ClientSession() as session:
                return await self.pmc_client.get_document_with_status(
                    session, record.pmcid, record.pmid
                )

        try:
            document, status = self.loop.run(_fetch())
        except Exception as exc:  # PMC 瞬断不应阻断整条水合
            logger.warning("PMC fulltext fetch failed for %s: %s", record.pmid, exc)
            return None
        if document is None:
            logger.info(
                "no PMC OA fulltext for %s (%s)", record.pmid, status.get("reason")
            )
            return None
        license_name = document.license.license if document.license else None
        return document, license_name


def _abstract_sections(title: str, abstract: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    if title:
        sections.append(("TITLE", title))
    if abstract:
        sections.append(("ABSTRACT", abstract[:_MAX_ABSTRACT_CHARS]))
    return sections


def _spans_for_sections(
    canonical_text: str, sections: list[tuple[str, str]]
) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    offset = 0
    for path, text in sections:
        start = offset
        offset = start + len(text) + 2  # "\n\n" 连接，与 canonical 组装一致
        spans.append((path, start, start + len(text)))
    return spans


class PubexCitationAdapter:
    """引文扩展端口：相关文献的 cited-by / references（经 pubex 客户端）。"""

    def __init__(self, citation_client: Any, loop: LoopRunner) -> None:
        self.client = citation_client
        self.loop = loop

    def fetch_citations(self, pmids: list[str]) -> dict[str, Any]:
        return self.loop.run(self.client.fetch_citation_data(list(pmids)))
