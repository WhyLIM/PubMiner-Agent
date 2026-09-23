"""PR-004 contract test：retry 分类与客户端组装（离线，网络层用 fake）。"""
import asyncio

import pytest

from pubex.clients.retry import http_error_from_status, retry_async
from pubex.errors import (
    PubExHTTPError,
    PubExMaxRetriesExceeded,
    PubExNetworkError,
    PubExRateLimitError,
    PubExTLSVerificationError,
)
from pubex.models.search import CitationEntry, SearchResultPage


class TestRetryAsync:
    async def test_success_first_try(self):
        async def op():
            return "ok"

        assert await retry_async(op, max_retries=3, base_wait=0, sleep=lambda *_: asyncio.sleep(0)) == "ok"

    async def test_network_error_retries_then_succeeds(self):
        state = {"n": 0}

        async def op():
            state["n"] += 1
            if state["n"] < 3:
                raise ConnectionResetError("connection reset")
            return "recovered"

        result = await retry_async(op, max_retries=3, base_wait=0, sleep=lambda *_: asyncio.sleep(0))
        assert result == "recovered" and state["n"] == 3

    async def test_tls_failure_fails_fast(self):
        calls = {"n": 0}

        async def op():
            calls["n"] += 1
            raise PubExTLSVerificationError("certificate verify failed")

        with pytest.raises(PubExTLSVerificationError):
            await retry_async(op, max_retries=5, base_wait=0, sleep=lambda *_: asyncio.sleep(0))
        assert calls["n"] == 1

    async def test_exhaustion_raises_max_retries(self):
        async def op():
            raise TimeoutError("timed out")

        with pytest.raises(PubExMaxRetriesExceeded) as exc_info:
            await retry_async(op, max_retries=2, base_wait=0, sleep=lambda *_: asyncio.sleep(0))
        assert isinstance(exc_info.value.last_error, PubExNetworkError)

    async def test_http_error_passthrough(self):
        async def op():
            raise PubExHTTPError(404, "not found", retryable=False)

        with pytest.raises(PubExHTTPError):
            await retry_async(op, max_retries=3, base_wait=0, sleep=lambda *_: asyncio.sleep(0))


class TestStatusClassification:
    def test_429_is_rate_limit(self):
        assert isinstance(http_error_from_status(429), PubExRateLimitError)

    def test_5xx_retryable(self):
        assert http_error_from_status(503).retryable is True

    def test_4xx_not_retryable(self):
        assert http_error_from_status(403).retryable is False


class TestClientAssembly:
    def test_facade_shares_rate_limit_state(self):
        from pubex.clients.pubmed import AsyncPubMedClient

        client = AsyncPubMedClient(email="test@example.com")
        assert client.rate_limit == 0.34
        client2 = AsyncPubMedClient(email="test@example.com", api_key="k" * 36)
        assert client2.rate_limit == 0.1

    def test_typed_result_models(self):
        page = SearchResultPage(query="test", pmids=["123"], total_count=5, returned_count=1)
        assert page.returned_count == 1 and page.webenv is None
        entry = CitationEntry(pmid="123", cited_by=["456"])
        assert entry.cited_count == 1 and entry.references_count == 0
