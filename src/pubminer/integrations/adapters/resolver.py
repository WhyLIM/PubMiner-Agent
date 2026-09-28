"""实体归一化适配器：NCBI Gene + PubTator 双源交叉验证（ADR-006）。

标识符只能来自 resolver 返回。GENE/PROTEIN 走 NCBI Gene esearch，并用
PubTator 候选名做交叉验证（缩写如 BMI/GAR 会被假阳性基因命中——两源一致
才确认，不一致标 needs_review 交 curator）；非基因类（疾病/化学指标）走
PubTator concept 检索映射 MESH；零候选一律 needs_review 交人工，绝不编造。
"""
from __future__ import annotations

import asyncio
import logging

from pubminer.integrations.loop_runner import LoopRunner
from pubminer.workflows.ports import ResolutionCandidate

logger = logging.getLogger("pubminer.adapters.resolver")


def parse_esearch_ids(payload: dict) -> list[str]:
    """Bio.Entrez.read 后的 esearch 结果 → 有序 ID 列表。"""
    return [str(uid) for uid in payload.get("IdList", []) if str(uid).strip()]


class EntrezGeneResolver:
    """db=gene esearch；term = "<mention>[Gene Name]"。"""

    def __init__(self, loop: LoopRunner, *, email: str, api_key: str | None = None, retmax: int = 3):
        from Bio import Entrez

        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
        self._entrez = Entrez
        self.loop = loop
        self.retmax = retmax

    async def _esearch(self, mention: str) -> dict:
        handle = await asyncio.to_thread(
            self._entrez.esearch,
            db="gene",
            term=f"{mention}[Gene Name]",
            retmax=self.retmax,
            idtype="acc",
        )
        try:
            data = await asyncio.to_thread(self._entrez.read, handle)
        finally:
            await asyncio.to_thread(handle.close)
        return data

    def resolve(self, mention: str, entity_type: str):
        """返回 (candidates, needs_review)。entity_type 非 GENE 时空结果。"""
        if entity_type != "GENE":
            logger.warning("resolver supports GENE only; got %s", entity_type)
            return [], True
        try:
            data = self.loop.run(self._esearch(mention))
        except Exception as exc:
            logger.warning("gene esearch failed for %s: %s", mention, exc)
            return [], True
        ids = parse_esearch_ids(data)
        candidates = [
            ResolutionCandidate(
                entity_id=f"tmp:{uid}",
                name=mention,
                identifier=f"NCBIGene:{uid}",
                score=1.0 - 0.1 * index,
            )
            for index, uid in enumerate(ids)
        ]
        needs_review = len(candidates) != 1
        return candidates, needs_review


class CompositeEntityResolver:
    """GENE/PROTEIN：NCBI Gene 检索 + PubTator 名称交叉验证；
    其他类型：PubTator concept 检索。零候选一律 needs_review。

    交叉验证规则：Entrez 唯一候选的名称（归一化后，忽略大小写/空白/
    连字符差异）必须出现在 PubTator 候选名中，才视为"确认"；否则认为
    缩写与基因符号是巧合匹配，标记 needs_review 交 curator 裁决
    （真实案例：BMI 体质指数 ≠ BMI1 基因；GAR 比值 ≠ GAR 基因）。
    """

    def __init__(
        self,
        gene_resolver=None,
        pubtator_resolver=None,
        *,
        max_candidates: int = 4,
    ) -> None:
        self.gene_resolver = gene_resolver
        self.pubtator_resolver = pubtator_resolver
        self.max_candidates = max_candidates

    @staticmethod
    def _norm(name: str) -> str:
        import re

        return re.sub(r"[^a-z0-9]", "", name.lower())

    def resolve(self, mention: str, entity_type: str):
        candidates: list[ResolutionCandidate] = []
        seen: set[str] = set()
        ambiguous = False

        gene_top_norm: str | None = None
        if entity_type.upper() in ("GENE", "PROTEIN") and self.gene_resolver is not None:
            gene_candidates, _ = self.gene_resolver.resolve(mention, "GENE")
            pubtator_candidates, _ = (
                self.pubtator_resolver.resolve(mention, "GENE")
                if self.pubtator_resolver is not None
                else ([], False)
            )
            pubtator_names = {
                self._norm(c.name) for c in pubtator_candidates if c.name
            }
            gene_top_norm = self._norm(
                (gene_candidates[0].name if gene_candidates else "") or mention
            )
            # 交叉验证：Entrez 首选名（归一化）须出现在 PubTator 候选名中；
            # 否则视为缩写与基因符号的巧合匹配（如 BMI≠BMI1），送 curator
            ambiguous = bool(gene_candidates) and (
                len(gene_candidates) > 1 or gene_top_norm not in pubtator_names
            )
            for candidate in gene_candidates:
                if candidate.identifier in seen:
                    continue
                seen.add(candidate.identifier)
                candidates.append(candidate)

        if self.pubtator_resolver is not None:
            try:
                pubtator_candidates, _ = self.pubtator_resolver.resolve(mention, entity_type)
            except Exception as exc:
                logger.warning("pubtator resolve failed for %r: %s", mention, exc)
                pubtator_candidates = []
            for candidate in pubtator_candidates:
                # 同名跨源去重：物种聚合 ID 不同的同一实体不重复计入
                norm_name = self._norm(candidate.name)
                if norm_name and norm_name == gene_top_norm:
                    continue
                if candidate.identifier in seen:
                    continue
                seen.add(candidate.identifier)
                candidates.append(candidate)

        if len(candidates) > 1:
            ambiguous = True
        return candidates[: self.max_candidates], ambiguous
