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

    def extract(self, hydrated: HydratedDocument) -> tuple[list[BiomarkerEvidence], dict | None]:
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
            biomarker_type: str | None = None
            disease_mention: str | None = None
            role: str
            direction: str | None = None
            outcome: str | None = None
            statistics: dict | None = None
            study_design: str | None = None
            evidence_span: str

        class _StudyContext(BaseModel):
            n: int | None = None
            disease_stage: str | None = None
            tumor_location: str | None = None
            age_mean: float | None = None
            age_range: str | None = None
            ethnicity: str | None = None
            country: str | None = None
            male_count: int | None = None
            female_count: int | None = None
            detection_method: str | None = None
            sample_type: str | None = None
            follow_up_months: int | None = None
            multivariate_adjusted: bool | None = None
            study_conclusion: str | None = None
            drugs: str | None = None

        class _ExtractionOut(BaseModel):
            items: list[_Item] = []
            study_context: _StudyContext | None = None

        def _repair_out_model():
            from pydantic import BaseModel as _BM

            class _RepairOut(_BM):
                evidence_span: str
            return _RepairOut

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
                # 二次修复：用 mention 所在的原文片段重新请求逐字摘录
                repaired = self._repair_span(canonical, raw)
                if repaired is not None:
                    raw = {**raw, "evidence_span": repaired}
                    located = locate_span(canonical, repaired.strip())
            if located is None:
                # grounding 失败：丢弃该条（宁可漏，不可造）
                logger.warning(
                    "dropped extraction for %r: evidence_span not found in canonical text",
                    raw.get("biomarker_mention"),
                )
                continue
            start, span_text = located
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
                src = "fulltext" if hydrated.fulltext_available else "abstract"
                results.append(
                    BiomarkerEvidence(
                        biomarker_mention=str(raw["biomarker_mention"]),
                        biomarker_type=raw.get("biomarker_type"),
                        evidence_source=src,
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

    def _repair_span(self, canonical: str, raw: dict) -> str | None:
        """span 二次修复：围绕 mention 所在片段请求逐字重摘。尽力而为。"""
        mention = str(raw.get("biomarker_mention", "")).strip()
        if not mention:
            return None
        anchor = canonical.lower().find(mention.lower())
        if anchor < 0:
            return None
        window_start = max(0, anchor - 600)
        window = canonical[window_start : anchor + 900]

        from pydantic import BaseModel as _BM

        class _RepairOut(_BM):
            evidence_span: str

        repair_prompt = self.prompts.get("extraction/biomarker", "v1")
        exact_instruction = (
            "IMPORTANT: the evidence_span MUST be copied character-for-character "
            "from the passage above. Do not paraphrase or merge sentences."
        )
        try:
            response = self.llm.structured_generate(
                LLMRequest(
                    purpose="extraction-repair",
                    prompt_version="extraction/biomarker@v1",
                    system=repair_prompt.system,
                    user=repair_prompt.render(passage=window) + "\n\n" + exact_instruction,
                    temperature=0.0,
                    max_tokens=4096,
                    metadata={"schema_version": "biomarker-v1", "repair": "1"},
                ),
                _RepairOut,
            )
            payload = _parse_json(response.text)
        except Exception as exc:
            logger.warning("span repair failed for %r: %s", mention, exc)
            return None
        return str(payload.get("evidence_span", "")).strip() or None



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


class LlmVerifyPort:
    """verification/v1：极性判定，confidence 不转真值。"""

    def __init__(self, llm, prompt_registry) -> None:
        self.llm = llm
        self.prompts = prompt_registry

    def verify(self, claim_signature: str, evidence) -> VerificationResult:
        from pubminer.workflows.verification_rules import rule_assess

        prompt = self.prompts.get("verification", "v1")
        span_text = evidence.evidence_span.text[:_MAX_CONTEXT_CHARS]
        stats = evidence.statistics.model_dump() if evidence.statistics else None
        rule_hint = rule_assess(span_text, stats)

        hint_lines = []
        if rule_hint.get("statistically_significant") is not None:
            hint_lines.append(
                f"Rule-based pre-check: p-value {'<' if rule_hint['statistically_significant'] else '>='} 0.05 "
                f"({'; '.join(rule_hint['rule_reasons'])})"
            )
        hint_text = "\n".join(hint_lines)

        suffix = "\n\n" + hint_text if hint_text else ""
        response = self.llm.structured_generate(
            LLMRequest(
                purpose="verification",
                prompt_version="verification@v1",
                system=prompt.system,
                user=prompt.render(claim=claim_signature, passage=span_text) + suffix,
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


