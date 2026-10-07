"""RAG 式证据问答：混合检索（embedding 语义 + 关键词命中）→ 证据片段 → LLM 生成。

检索层不依赖 LLM 的主观判定：embedding 负责语义对齐（跨中英文问法），
关键词负责专有名词（基因名/药物名）的精确命中，两者加权取 top-k。
生成层约束 LLM 只依据检索到的片段作答并按编号引用，保证答案可溯源；
LLM 不可用时降级为模板拼装（与旧版前端行为一致），界面不中断。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from pubminer.domain.claims import Claim
from pubminer.application.ports import LLMRequest
from pubminer.workflows.embedding_service import EmbeddingService, cosine_similarity
from pubminer.workflows.verification import CrossPaperVerifier

logger = logging.getLogger("pubminer.qa")

TOP_K = 5
MAX_FRAGMENTS = 8
MAX_FRAGMENT_CHARS = 600
MAX_CLAIMS_FOR_RETRIEVAL = 1000

_TOKEN_SPLIT = re.compile(r"[^\w]+", re.UNICODE)


def keyword_score(question: str, text: str) -> float:
    """字面命中得分：问题词在文本中出现的字符占比（0~1）。

    中文无分词，按切出的 >=2 字词组做子串匹配；命中越长权重越高。
    """
    tokens = [t for t in _TOKEN_SPLIT.split(question.lower()) if len(t) >= 2]
    if not tokens:
        return 0.0
    hay = text.lower()
    matched = sum(len(t) for t in tokens if t in hay)
    return min(1.0, matched / 6.0)


def combined_scores(
    question: str, texts: list[str], embedding_service: EmbeddingService | None, *, session=None,
) -> list[float]:
    """混合得分 = embedding 语义相似度 + 0.5 × 关键词命中。"""
    if not texts:
        return []
    kw = [keyword_score(question, t) for t in texts]
    if embedding_service is None:
        return [0.5 * k for k in kw]
    qvec = embedding_service.build_profile(question)
    vecs = embedding_service.embed_texts(texts, session=session)
    emb = [cosine_similarity(qvec, v) for v in vecs]
    return [e + 0.5 * k for e, k in zip(emb, kw)]


@dataclass
class QaCitation:
    label: str
    claim_signature: str = ""
    polarity: str = ""
    section_path: str = ""
    document_title: str = ""


@dataclass
class QaResult:
    answer: str
    generated_by: str = "template"
    citations: list[QaCitation] = field(default_factory=list)
    matched_claims: list[dict] = field(default_factory=list)


class EvidenceQA:
    """面向单一会话证据库的检索问答（不区分会话归属，检索范围=当前全库聚合）。"""

    def __init__(
        self,
        session: Session,
        claim_repo,
        entity_repo,
        embedding_service: EmbeddingService | None = None,
        llm=None,
        prompt_registry=None,
        session_id=None,
    ) -> None:
        self.session = session
        self.session_id = session_id
        self.claim_repo = claim_repo
        self.entity_repo = entity_repo
        self.embedding_service = embedding_service
        self.llm = llm
        self.prompts = prompt_registry

    # ------------------------------------------------------------------ 检索

    def _claim_text(self, agg, claim: Claim | None, subject_name: str) -> str:
        parts = [subject_name, agg.canonical_signature]
        if agg.reasons:
            parts.append("；".join(agg.reasons))
        if claim is not None and claim.object_value:
            parts.append(str(claim.object_value))
        return " ".join(p for p in parts if p)

    def _resolve_subject(self, claim: Claim | None) -> tuple[str, str]:
        if claim is None or not claim.subject_entity_id:
            return "", ""
        entity = self.entity_repo.get(claim.subject_entity_id)
        if entity is None:
            return "", ""
        etype = getattr(entity.type, "value", entity.type)
        return entity.canonical_name, str(etype).upper()

    def retrieve(self, question: str, top_k: int = TOP_K) -> list[dict]:
        """混合检索：返回 [{agg, claim, subject_name, subject_type, score}]。"""
        from pubminer.infrastructure.db.orm_documents import DocumentVersionRow

        claim_repo = self.claim_repo
        verifier = CrossPaperVerifier(claim_repo)
        aggregations = verifier.aggregate(
            self.session, limit=MAX_CLAIMS_FOR_RETRIEVAL, session_id=self.session_id
        )
        if not aggregations:
            return []

        entries: list[dict] = []
        for agg in aggregations:
            claim = claim_repo.get(agg.claim_id)
            subject_name, subject_type = self._resolve_subject(claim)
            entries.append({
                "agg": agg,
                "claim": claim,
                "subject_name": subject_name,
                "subject_type": subject_type,
                "text": self._claim_text(agg, claim, subject_name),
            })

        scores = combined_scores(
            question, [e["text"] for e in entries], self.embedding_service,
            session=self.session,
        )
        for entry, score in zip(entries, scores):
            entry["score"] = score
        entries.sort(key=lambda e: -e["score"])
        return [e for e in entries[:top_k] if e["score"] > 0.1]

    # ------------------------------------------------------------------ 片段

    def _fragments(self, entries: list[dict]) -> tuple[list[str], list[QaCitation]]:
        """每个命题取支持 + 反对各一条片段（有则取），编号拼装。"""
        from pubminer.infrastructure.db.orm_documents import DocumentVersionRow

        fragments: list[str] = []
        citations: list[QaCitation] = []
        for rank, entry in enumerate(entries, start=1):
            agg = entry["agg"]
            evidences = self.claim_repo.get_evidence(agg.claim_id)
            picked = {"SUPPORT": None, "CONTRADICT": None}
            for ev in evidences:
                pol = ev.polarity.value if hasattr(ev.polarity, "value") else str(ev.polarity)
                if pol in picked and picked[pol] is None:
                    picked[pol] = ev
            for pol, ev in picked.items():
                if ev is None or not ev.span.text:
                    continue
                version_row = self.session.get(
                    DocumentVersionRow, ev.document_version_id
                )
                doc_title = (version_row.title if version_row else "") or ""
                section = ev.span.section_path or "正文"
                text = ev.span.text[:MAX_FRAGMENT_CHARS]
                num = len(fragments) + 1
                fragments.append(
                    f"[{num}] (claim {agg.canonical_signature} | polarity {pol} | {section})\n{text}"
                )
                citations.append(QaCitation(
                    label=f"doc {str(ev.document_version_id)[:8]} · {section} · {pol}",
                    claim_signature=agg.canonical_signature,
                    polarity=pol,
                    section_path=section,
                    document_title=doc_title[:80],
                ))
                if len(fragments) >= MAX_FRAGMENTS:
                    return fragments, citations
        return fragments, citations

    # ------------------------------------------------------------------ 生成

    def _template_answer(self, entries: list[dict], fragments: list[str], citations: list[QaCitation]) -> str:
        if not entries:
            return "在当前证据库中未找到与该问题相关的命题。可尝试换用基因/药物/表型关键词，或先扩大检索范围重跑管线。"
        lines: list[str] = []
        by_claim: dict[str, list[str]] = {}
        for cit in citations:
            by_claim.setdefault(cit.claim_signature, []).append(f"[{citations.index(cit) + 1}]")
        for entry in entries:
            agg = entry["agg"]
            refs = " ".join(by_claim.get(agg.canonical_signature, []))
            lines.append(
                f"【{agg.canonical_signature}】{refs} 支持 {agg.support_count} · 反驳 {agg.contradict_count}"
                f" · 无效应 {agg.no_effect_count} · 不确定 {agg.uncertain_count}"
                f"（{agg.distinct_documents} 篇独立文献，{'已独立验证' if agg.independent_validation else '未达独立验证'}）"
            )
        return "\n\n".join(lines) + "\n\n以上结论均来自当前证据库原文片段，可在文献页逐条复核。"

    def answer(self, question: str) -> QaResult:
        entries = self.retrieve(question)
        fragments, citations = self._fragments(entries)
        matched = [
            {
                "claim_id": str(e["agg"].claim_id),
                "signature": e["agg"].canonical_signature,
                "subject_name": e["subject_name"],
                "score": round(e["score"], 4),
            }
            for e in entries
        ]

        if not fragments:
            return QaResult(
                answer="在当前证据库中未找到与该问题相关的命题或原文片段。可尝试换用基因/药物/表型关键词，或先扩大检索范围重跑管线。",
                generated_by="template",
                citations=[],
                matched_claims=matched,
            )

        if self.llm is not None and self.prompts is not None:
            try:
                prompt = self.prompts.get("qa-answer", "v1")
                response = self.llm.generate(
                    LLMRequest(
                        purpose="qa",
                        prompt_version="qa-answer@v1",
                        system=prompt.system,
                        user=prompt.render(question=question, evidence="\n\n".join(fragments)),
                        temperature=0.2,
                        max_tokens=2048,
                        metadata={"schema_version": "qa-answer-v1"},
                    )
                )
                text = (response.text or "").strip()
                if text:
                    return QaResult(answer=text, generated_by="llm", citations=citations, matched_claims=matched)
            except Exception as exc:  # LLM 失败降级模板，不中断问答
                logger.warning("qa llm generation failed, fallback to template: %s", exc)

        return QaResult(
            answer=self._template_answer(entries, fragments, citations),
            generated_by="template",
            citations=citations,
            matched_claims=matched,
        )
