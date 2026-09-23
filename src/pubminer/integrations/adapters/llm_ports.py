"""LLM 端口适配器：screening / extraction / verification（结构化输出）。

Grounding 规则：抽取返回的 evidence_span 必须是 canonical text 的逐字
子串；定位失败即丢弃该条抽取（禁止无 span claim），不模糊匹配。
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

from pubminer.application.ports import LLMPort, LLMRequest
from pubminer.domain.documents import Document, EvidenceSpan
from pubminer.domain.evidence import (
    BiomarkerEvidence,
    Population,
    Statistics,
    StudyDesign,
    VerificationResult,
)
from pubminer.domain.screening import ScreeningDecision, ScreeningLabel
from pubminer.workflows.ports import HydratedDocument

logger = logging.getLogger("pubminer.adapters.llm")

_MAX_CONTEXT_CHARS = 9000


class LlmScreenPort:
    """screening/v1 prompt：RELEVANT / IRRELEVANT / UNCERTAIN。"""

    def __init__(self, llm: LLMPort, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def screen(self, document: Document, criteria: str | None = None) -> ScreeningDecision:
        prompt = self.prompts.get("screening", "v1")
        article_text = "\n".join(
            part for part in (f"TITLE: {document.title}", f"ABSTRACT: {document.abstract}") if part
        )[:_MAX_CONTEXT_CHARS]
        from pydantic import BaseModel

        class _ScreenOut(BaseModel):
            label: ScreeningLabel
            confidence: float = 0.5
            reasons: list[str] = []
            study_type: str | None = None
            needs_fulltext: bool = False

        response = self.llm.structured_generate(
            LLMRequest(
                purpose="screening",
                prompt_version="screening@v1",
                system=prompt.system,
                user=prompt.render(
                    research_question=article_text,
                    criteria=criteria or "biomarker evidence for the stated disease and task",
                ),
                temperature=0.1,
                max_tokens=4096,
                metadata={"schema_version": "screening-v1"},
            ),
            _ScreenOut,
        )

        payload = _parse_json(response.text)
        return ScreeningDecision(
            document_id=document.id,
            label=ScreeningLabel(str(payload.get("label", "UNCERTAIN")).upper()),
            confidence=float(payload.get("confidence", 0.5)),
            reasons=[str(r) for r in payload.get("reasons", [])],
            study_type=payload.get("study_type"),
            needs_fulltext=bool(payload.get("needs_fulltext", False)),
        )


class LlmExtractPort:
    """extraction/biomarker/v1：多目标抽取 + verbatim span 定位。"""

    def __init__(self, llm: LLMPort, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def extract(self, hydrated: HydratedDocument) -> list[BiomarkerEvidence]:
        version = hydrated.version
        canonical = (
            version.get("canonical_text", "")
            if isinstance(version, dict)
            else version.canonical_text
        )
        version_id = (
            UUID(version["id"]) if isinstance(version, dict) else version.id
        )
        if not canonical:
            return []

        from pydantic import BaseModel

        class _Item(BaseModel):
            biomarker_mention: str
            disease_mention: str | None = None
            role: str
            direction: str | None = None
            outcome: str | None = None
            statistics: dict | None = None
            study_design: str | None = None
            evidence_span: str

        class _ExtractionOut(BaseModel):
            items: list[_Item] = []

        prompt = self.prompts.get("extraction/biomarker", "v1")
        response = self.llm.structured_generate(
            LLMRequest(
                purpose="extraction",
                prompt_version="extraction/biomarker@v1",
                system=prompt.system,
                user=prompt.render(passage=canonical[:_MAX_CONTEXT_CHARS]),
                temperature=0.0,
                max_tokens=8192,
                metadata={"schema_version": "biomarker-v1"},
            ),
            _ExtractionOut,
        )
        payload = _parse_json(response.text)

        results: list[BiomarkerEvidence] = []
        for raw in payload.get("items", []):
            located = locate_span(canonical, str(raw.get("evidence_span", "")).strip())
            if located is None:
                # grounding 失败：丢弃该条（宁可漏，不可造）
                logger.warning(
                    "dropped extraction for %r: evidence_span not found in canonical text",
                    raw.get("biomarker_mention"),
                )
                continue
            start, matched_text = located
            span_text = matched_text
            section = _section_at(hydrated.section_spans, start)
            study_design = raw.get("study_design") or "unknown"
            try:
                design = StudyDesign(study_design)
            except ValueError:
                design = StudyDesign.UNKNOWN
            statistics = (
                Statistics.model_validate(raw["statistics"])
                if isinstance(raw.get("statistics"), dict)
                else None
            )
            try:
                results.append(
                    BiomarkerEvidence(
                        biomarker_mention=str(raw["biomarker_mention"]),
                        disease_mention=raw.get("disease_mention") or "",
                        role=str(raw.get("role", "prognostic")),
                        direction=raw.get("direction"),
                        outcome=raw.get("outcome"),
                        population=Population(),
                        study_design=design,
                        statistics=statistics,
                        evidence_span=EvidenceSpan.from_text(
                            version_id, uuid4(), span_text, start, section
                        ),
                    )
                )
            except Exception as exc:  # 单条字段异常丢弃，不拖垮整篇
                logger.warning("dropped malformed extraction for %r: %s",
                               raw.get("biomarker_mention"), exc)
        return results


class LlmVerifyPort:
    """verification/v1：极性判定，confidence 不转真值。"""

    def __init__(self, llm: LLMPort, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def verify(self, claim_signature: str, evidence: BiomarkerEvidence) -> VerificationResult:
        prompt = self.prompts.get("verification", "v1")
        response = self.llm.structured_generate(
            LLMRequest(
                purpose="verification",
                prompt_version="verification@v1",
                system=prompt.system,
                user=prompt.render(
                    claim=claim_signature,
                    passage=evidence.evidence_span.text[:_MAX_CONTEXT_CHARS],
                ),
                temperature=0.0,
                max_tokens=4096,
                metadata={"schema_version": "verification-v1"},
            ),
            VerificationResult,
        )
        payload = _parse_json(response.text)
        from pubminer.domain.evidence import AnalysisType

        analysis = str(payload.get("analysis_type", "unknown"))
        try:
            analysis_type = AnalysisType(analysis)
        except ValueError:
            analysis_type = AnalysisType.UNKNOWN
        return VerificationResult(
            polarity=str(payload.get("polarity", "UNCERTAIN")).upper(),
            entity_correct=payload.get("entity_correct"),
            disease_correct=payload.get("disease_correct"),
            endpoint_correct=payload.get("endpoint_correct"),
            statistically_significant=payload.get("statistically_significant"),
            analysis_type=analysis_type,
            independent_validation=payload.get("independent_validation"),
            reasons=[str(r) for r in payload.get("reasons", [])],
            needs_human_review=bool(payload.get("needs_human_review", False)),
        )


_QUOTE_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
}


def _normalize_indexed(text: str) -> tuple[str, list[int]]:
    """引号/连字符归一 + 去空白 + 小写；mapping[i] = 归一化第 i 字符的原始下标。"""
    out: list[str] = []
    mapping: list[int] = []
    for index, ch in enumerate(text):
        ch = _QUOTE_MAP.get(ch, ch)
        if ch.isspace():
            continue
        out.append(ch.lower())
        mapping.append(index)
    return "".join(out), mapping


def locate_span(canonical: str, span_text: str) -> tuple[int, str] | None:
    """返回 (start, matched_text)；先精确匹配，失败再做格式归一化匹配。

    归一化只对齐引号/连字符/空白/大小写等排版差异——语义被改写的 span
    仍然定位失败并被丢弃（grounding 红线不变）。
    """
    if not span_text:
        return None
    exact = canonical.find(span_text)
    if exact >= 0:
        return exact, span_text
    norm_canonical, canonical_map = _normalize_indexed(canonical)
    norm_span, span_map = _normalize_indexed(span_text)
    if not norm_span:
        return None
    found = norm_canonical.find(norm_span)
    if found < 0:
        return None
    start = canonical_map[found]
    end = canonical_map[found + len(norm_span) - 1] + 1
    return start, canonical[start:end]


def _section_at(section_spans: list, start: int) -> str:
    for span in section_spans:
        path, span_start, span_end = span
        if span_start <= start < span_end:
            return path
    return "OTHER"


def _parse_json(text: str) -> dict:
    import json

    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return json.loads(text)
