"""PR-005 领域不变量测试：grounding、no-evidence-no-claim、signature、状态机。"""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pubminer.domain.agents import (
    AgentAction,
    AgentSession,
    Budget,
    BudgetDelta,
    BudgetState,
    Plan,
    PlanStep,
    StopReason,
    StopReasonKind,
    TaskSpec,
)
from pubminer.domain.claims import (
    Claim,
    ClaimContext,
    ClaimStatus,
    Direction,
    Predicate,
    build_canonical_signature,
)
from pubminer.domain.documents import (
    Document,
    DocumentIdentifier,
    DocumentVersion,
    EvidenceSpan,
    PassageRef,
)
from pubminer.domain.evidence import (
    AnalysisType,
    Evidence,
    EvidencePolarity,
    VerificationResult,
)
from pubminer.domain.reviews import Review, ReviewDecision, ReviewTarget, ReviewTargetType


class TestGrounding:
    def test_evidence_span_hash_validated(self):
        with pytest.raises(ValidationError, match="text_hash mismatch"):
            EvidenceSpan(
                document_version_id=uuid4(),
                passage_id=uuid4(),
                start_char=0,
                end_char=5,
                text="hello",
                text_hash="bad",
            )

    def test_evidence_span_factory_roundtrip(self):
        span = EvidenceSpan.from_text(uuid4(), uuid4(), "biomarker correlates with OS", 0, "RESULTS")
        assert span.end_char == len("biomarker correlates with OS")
        assert EvidenceSpan.model_validate(span.model_dump(mode="json"))

    def test_passage_ref_must_be_nonempty(self):
        with pytest.raises(ValidationError):
            PassageRef(document_version_id=uuid4(), passage_id="p1", start_char=5, end_char=5)

    def test_document_identity_key_prefers_pmid(self):
        doc = Document(
            identifiers=[DocumentIdentifier(kind="doi", value="10.1/X"), DocumentIdentifier(kind="pmid", value="123")]
        )
        assert doc.identity_key() == "pmid:123"

    def test_document_identity_normalizes_doi(self):
        doc = Document(identifiers=[DocumentIdentifier(kind="doi", value="10.1/AbC")])
        assert doc.identity_key() == "doi:10.1/abc"

    def test_document_without_identifier_rejects_key(self):
        with pytest.raises(ValueError, match="manual confirmation"):
            Document().identity_key()

    def test_document_version_hash_consistency(self):
        doc = DocumentVersion(document_id=uuid4(), canonical_text="canon")
        assert doc.text_hash
        with pytest.raises(ValidationError):
            DocumentVersion(document_id=uuid4(), canonical_text="canon", text_hash="wrong")


def _span() -> EvidenceSpan:
    return EvidenceSpan.from_text(uuid4(), uuid4(), "High ABC1 expression predicted poor OS (HR 2.1)", 0, "RESULTS")


class TestNoEvidenceNoClaim:
    def test_evidence_requires_real_span_text(self):
        claim_id = uuid4()
        with pytest.raises(ValidationError):
            Evidence(
                claim_id=claim_id,
                document_id=uuid4(),
                document_version_id=uuid4(),
                passage_id=uuid4(),
                span=None,  # type: ignore[arg-type]
                polarity=EvidencePolarity.SUPPORT,
            )

    def test_claim_supports_four_polarities(self):
        claim_id = uuid4()
        pols = set()
        for polarity in EvidencePolarity:
            ev = Evidence(
                claim_id=claim_id, document_id=uuid4(), document_version_id=uuid4(),
                passage_id=uuid4(), span=_span(), polarity=polarity,
            )
            pols.add(ev.polarity)
        assert pols == set(EvidencePolarity)

    def test_verification_result_polarities(self):
        for polarity in EvidencePolarity:
            result = VerificationResult(polarity=polarity, reasons=["r"])
            assert result.polarity == polarity
            assert result.analysis_type == AnalysisType.UNKNOWN


class TestCanonicalSignature:
    def test_signature_deterministic(self):
        kwargs = dict(
            subject_identifier="NCBIGene:5290",
            predicate=Predicate.PROGNOSTIC,
            object_identifier="MESH:D010190",
            direction=Direction.HIGH,
            context=ClaimContext(disease_name="PDAC", outcome="overall_survival"),
        )
        assert build_canonical_signature(**kwargs) == build_canonical_signature(**kwargs)

    def test_signature_shape(self):
        sig = build_canonical_signature(
            subject_identifier="NCBIGene:5290",
            predicate="PROGNOSTIC",
            object_value="PDAC",
            direction=Direction.HIGH,
        )
        assert sig == "NCBIGENE:5290 | PROGNOSTIC | PDAC | HIGH"

    def test_claim_autogenerates_signature(self):
        claim = Claim(
            subject_entity_id=uuid4(),
            predicate=Predicate.PROGNOSTIC,
            object_value="PDAC",
            direction=Direction.HIGH,
        )
        assert claim.canonical_signature.startswith("ENTITY:")
        assert "PROGNOSTIC" in claim.canonical_signature

    def test_claim_requires_object(self):
        with pytest.raises(ValidationError):
            Claim(subject_entity_id=uuid4(), predicate=Predicate.PROGNOSTIC)


