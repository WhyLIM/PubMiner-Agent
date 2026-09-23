"""MiningWorkflow 端口：竖切各步骤的外部能力契约。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pubminer.domain.documents import Document, DocumentVersion
from pubminer.domain.evidence import BiomarkerEvidence, VerificationResult
from pubminer.domain.screening import ScreeningDecision


@dataclass
class SearchIntent:
    """一次检索意图（来自 plan / query planner）。"""

    name: str
    query: str
    max_results: int = 50
    date_range: tuple[str, str] | None = None


@dataclass
class HydratedDocument:
    """检索命中文档的水合结果：元数据 + 可得正文（abstract 降级允许）。"""

    document: Document
    version: DocumentVersion
    section_spans: list[tuple[str, int, int]] = field(default_factory=list)
    fulltext_available: bool = False


@dataclass
class ResolutionCandidate:
    entity_id: str  # 已入库 entity 的 id（字符串形式）或临时标识
    name: str
    identifier: str | None = None  # NAMESPACE:VALUE；只能来自 resolver
    score: float = 0.0


class SearchPort(Protocol):
    def search(self, intent: SearchIntent) -> list[dict]: ...


class HydratePort(Protocol):
    def hydrate(self, pmid: str) -> HydratedDocument | None: ...


class ScreenPort(Protocol):
    def screen(self, document: Document, criteria: str | None = None) -> ScreeningDecision: ...


class ExtractPort(Protocol):
    def extract(self, hydrated: HydratedDocument) -> list[BiomarkerEvidence]: ...


class NormalizePort(Protocol):
    def resolve(
        self, mention_text: str, entity_type: str
    ) -> tuple[list[ResolutionCandidate], bool]:  # (candidates, needs_review)
        ...


class VerifyPort(Protocol):
    def verify(self, claim_signature: str, evidence: BiomarkerEvidence) -> VerificationResult: ...


class MiningPorts(Protocol):
    search: SearchPort
    hydrate: HydratePort
    screen: ScreenPort
    extract: ExtractPort
    normalize: NormalizePort
    verify: VerifyPort
