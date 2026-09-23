"""实体归一化适配器：NCBI Gene esearch 作为 GENE resolver（ADR-006）。

identifier 只能来自 resolver 返回；多候选时选最高优先但标记 needs_review，
零候选返回空（上层将拒绝造 ID，宁可中断不可编造）。
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
