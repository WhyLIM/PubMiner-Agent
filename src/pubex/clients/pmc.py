"""PMC Open Access 全文客户端（BioC API）。

迁移自 PubMiner-webui `pubminer/downloader/pmc_bioc.py`；输出改为 typed
DocumentVersion（带稳定 passage offset 与 LicenseRecord）。许可未知时
`allows_redistribution=None`——不得默认允许再分发。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from pubex.clients.retry import http_error_from_status, retry_async
from pubex.models.document import DocumentVersion, LicenseRecord
from pubex.parsers.bioc import BiocSectionParser

logger = logging.getLogger("pubex.pmc")


class PMCFulltextClient:
    """NCBI BioC API（PMC OA Subset）客户端。

    只访问 PMC Open Access Subset 端点；响应 HTML 表示不在 OA Subset 内，返回 None。
    """

    BASE_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi"

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        cache_dir: str | Path | None = None,
        use_cache: bool = True,
    ) -> None:
        self.timeout_seconds = timeout
        self.max_retries = max_retries
        self.parser = BiocSectionParser()
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.use_cache and self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ cache

    def _cache_path(self, pmcid: str) -> Path | None:
        if self.cache_dir is None:
            return None
        normalized = self._normalize_pmcid(pmcid)
        return self.cache_dir / f"{normalized}.json"

    def _load_cache(self, pmcid: str, pmid: str) -> DocumentVersion | None:
        path = self._cache_path(pmcid)
        if not self.use_cache or path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            document = DocumentVersion.model_validate(payload["document"])
            if document.pmid and pmid and document.pmid != pmid:
                logger.warning("cache pmid mismatch for %s", pmcid)
            return document
        except Exception as exc:
            logger.warning("failed to read cache for %s: %s", pmcid, exc)
            return None

    def _save_cache(self, document: DocumentVersion) -> None:
        path = self._cache_path(document.pmcid or "")
        if not self.use_cache or path is None:
            return
        payload = {
            "document": document.model_dump(mode="json", exclude={"raw_bioc"}),
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------ fetch

    @staticmethod
    def _normalize_pmcid(pmcid: str) -> str:
        pmcid = pmcid.strip().upper()
        return pmcid if pmcid.startswith("PMC") else f"PMC{pmcid}"

    async def fetch_bioc(self, session: aiohttp.ClientSession, pmcid: str) -> dict[str, Any] | None:
        """拉取 BioC JSON；不在 OA Subset 时返回 None；错误走 typed retry。"""
        normalized = self._normalize_pmcid(pmcid)
        url = f"{self.BASE_URL}/BioC_json/{normalized}/unicode"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        async def attempt() -> dict[str, Any] | None:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "html" in content_type:
                        logger.debug("%s not in PMC OA Subset", normalized)
                        return None
                    return await response.json(content_type=None)
                if response.status == 404:
                    return None
                if response.status == 429:
                    retry_after = float(response.headers.get("Retry-After", 5))
                    logger.warning("rate limited by PMC BioC; waiting %.0fs", retry_after)
                    await asyncio.sleep(retry_after)
                    raise http_error_from_status(429)
                raise http_error_from_status(int(response.status), f"BioC API error for {normalized}")

        return await retry_async(attempt, max_retries=self.max_retries, base_wait=1.0)

    # ------------------------------------------------------------ document

    async def get_document_with_status(
        self,
        session: aiohttp.ClientSession,
        pmcid: str,
        pmid: str = "",
        *,
        source: str = "pmc-oa",
    ) -> tuple[DocumentVersion | None, dict[str, Any]]:
        """获取全文并解析为 DocumentVersion；返回 (document|None, status)。"""
        normalized = self._normalize_pmcid(pmcid)
        status: dict[str, Any] = {
            "pmcid": normalized,
            "pmid": pmid,
            "status": "failed",
            "reason": "unknown",
            "message": "",
            "cached": False,
        }

        cached = self._load_cache(normalized, pmid)
        if cached is not None:
            status.update(status="success", reason="cache_hit", message="loaded from local cache", cached=True)
            return cached, status

        try:
            bioc_data = await self.fetch_bioc(session, normalized)
        except Exception as exc:
            status.update(reason="request_failed", message=str(exc))
            return None, status

        if not bioc_data:
            status.update(reason="not_available", message="PMCID not available in PMC OA BioC response")
            return None, status

        license_record = LicenseRecord(
            source=source,
            license=None,  # BioC API 不返回许可；保持未知，不猜测
            retrieval_method="bioc-api",
            url=f"{self.BASE_URL}/BioC_json/{normalized}/unicode",
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            allows_redistribution=None,
        )
        try:
            document = self.parser.build_document_version(
                bioc_data,
                pmid=pmid or None,
                pmcid=normalized,
                license_record=license_record,
            )
        except Exception as exc:
            status.update(reason="parse_error", message=str(exc))
            return None, status

        if not document.canonical_text:
            status.update(reason="empty_content", message="no usable body text after filtering")
            return None, status

        self._save_cache(document)
        status.update(status="success", reason="structured_sections", message="downloaded and parsed")
        return document, status

    async def batch_download(
        self,
        pmcids: list[str],
        pmids: list[str] | None = None,
        concurrency: int = 5,
    ) -> list[DocumentVersion]:
        """并发批量下载，返回成功的文档。"""
        semaphore = asyncio.Semaphore(concurrency)
        pmid_map = dict(zip(pmcids, pmids or []))

        async with aiohttp.ClientSession() as session:

            async def download(pmcid: str) -> DocumentVersion | None:
                async with semaphore:
                    document, _ = await self.get_document_with_status(
                        session, pmcid, pmid_map.get(pmcid, "")
                    )
                    return document

            results = await asyncio.gather(*(download(p) for p in pmcids))

        documents = [doc for doc in results if doc is not None]
        logger.info("downloaded %d/%d full-text documents", len(documents), len(pmcids))
        return documents
