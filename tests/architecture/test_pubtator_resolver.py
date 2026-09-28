"""PubTator 适配器与复合解析器测试（离线 MockTransport）。"""
from __future__ import annotations

import httpx

from pubminer.integrations.adapters.pubtator import PubTatorEntityResolver
from pubminer.integrations.adapters.resolver import CompositeEntityResolver
from pubminer.integrations.loop_runner import LoopRunner
from pubminer.workflows.ports import ResolutionCandidate


def _resolver_with(handler, max_candidates=3):
    transport = httpx.MockTransport(handler)
    return PubTatorEntityResolver(
        LoopRunner(), base_url="https://pubtator.example", transport=transport,
        max_candidates=max_candidates,
    )


class TestPubTatorResolver:
    def test_gene_candidates_map_ncbigene_namespace(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "concept=gene" in str(request.url)
            return httpx.Response(200, json=[
                {"_id": "@GENE_KRAS", "db": "ncbi_gene", "db_id": "24525", "name": "Kras"},
                {"_id": "@GENE_HRAS", "db": "ncbi_gene", "db_id": "3265", "name": "HRAS"},
            ])

        resolver = _resolver_with(handler)
        candidates, needs_review = resolver.resolve("KRAS", "GENE")
        assert [c.identifier for c in candidates] == ["NCBIGene:24525", "NCBIGene:3265"]
        assert needs_review is True  # 两个候选 → 歧义

    def test_disease_maps_mesh(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "concept=disease" in str(request.url)
            return httpx.Response(200, json=[
                {"_id": "@DISEASE_Pancreatic_Neoplasms", "db": "ncbi_mesh",
                 "db_id": "D010190", "name": "Pancreatic Neoplasms"},
            ])

        resolver = _resolver_with(handler)
        candidates, needs_review = resolver.resolve("pancreatic carcinoma", "DISEASE")
        assert candidates[0].identifier == "MESH:D010190"
        assert needs_review is False

    def test_single_candidate_is_not_ambiguous(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[
                {"_id": "@GENE_KRAS", "db": "ncbi_gene", "db_id": "24525", "name": "Kras"},
            ])

        resolver = _resolver_with(handler)
        _, needs_review = resolver.resolve("KRAS", "GENE")
        assert needs_review is False

    def test_zero_candidates_flags_review(self):
        resolver = _resolver_with(
            lambda request: httpx.Response(200, json=[]),
        )
        candidates, needs_review = resolver.resolve("unknown-marker", "GENE")
        assert candidates == [] and needs_review is True

    def test_network_failure_is_graceful(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        resolver = _resolver_with(handler)
        candidates, needs_review = resolver.resolve("KRAS", "GENE")
        assert candidates == [] and needs_review is True

    def test_candidates_capped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[
                {"_id": f"@GENE_G{i}", "db": "ncbi_gene", "db_id": str(i), "name": f"G{i}"}
                for i in range(10)
            ])

        resolver = _resolver_with(handler)
        candidates, _ = resolver.resolve("m", "GENE")
        assert len(candidates) == 3


class TestCompositeResolver:
    @staticmethod
    def _fake_resolver(candidates, needs_review):
        class _R:
            def resolve(self, mention, entity_type):
                return candidates, needs_review
        return _R()

    def test_gene_confirmed_when_pubtator_agrees(self):
        gene = self._fake_resolver([
            ResolutionCandidate(entity_id="t1", name="KRAS", identifier="NCBIGene:3845", score=1.0),
        ], False)
        pubtator = self._fake_resolver([
            ResolutionCandidate(entity_id="t2", name="Kras", identifier="NCBIGene:24525", score=0.9),
        ], False)

        composite = CompositeEntityResolver(gene_resolver=gene, pubtator_resolver=pubtator)
        candidates, needs_review = composite.resolve("KRAS", "GENE")
        # 名称归一化后一致（大小写差异）→ 确认，非歧义
        assert candidates[0].identifier == "NCBIGene:3845"
        assert needs_review is False

    def test_abbreviation_disagreement_flags_review(self):
        gene = self._fake_resolver([
            ResolutionCandidate(entity_id="t1", name="BMI", identifier="NCBIGene:1956", score=1.0),
        ], False)
        pubtator = self._fake_resolver([
            ResolutionCandidate(entity_id="t2", name="BMI1", identifier="NCBIGene:12151", score=0.9),
            ResolutionCandidate(entity_id="t3", name="FTO", identifier="NCBIGene:79068", score=0.6),
        ], True)

        composite = CompositeEntityResolver(gene_resolver=gene, pubtator_resolver=pubtator)
        candidates, needs_review = composite.resolve("BMI", "GENE")
        # Entrez 的 "BMI" 在 PubTator 候选名（bmi1/fto/pcsk1）中找不到 → 歧义送审
        assert needs_review is True

    def test_falls_back_to_pubtator_when_gene_finds_nothing(self):
        gene = self._fake_resolver([], True)
        pubtator = self._fake_resolver([
            ResolutionCandidate(entity_id="t", name="CA 19-9", identifier="MESH:D000067631", score=0.9),
        ], False)

        composite = CompositeEntityResolver(gene_resolver=gene, pubtator_resolver=pubtator)
        candidates, needs_review = composite.resolve("CA 19-9", "CHEMICAL")
        assert candidates[0].identifier == "MESH:D000067631"
        assert needs_review is False
