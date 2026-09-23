"""集成适配器测试（全部离线）：OpenAI 兼容 provider、LLM 端口、resolver 解析、
pubex→domain 水合转换、环境装配。

真实网络路径（NCBI/GLM）由 env 装配在生产使用，测试通过注入与 Mock 隔离。
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from pubminer.domain.documents import Document, DocumentIdentifier
from pubminer.workflows.ports import HydratedDocument, SearchIntent

REPO_ROOT = Path(__file__).resolve().parents[2]

SPAN_TEXT = "High KRAS expression was associated with poor overall survival (HR 2.1, 95% CI 1.4-3.2)."
CANONICAL = (
    "METHODS BODY ABOUT COHORTS. " + SPAN_TEXT + " DISCUSSION FOLLOWS."
)


class TestOpenAICompatibleProvider:
    def _provider(self, handler):
        from pubminer.integrations.llm.providers.openai_compat import OpenAICompatibleProvider

        transport = httpx.MockTransport(handler)
        return OpenAICompatibleProvider(
            "key-123", "glm-4-flash", base_url="https://llm.example/v4", transport=transport
        )

    def test_complete_parses_usage(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "glm-4-flash"
            assert request.headers["Authorization"] == "Bearer key-123"
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            })

        provider = self._provider(handler)
        text, usage = provider.complete("sys", "usr", temperature=0.1, max_tokens=64)
        assert text == "hello"
        assert usage.prompt_tokens == 11 and usage.completion_tokens == 7

    def test_http_error_raises_typed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized")

        from pubminer.application.ports import LLMError

        provider = self._provider(handler)
        with pytest.raises(LLMError, match="401"):
            provider.complete("s", "u", temperature=0, max_tokens=8)

    def test_requires_key(self):
        from pubminer.application.ports import LLMError
        from pubminer.integrations.llm.providers.openai_compat import OpenAICompatibleProvider

        with pytest.raises(LLMError, match="API key"):
            OpenAICompatibleProvider("", "m")


def _gateway_returning(payload: dict):
    from pubminer.integrations.llm import FakeLLMProvider, LLMGateway

    return LLMGateway(
        FakeLLMProvider(responder=lambda s, u, t: (json.dumps(payload), 10, 10))
    )


def _prompt_registry():
    from pubminer.integrations.llm import PromptRegistry

    return PromptRegistry(REPO_ROOT / "prompts")


def _hydrated() -> HydratedDocument:
    document = Document(
        identifiers=[DocumentIdentifier(kind="pmid", value="33145284")],
        title="KRAS study",
        abstract="Cohort study abstract.",
    )
    version = {
        "id": str(uuid4()),
        "document_id": str(document.id),
        "canonical_text": CANONICAL,
    }
    return HydratedDocument(
        document=document,
        version=version,
        section_spans=[("METHODS", 0, 28), ("RESULTS", 28, 28 + len(SPAN_TEXT))],
        fulltext_available=True,
    )


class TestLlmPorts:
    def test_screen_maps_label_and_document(self):
        from pubminer.integrations.adapters import LlmScreenPort

        port = LlmScreenPort(
            _gateway_returning({"label": "RELEVANT", "confidence": 0.9,
                                "reasons": ["PDAC", "survival"], "study_type": "cohort",
                                "needs_fulltext": False}),
            _prompt_registry(),
        )
        document = _hydrated().document
        decision = port.screen(document, criteria="PDAC prognostic")
        assert decision.document_id == document.id
        assert decision.label.value == "RELEVANT"
        assert decision.reasons == ["PDAC", "survival"]

    def test_extract_locates_verbatim_span_with_offsets(self):
        from pubminer.integrations.adapters import LlmExtractPort

        hydrated = _hydrated()
        port = LlmExtractPort(
            _gateway_returning({"items": [{
                "biomarker_mention": "KRAS",
                "disease_mention": "PDAC",
                "role": "prognostic",
                "direction": "HIGH",
                "outcome": "overall_survival",
                "statistics": {"effect_measure": "HR", "effect_value": "2.1"},
                "study_design": "retrospective_cohort",
                "evidence_span": SPAN_TEXT,
            }]}),
            _prompt_registry(),
        )
        results = port.extract(hydrated)
        assert len(results) == 1
        span = results[0].evidence_span
        assert span.document_version_id == UUID(hydrated.version["id"])
        assert hydrated.version["canonical_text"][span.start_char : span.end_char] == SPAN_TEXT
        assert span.section_path == "RESULTS"
        assert results[0].statistics.effect_value == "2.1"

    def test_extract_drops_non_verbatim_span(self):
        from pubminer.integrations.adapters import LlmExtractPort

        port = LlmExtractPort(
            _gateway_returning({"items": [{
                "biomarker_mention": "KRAS", "disease_mention": "PDAC", "role": "prognostic",
                "evidence_span": "KRAS expression predicts death (made up HR 9.9)",
            }]}),
            _prompt_registry(),
        )
        assert port.extract(_hydrated()) == []

    def test_verify_maps_polarity(self):
        from pubminer.domain.evidence import AnalysisType
        from pubminer.integrations.adapters import LlmExtractPort, LlmVerifyPort

        evidence = LlmExtractPort(
            _gateway_returning({"items": [{
                "biomarker_mention": "KRAS", "disease_mention": "PDAC", "role": "prognostic",
                "evidence_span": SPAN_TEXT,
            }]}),
            _prompt_registry(),
        ).extract(_hydrated())[0]

        port = LlmVerifyPort(
            _gateway_returning({
                "polarity": "SUPPORT", "entity_correct": True, "disease_correct": True,
                "endpoint_correct": True, "statistically_significant": True,
                "analysis_type": "multivariate", "independent_validation": False,
                "reasons": ["HR reported"], "needs_human_review": False,
            }),
            _prompt_registry(),
        )
        result = port.verify("SIG", evidence)
        assert result.polarity.value == "SUPPORT"
        assert result.analysis_type == AnalysisType.MULTIVARIATE


class TestGeneResolverParsing:
    def test_parse_esearch_ids(self):
        from pubminer.integrations.adapters.resolver import parse_esearch_ids

        assert parse_esearch_ids({"IdList": ["3845", "123"]}) == ["3845", "123"]
        assert parse_esearch_ids({}) == []

    def test_resolve_flags_ambiguity_without_network(self, monkeypatch):
        from types import SimpleNamespace

        from pubminer.integrations.adapters.resolver import EntrezGeneResolver
        from pubminer.integrations.loop_runner import LoopRunner

        loop = LoopRunner()

        class FakeEntrez:
            @staticmethod
            def esearch(**kwargs):
                assert "[Gene Name]" in kwargs["term"]
                return SimpleNamespace(close=lambda: None)

            @staticmethod
            def read(handle):
                return {"IdList": ["3845", "9999"]}

        resolver = EntrezGeneResolver.__new__(EntrezGeneResolver)
        resolver.loop = loop
        resolver.retmax = 3
        resolver._entrez = FakeEntrez

        candidates, needs_review = resolver.resolve("KRAS", "GENE")
        assert [c.identifier for c in candidates] == ["NCBIGene:3845", "NCBIGene:9999"]
        assert needs_review is True
        loop.close()

    def test_non_gene_type_unsupported(self):
        from pubminer.integrations.adapters.resolver import EntrezGeneResolver
        from pubminer.integrations.loop_runner import LoopRunner

        resolver = EntrezGeneResolver.__new__(EntrezGeneResolver)
        resolver.loop = LoopRunner()
        candidates, needs_review = resolver.resolve("PDAC", "DISEASE")
        assert candidates == [] and needs_review is True


class TestHydrateConversion:
    def test_abstract_only_fallback(self, monkeypatch):
        from types import SimpleNamespace

        from pubminer.integrations.adapters.pubmed import PubexHydrateAdapter
        from pubminer.integrations.loop_runner import LoopRunner

        record = SimpleNamespace(
            pmid="33145284", pmcid=None, doi="10.1/x", title="T", journal="J",
            year=2021, authors=["A B"], abstract="ABSTRACT BODY",
        )
        async def fetch_batch(pmids, batch_size=1):
            return [record]

        metadata_client = SimpleNamespace(fetch_batch=fetch_batch)

        adapter = PubexHydrateAdapter(metadata_client, None, LoopRunner())
        hydrated = adapter.hydrate("33145284")

        assert hydrated is not None and hydrated.fulltext_available is False
        assert hydrated.document.abstract == "ABSTRACT BODY"
        kinds = {i.kind: i.value for i in hydrated.document.identifiers}
        assert kinds["pmid"] == "33145284" and kinds["doi"] == "10.1/x"
        assert hydrated.version.canonical_text.startswith("T\n\nABSTRACT BODY")
        # spans 与 canonical 一致
        for path, start, end in hydrated.section_spans:
            assert hydrated.version.canonical_text[start:end]

    def test_pmc_fulltext_maps_license_and_spans(self):
        from types import SimpleNamespace

        from pubminer.integrations.adapters.pubmed import PubexHydrateAdapter
        from pubminer.integrations.loop_runner import LoopRunner
        from pubex.models import DocumentVersion as PubexDocumentVersion  # noqa: F401 — 确认 pubex SDK 可用

        record = SimpleNamespace(
            pmid="33145284", pmcid="PMC7756730", doi=None, title="T",
            journal="J", year=2021, authors=[], abstract="abstract",
        )
        async def fetch_batch(pmids, batch_size=1):
            return [record]

        metadata_client = SimpleNamespace(fetch_batch=fetch_batch)

        pubex_passage = SimpleNamespace(section_path="RESULTS", start_char=0, end_char=11)
        pubex_version = SimpleNamespace(canonical_text="RESULT TEXT", passages=[pubex_passage],
                                         license=SimpleNamespace(license="cc-by"))
        pmc_client = SimpleNamespace()

        async def fake_fetch(session, pmcid, pmid):
            return pubex_version, {"reason": "structured_sections"}

        pmc_client.get_document_with_status = fake_fetch

        adapter = PubexHydrateAdapter(metadata_client, pmc_client, LoopRunner())
        hydrated = adapter.hydrate("33145284")

        assert hydrated.fulltext_available is True
        assert hydrated.version.canonical_text == "RESULT TEXT"
        assert hydrated.version.license == "cc-by"
        assert hydrated.section_spans == [("RESULTS", 0, 11)]


class TestEnvAssembly:
    def test_missing_env_disables_ports_with_notes(self, monkeypatch):
        import os

        from pubminer.api.deps import build_container_from_env

        env = {k: v for k, v in os.environ.items()
               if k not in ("PUBMED_EMAIL", "PUBMINER_LLM_API_KEY")}
        container, notes = build_container_from_env(env)
        assert container.workflow_ports is None
        assert any("PUBMED_EMAIL" in n for n in notes)

    def test_full_env_wires_real_ports(self, monkeypatch, tmp_path):
        from pubminer.api.deps import build_container_from_env

        env = {
            "PUBMINER_DB_URL": f"sqlite:///{(tmp_path / 'env.db').as_posix()}",
            "PUBMED_EMAIL": "test@example.com",
            "PUBMINER_LLM_API_KEY": "k" * 8,
            "PUBMINER_LLM_BASE_URL": "https://llm.example/v4",
            "PUBMINER_LLM_MODEL": "glm-4-flash",
        }
        container, notes = build_container_from_env(env)
        assert container.workflow_ports is not None
        ports = container.workflow_ports
        for name in ("search", "hydrate", "screen", "extract", "normalize", "verify"):
            assert getattr(ports, name) is not None, name
        assert any("real ports wired" in n for n in notes)
