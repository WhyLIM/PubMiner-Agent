"""PubTator 3 实体解析适配器。

覆盖非基因类 biomarker（疾病、化学/临床指标、蛋白）的归一化：
autocomplete 返回 `db`（ncbi_gene/ncbi_mesh/…）+ `db_id`，直接映射为
`NCBIGene:24525`、`MESH:D010190` 等正式标识符（ADR-006 合规）。

端点（官方）：https://www.ncbi.nlm.nih.gov/research/pubtator3-api
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from pubminer.integrations.loop_runner import LoopRunner
from pubminer.workflows.ports import ResolutionCandidate

logger = logging.getLogger("pubminer.adapters.pubtator")

AUTOCOMPLETE_PATH = "/entity/autocomplete/"

#: PubTator `db` 字段 → 我们命名空间
_DB_TO_NAMESPACE = {
    "ncbi_gene": "NCBIGene",
    "ncbi_mesh": "MESH",
    "ncbi_taxon": "NCBITaxon",
}

#: 解析目标类型 → PubTator concept 过滤值
_TYPE_TO_CONCEPT = {
    "GENE": "gene",
    "PROTEIN": "gene",
    "DISEASE": "disease",
    "CHEMICAL": "chemical",
    "CLINICAL_MARKER": "chemical",
    "METABOLITE": "chemical",
}


class PubTatorEntityResolver:
    """PubTator 3 autocomplete 实体解析。"""

    def __init__(
        self,
        loop: LoopRunner,
        *,
        base_url: str = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api",
        timeout: float = 20.0,
        max_candidates: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.loop = loop
        self.max_candidates = max_candidates
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    async def _autocomplete(self, mention: str, concept: str | None) -> list[dict[str, Any]]:
        params: dict[str, str] = {"query": mention}
        if concept:
            params["concept"] = concept
        response = await asyncio.to_thread(self._client.get, AUTOCOMPLETE_PATH, params=params)
        response.raise_for_status()
        return response.json()

    def resolve(self, mention: str, entity_type: str):
        """返回 (candidates, needs_review)；零候选时 ([], True)。"""
        concept = _TYPE_TO_CONCEPT.get(entity_type.upper(), "")
        try:
            payload = self.loop.run(self._autocomplete(mention, concept))
        except Exception as exc:
            logger.warning("pubtator autocomplete failed for %r: %s", mention, exc)
            return [], True
        candidates = self._candidates_from(payload)
        if not candidates and concept:
            # 概念过滤无命中时放开过滤再试一次
            try:
                payload = self.loop.run(self._autocomplete(mention, None))
            except Exception as exc:
                logger.warning("pubtator unfiltered retry failed for %r: %s", mention, exc)
                return [], True
            candidates = self._candidates_from(payload)
        needs_review = len(candidates) != 1
        return candidates, needs_review

    def _candidates_from(self, payload: list[dict[str, Any]]) -> list[ResolutionCandidate]:
        candidates: list[ResolutionCandidate] = []
        seen: set[str] = set()
        for index, entry in enumerate(payload or []):
            db = str(entry.get("db", ""))
            db_id = str(entry.get("db_id", "")).strip()
            pubtator_id = str(entry.get("_id", "")).strip()
            if db_id:
                namespace = _DB_TO_NAMESPACE.get(db, "PUBTATOR")
                identifier = f"{namespace}:{db_id}"
            elif pubtator_id:
                identifier = f"PUBTATOR:{pubtator_id}"
            else:
                continue
            if identifier in seen:
                continue
            seen.add(identifier)
            candidates.append(
                ResolutionCandidate(
                    entity_id=f"tmp:{pubtator_id or db_id}",
                    name=str(entry.get("name", "")) or pubtator_id,
                    identifier=identifier,
                    score=round(1.0 - 0.1 * index, 2),
                )
            )
            if len(candidates) >= self.max_candidates:
                break
        return candidates

