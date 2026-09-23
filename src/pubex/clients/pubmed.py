"""PubMed 检索 / 元数据 / 引用客户端（Biopython Entrez + asyncio.to_thread）。

迁移自 PubMiner-webui `pubminer/fetcher/pubmed_client.py`；职责按设计文档拆分：
PubMedSearchClient / PubMedMetadataClient / PubMedCitationClient + 组合门面
AsyncPubMedClient（兼容原方法面）。全部解析逻辑在 pubmed_parse 纯函数中，可离线测试。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from Bio import Entrez

from pubex.clients.pubmed_parse import parse_pubmed_record
from pubex.clients.retry import http_error_from_status, retry_async
from pubex.errors import PubExError
from pubex.models.pubmed_record import PubMedRecord
from pubex.models.search import CitationEntry, SearchResultPage

logger = logging.getLogger("pubex.pubmed")


def _read_handle(handle: Any) -> Any:
    try:
        return Entrez.read(handle)
    finally:
        handle.close()


class _EntrezMixin:
    """共享：Entrez 账号配置、限流、HTTP 错误分类。"""

    def __init__(
        self,
        email: str,
        api_key: str | None = None,
        tool_name: str = "PubEx",
        rate_limit: float = 0.34,
    ) -> None:
        Entrez.email = email
        Entrez.tool = tool_name
        self.api_key = api_key
        if api_key:
            Entrez.api_key = api_key
        self.rate_limit_without_key = rate_limit
        self.rate_limit = 0.1 if api_key else rate_limit
        self._last_request_time = 0.0
        self._request_lock = asyncio.Lock()

    async def _call(self, func, *args, **kwargs) -> Any:
        """限流 + 线程池执行 Entrez 调用；HTTPError 归类为 typed PubEx 错误。"""
        async with self._request_lock:
            loop = asyncio.get_event_loop()
            elapsed = loop.time() - self._last_request_time
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)
            try:
                result = await asyncio.to_thread(func, *args, **kwargs)
                self._last_request_time = loop.time()
                return result
            except PubExError:
                raise
            except Exception as exc:  # HTTPError 等
                code = getattr(exc, "code", None)
                if code is not None:
                    raise http_error_from_status(int(code), str(exc)) from exc
                raise

    async def read(self, func, *args, **kwargs) -> Any:
        """限流调用 + Entrez.read，包 retry_async（证书失败不重试）。"""
        return await retry_async(lambda: self._call_and_read(func, *args, **kwargs))

    async def _call_and_read(self, func, *args, **kwargs) -> Any:
        handle = await self._call(func, *args, **kwargs)
        return await asyncio.to_thread(_read_handle, handle)


class PubMedSearchClient(_EntrezMixin):
    """esearch：PubMed 检索（支持 History）。"""

    async def search(
        self,
        query: str,
        max_results: int = 100,
        offset: int = 0,
        date_range: tuple[str, str] | None = None,
        use_history: bool = True,
    ) -> SearchResultPage:
        search_args: dict[str, Any] = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retstart": offset,
            "usehistory": "y" if use_history else "n",
        }
        if date_range:
            search_args["mindate"] = date_range[0]
            search_args["maxdate"] = date_range[1]

        record = await self.read(Entrez.esearch, **search_args)
        pmids = [str(p) for p in record.get("IdList", [])]
        return SearchResultPage(
            query=query,
            pmids=pmids,
            total_count=int(record.get("Count", 0)),
            offset=offset,
            returned_count=len(pmids),
            webenv=record.get("WebEnv"),
            query_key=record.get("QueryKey"),
        )


class PubMedMetadataClient(_EntrezMixin):
    """efetch：PubMed XML 元数据批量获取。"""

    async def fetch_batch(
        self,
        pmids: list[str],
        *,
        batch_size: int = 200,
        retries_per_batch: int = 2,
    ) -> list[PubMedRecord]:
        records: list[PubMedRecord] = []
        for index in range(0, len(pmids), batch_size):
            batch = pmids[index : index + batch_size]
            raw_articles = await retry_async(
                lambda b=batch: self._fetch_raw_batch(b),
                max_retries=retries_per_batch,
                base_wait=0.5,
            )
            for raw in raw_articles:
                try:
                    records.append(parse_pubmed_record(raw))
                except Exception as exc:  # 单条脏数据不拖垮整批
                    logger.warning("skip unparsable PubMed record: %s", exc)
        return records

    async def _fetch_raw_batch(self, batch: list[str]) -> list[dict[str, Any]]:
        handle = await self._call(
            Entrez.efetch, db="pubmed", id=",".join(batch), rettype="xml", retmode="xml"
        )
        data = await asyncio.to_thread(_read_handle, handle)
        return data.get("PubmedArticle", [])


class PubMedCitationClient(_EntrezMixin):
    """elink：cited-by / references 引用关系。"""

    async def fetch_citations(self, pmids: list[str]) -> dict[str, CitationEntry]:
        entries = {pmid: CitationEntry(pmid=pmid) for pmid in pmids}
        if not pmids:
            return entries

        async def link_map(linkname: str) -> dict[str, list[str]]:
            record = await self.read(
                Entrez.elink,
                dbfrom="pubmed",
                db="pubmed",
                id=",".join(pmids),
                linkname=linkname,
                retmode="xml",
                cmd="neighbor",
            )
            result: dict[str, list[str]] = {}
            for i, record_entry in enumerate(record):
                pmid = pmids[i] if i < len(pmids) else None
                if not pmid:
                    continue
                ids: list[str] = []
                for linkset in record_entry.get("LinkSetDb", []):
                    if linkset.get("LinkName") != linkname:
                        continue
                    ids.extend(link["Id"] for link in linkset.get("Link", []) if link.get("Id"))
                result[pmid] = ids
            return result

        try:
            cited_map = await link_map("pubmed_pubmed_citedin")
        except Exception as exc:
            logger.warning("cited-by fetch failed: %s", exc)
            cited_map = {}
        try:
            refs_map = await link_map("pubmed_pubmed_refs")
        except Exception as exc:
            logger.warning("references fetch failed: %s", exc)
            refs_map = {}

        for pmid, entry in entries.items():
            entry.cited_by = cited_map.get(pmid, [])
            entry.references = refs_map.get(pmid, [])
        return entries


class AsyncPubMedClient(PubMedSearchClient, PubMedMetadataClient, PubMedCitationClient):
    """组合门面：与 webui 版 AsyncPubMedClient 方法面兼容。

    search() 现在返回 typed SearchResultPage；fetch_metadata 返回 list[PUBMED_RECORD]；
    fetch_citation_data 返回 dict[pmid, CitationEntry]。
    """

    async def fetch_metadata(
        self,
        pmids: list[str],
        batch_size: int = 200,
        include_citations: bool = False,
    ) -> list[PubMedRecord]:
        if not pmids:
            return []
        results = await self.fetch_batch(pmids, batch_size=batch_size)
        if include_citations and results:
            citations = await self.fetch_citations([r.pmid for r in results])
            for record in results:
                entry = citations.get(record.pmid)
                if entry:
                    record.cited_by = entry.cited_by
                    record.cited_count = entry.cited_count
                    record.references = entry.references
                    record.references_count = entry.references_count
        return results

    async def fetch_citation_data(self, pmids: list[str]) -> dict[str, CitationEntry]:
        return await self.fetch_citations(pmids)

    async def get_pmcid(self, pmid: str) -> str | None:
        record = await self.read(
            Entrez.elink, dbfrom="pubmed", db="pmc", id=pmid, linkname="pubmed_pmc"
        )
        for linkset in record:
            for linksetdb in linkset.get("LinkSetDb", []):
                for link in linksetdb.get("Link", []):
                    return f"PMC{link.get('Id', '')}"
        return None

    async def close(self) -> None:  # Entrez 无持久连接；保留方法面兼容
        return None
