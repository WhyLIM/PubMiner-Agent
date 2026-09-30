"""Embedding 服务与预筛测试（离线，mock provider）。"""
import httpx
import pytest

from pubminer.application.ports import LLMError
from pubminer.integrations.llm.providers.embedding import EmbeddingProvider
from pubminer.workflows.embedding_service import EmbeddingService, cosine_similarity


class TestCosineSimilarity:
    def test_identical(self):
        assert cosine_similarity([1, 0], [1, 0]) == 1.0

    def test_orthogonal(self):
        assert cosine_similarity([1, 0], [0, 1]) == 0.0

    def test_zero_vector(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0


class TestZhipuEmbeddingProvider:
    def test_embed_parses_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            import json
            data = json.loads(request.content)
            assert data["model"] == "embedding-3"
            assert data["input"] == ["hello", "world"]
            return httpx.Response(200, json={
                "data": [
                    {"embedding": [0.1, 0.2], "index": 0},
                    {"embedding": [0.3, 0.4], "index": 1},
                ],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            })

        transport = httpx.MockTransport(handler)
        provider = EmbeddingProvider("k", "embedding-3", base_url="https://x/v4", transport=transport)
        vectors = provider.embed(["hello", "world"])
        assert len(vectors) == 2
        assert vectors[0] == [0.1, 0.2]

    def test_requires_key(self):
        with pytest.raises(LLMError, match="API key"):
            EmbeddingProvider("", "m")


class TestEmbeddingService:
    @staticmethod
    def _service(vectors: dict, threshold=0.3):
        return EmbeddingService(lambda texts: [vectors[t] for t in texts], threshold=threshold)

    def test_prefilter_passes_relevant(self):
        vectors = {"cancer prognosis": [1.0, 0.0], "unrelated recipe": [0.0, 1.0]}
        svc = self._service(vectors)
        profile = vectors["cancer prognosis"]
        candidates = [
            {"pmid": "1", "abstract": "cancer prognosis"},
            {"pmid": "2", "abstract": "unrelated recipe"},
        ]
        passed, scores = svc.prefilter(profile, candidates)
        assert len(passed) == 1 and passed[0]["pmid"] == "1"

    def test_cache_hit(self):
        vectors = {"a": [1.0], "b": [0.0]}
        svc = self._service(vectors)
        svc.embed_texts(["a", "a"])
        assert len(svc._cache) == 1