class TestClaimStateMachine:
    def test_happy_path(self):
        claim = Claim(subject_entity_id=uuid4(), predicate=Predicate.PROGNOSTIC, object_value="PDAC")
        claim.transition(ClaimStatus.REVIEWED, actor="reviewer")
        claim.transition(ClaimStatus.APPROVED, actor="reviewer")
        claim.transition(ClaimStatus.PUBLISHED, actor="reviewer")
        claim.transition(ClaimStatus.DEPRECATED, actor="admin")
        assert claim.status == ClaimStatus.DEPRECATED

    def test_agent_cannot_skip_to_published(self):
        claim = Claim(subject_entity_id=uuid4(), predicate=Predicate.PROGNOSTIC, object_value="PDAC")
        with pytest.raises(ValueError, match="illegal"):
            claim.transition(ClaimStatus.PUBLISHED, actor="agent")

    def test_rejected_is_terminal(self):
        claim = Claim(subject_entity_id=uuid4(), predicate=Predicate.PROGNOSTIC, object_value="PDAC")
        claim.transition(ClaimStatus.REJECTED, actor="reviewer")
        with pytest.raises(ValueError):
            claim.transition(ClaimStatus.REVIEWED, actor="reviewer")


class TestAgentSessionDomain:
    def test_session_requires_goal(self):
        with pytest.raises(ValidationError):
            AgentSession(goal="   ")

    def test_action_type_whitelist(self):
        session = AgentSession(goal="prognostic biomarkers in PDAC")
        with pytest.raises(ValidationError, match="unknown action type"):
            AgentAction(session_id=session.id, turn=0, plan_version=1, action_type="EXECUTE_SQL")

    def test_plan_step_action_whitelist(self):
        with pytest.raises(ValidationError):
            PlanStep(id="s1", action_type="DOWNLOAD_ANYTHING")

    def test_plan_appends_not_overwrites(self):
        session = AgentSession(goal="g")
        session.plans.append(Plan(version=1, steps=[PlanStep(id="s1", action_type="SEARCH")]))
        session.plans.append(Plan(version=2, steps=[PlanStep(id="s2", action_type="SCREEN")]))
        assert session.latest_plan.version == 2
        assert len(session.plans) == 2

    def test_budget_accounting(self):
        state = BudgetState()
        state.add(BudgetDelta(turns=1, articles=25, cost_usd=0.5, search_runs=1))
        state.add(BudgetDelta(turns=1, articles=10, cost_usd=0.25))
        assert state.turns == 2 and state.articles_considered == 35
        assert state.cost_usd == 0.75 and state.search_runs == 1

    def test_budget_limits_are_positive(self):
        with pytest.raises(ValidationError):
            Budget(max_turns=0)

    def test_stop_reason_classification(self):
        assert StopReason(kind=StopReasonKind.NORMAL).is_normal
        assert StopReason(kind=StopReasonKind.LIMIT_COST).is_limited
        assert not StopReason(kind=StopReasonKind.AWAITING_HUMAN).is_limited

    def test_taskspec_missing_fields(self):
        spec = TaskSpec(goal_text="pancreatic cancer biomarkers")
        assert spec.missing_required_fields() == ["disease", "task"]
        spec.disease = "PDAC"
        spec.task = "prognostic_biomarker"
        assert spec.missing_required_fields() == []


class TestReviewInvariants:
    def test_edit_accept_requires_after(self):
        with pytest.raises(ValidationError, match="revised payload"):
            Review(
                target=ReviewTarget(type=ReviewTargetType.CLAIM, id=uuid4()),
                decision=ReviewDecision.EDIT_ACCEPT,
                reviewer_id="curator1",
                reason="fix direction",
            )

    def test_reason_required(self):
        with pytest.raises(ValidationError, match="reason"):
            Review(
                target=ReviewTarget(type=ReviewTargetType.CLAIM, id=uuid4()),
                decision=ReviewDecision.ACCEPT,
                reviewer_id="curator1",
                reason="",
            )

    def test_valid_accept(self):
        review = Review(
            target=ReviewTarget(type=ReviewTargetType.CLAIM, id=uuid4()),
            decision=ReviewDecision.ACCEPT,
            reviewer_id="curator1",
            before={"direction": "HIGH"},
            reason="matches source",
        )
        assert review.decision == ReviewDecision.ACCEPT
