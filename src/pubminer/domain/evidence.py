"""Evidence：与 Claim 分离的、必须 grounded 到 passage 的证据单元。

不变量（ADR-003 / §8.4）：
- Evidence 必须指向 passage；不得只有 summary；
- 同一 claim 可同时保存 SUPPORT / CONTRADICT / NO_EFFECT / UNCERTAIN；
- LLM confidence 不是事实真值。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from typing import Any

from pydantic import BaseModel, Field, model_validator

from pubminer.domain.documents import EvidenceSpan


class EvidencePolarity(str, Enum):
    SUPPORT = "SUPPORT"
    CONTRADICT = "CONTRADICT"
    NO_EFFECT = "NO_EFFECT"
    UNCERTAIN = "UNCERTAIN"


class StudyDesign(str, Enum):
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    PROSPECTIVE_COHORT = "prospective_cohort"
    RETROSPECTIVE_COHORT = "retrospective_cohort"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    RCT = "rct"
    CASE_REPORT = "case_report"
    IN_VITRO = "in_vitro"
    IN_VIVO = "in_vivo"
    UNKNOWN = "unknown"


class AnalysisType(str, Enum):
    UNIVARIATE = "univariate"
    MULTIVARIATE = "multivariate"
    UNKNOWN = "unknown"


class Population(BaseModel):
    """研究人群属性。"""

    n: int | None = None
    disease_stage: str | None = None
    ethnicity: str | None = None
    country: str | None = None
    age_range: str | None = None
    age_mean: float | None = None
    tumor_location: str | None = Field(None, description="如 colon / rectum / CRC")
    male_count: int | None = None
    female_count: int | None = None


class Statistics(BaseModel):
    """效应量与显著性。字符串保留原文表达，防止换算错误。

    LLM 常把数值输出为 JSON number（如 0.82）；这里宽松转型为字符串，
    因为原文表达（"0.82"、"2.1e-3"）才是证据的一部分。
    """

    effect_measure: str | None = Field(None, description="HR / OR / RR / beta")
    effect_value: str | None = None
    confidence_interval: str | None = None
    p_value: str | None = None
    statistically_significant: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_numbers_to_str(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("effect_measure", "effect_value", "confidence_interval", "p_value"):
                value = data.get(key)
                if value is not None and not isinstance(value, str):
                    data[key] = str(value)
        return data


class StudyAttributes(BaseModel):
    """抽取的研究属性（LLM 只抽取属性，等级由规则引擎计算）。"""

    design: StudyDesign = StudyDesign.UNKNOWN
    independent_validation: bool | None = None
    multivariate_adjusted: bool | None = None
    independent_cohort: bool | None = None
    population: Population = Field(default_factory=Population)
    follow_up_months: int | None = None
    detection_method: str | None = Field(None, description="如 IHC / qPCR / western blot")
    sample_type: str | None = Field(None, description="如 tissue / blood / serum")
    study_conclusion: str | None = None
    drugs: str | None = None
    evidence_source: str = Field("abstract", description="abstract | fulltext")


class Evidence(BaseModel):
    """一条证据：claim + 原文 span + 研究属性 + 统计量。"""

    id: UUID = Field(default_factory=uuid4)
    claim_id: UUID
    document_id: UUID
    document_version_id: UUID
    passage_id: UUID
    span: EvidenceSpan
    polarity: EvidencePolarity
    study: StudyAttributes = Field(default_factory=StudyAttributes)
    statistics: Statistics | None = None
    extraction_run_id: UUID | None = Field(None, description="来源 run；不同 pipeline 可并存")
    review_status: str = Field("pending", description="pending | approved | rejected")
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    @model_validator(mode="after")
    def _check(self) -> "Evidence":
        if not self.span.text.strip():
            raise ValueError("evidence span text must be non-empty (no-evidence-no-claim)")
        return self


class VerificationResult(BaseModel):
    """附录 A 契约：VERIFY 步骤输出。"""

    polarity: EvidencePolarity
    entity_correct: bool | None = None
    disease_correct: bool | None = None
    endpoint_correct: bool | None = None
    statistically_significant: bool | None = None
    analysis_type: AnalysisType = AnalysisType.UNKNOWN
    independent_validation: bool | None = None
    reasons: list[str] = Field(default_factory=list)
    needs_human_review: bool = False


class BiomarkerEvidence(BaseModel):
    """附录 A 契约：EXTRACT 步骤的 typed 输出（biomarker task family）。"""

    biomarker_mention: str
    biomarker_type: str | None = Field(
        None, description="gene | protein | clinical_marker | metabolite | other；驱动归一化路由"
    )
    disease_mention: str
    role: str = Field(..., description="prognostic | diagnostic | predictive")
    direction: str | None = None
    outcome: str | None = None
    population: Population = Field(default_factory=Population)
    study_design: StudyDesign = StudyDesign.UNKNOWN
    statistics: Statistics | None = None
    evidence_span: EvidenceSpan
    evidence_source: str = Field("abstract", description="abstract | fulltext")

    @model_validator(mode="after")
    def _check_role(self) -> "BiomarkerEvidence":
        if self.role not in {"prognostic", "diagnostic", "predictive"}:
            raise ValueError(f"invalid biomarker role: {self.role}")
        return self
