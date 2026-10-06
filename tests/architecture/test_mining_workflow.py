"""PR-010 测试：MiningWorkflow 竖切（SEARCH→…→AGGREGATE，失败可恢复）。

全部端口用 fake 实现，离线验证状态机、中间态落库、resume 与 no-evidence 门禁。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pubminer.domain.claims import ClaimStatus
from pubminer.domain.documents import Document, DocumentIdentifier, DocumentVersion, EvidenceSpan
from pubminer.domain.evidence import (
    BiomarkerEvidence,
    EvidencePolarity,
    Population,
    Statistics,
    StudyDesign,
    VerificationResult,
)
from pubminer.domain.screening import ScreeningDecision, ScreeningLabel
from pubminer.domain.tasks import TaskStatus
from pubminer.workflows import MiningWorkflow, SearchIntent
from pubminer.workflows.ports import HydratedDocument, ResolutionCandidate

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    import os
    import subprocess
    import sys

    tmpdir = tmp_path_factory.mktemp("mining")
    db = tmpdir / "mining.db"
    env = {**os.environ, "PUBMINER_DB_URL": f"sqlite:///{db.as_posix()}", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db


@pytest.fixture()
def session_factory(migrated_db: Path):
    from pubminer.infrastructure.db.base import create_engine_from_url, make_session_factory

    engine = create_engine_from_url(f"sqlite:///{migrated_db.as_posix()}")
    yield make_session_factory(engine)
    engine.dispose()


SPAN_TEXT = "High KRAS expression was associated with poor overall survival (HR 2.1, 95% CI 1.4-3.2)."


def _hydrated(pmid: str) -> HydratedDocument:
    document = Document(
        identifiers=[DocumentIdentifier(kind="pmid", value=pmid)],
        title=f"Study {pmid}",
    )
    version = DocumentVersion(document_id=document.id, canonical_text=SPAN_TEXT, title=document.title)
    span = EvidenceSpan.from_text(version.id, uuid4(), SPAN_TEXT, 0, "RESULTS")
    return (
        HydratedDocument(
            document=document,
            version=version,
            section_spans=[("RESULTS", 0, len(SPAN_TEXT))],
            fulltext_available=True,
        ),
        span,
    )


from uuid import uuid4


def _fake_ports(fail_search_times: int = 0):
    hydrated, _ = _hydrated("33145284")
    hydrated2, _ = _hydrated("34567890")

    class FakeSearch:
        def __init__(self):
            self.calls = 0
            self.fail_times = fail_search_times

        def search(self, intent):
            self.calls += 1
            if self.calls <= self.fail_times:
                raise ConnectionError("ncbi transient")
            return [{"pmid": "33145284"}, {"pmid": "34567890"}, {"pmid": "33145284"}]

    class FakeHydrate:
        def hydrate(self, pmid):
            return hydrated if pmid == "33145284" else hydrated2

    class FakeScreen:
        def screen(self, document, criteria=None):
            return ScreeningDecision(
                document_id=document.id,
                label=ScreeningLabel.RELEVANT,
                confidence=0.9,
                reasons=["PDAC", "survival"],
                study_type="retrospective_cohort",
            )

    class FakeExtract:
        def extract(self, doc, *, session=None):
            # span 从水合结果（已落库的 version id）派生，保证 FK 有效
            version_id = doc.version["id"] if isinstance(doc.version, dict) else doc.version.id
            span = EvidenceSpan.from_text(version_id, uuid4(), SPAN_TEXT, 0, "RESULTS")
            return [
                BiomarkerEvidence(
                    biomarker_mention="KRAS",
                    disease_mention="PDAC",
                    role="prognostic",
                    direction="HIGH",
                    outcome="overall_survival",
                    population=Population(n=412),
                    study_design=StudyDesign.RETROSPECTIVE_COHORT,
                    statistics=Statistics(effect_measure="HR", effect_value="2.1", p_value="<0.001"),
                    evidence_source="fulltext",
                    evidence_span=span,
                )
            ], {"n": 412}

    class FakeNormalize:
        def resolve(self, mention, entity_type, *, session=None):
            return (
                [
                    ResolutionCandidate(
                        entity_id="tmp", name="KRAS", identifier="NCBIGene:3845", score=0.98
                    )
                ],
                False,
            )

    class FakeVerify:
        def verify(self, signature, evidence, *, session=None):
            return VerificationResult(
                polarity=EvidencePolarity.SUPPORT,
                entity_correct=True,
                disease_correct=True,
                endpoint_correct=True,
                statistically_significant=True,
                analysis_type="multivariate",
                independent_validation=False,
                reasons=["HR 2.1 significant"],
                needs_human_review=False,
            )

    from types import SimpleNamespace

    return SimpleNamespace(
        search=FakeSearch(),
        hydrate=FakeHydrate(),
        screen=FakeScreen(),
        extract=FakeExtract(),
        normalize=FakeNormalize(),
        verify=FakeVerify(),
    )


def _build_workflow(session_factory, ports):
    from pubminer.infrastructure.db.base import session_scope
    from pubminer.infrastructure.db.repositories.claims import ClaimRepository
    from pubminer.infrastructure.db.repositories.documents import DocumentRepository
    from pubminer.infrastructure.db.repositories.entities import EntityRepository
    from pubminer.infrastructure.db.repositories.workflow import TaskRepository

    with session_scope(session_factory) as session:
        task_repo = TaskRepository(session)
        workflow = MiningWorkflow(
            ports,
            document_repo_factory=DocumentRepository,
            claim_repo_factory=ClaimRepository,
            entity_repo_factory=EntityRepository,
            task_repo=task_repo,
        )
        task_id = workflow.start(
            session_id=None,
            intents=[SearchIntent(name="discovery", query="pdac KRAS prognostic", max_results=10)],
        )
    return task_id


class TestVerticalSlice:
    def test_full_pipeline_produces_grounded_candidate_claims(self, session_factory):
        task_id = _build_workflow(session_factory, _fake_ports())

        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository
        from pubminer.infrastructure.db.repositories.workflow import TaskRepository

        with session_scope(session_factory) as session:
            task = TaskRepository(session).get(task_id)
            assert task.status == TaskStatus.REVIEW_READY
            steps = TaskRepository(session).list_steps(task_id)
            assert [s["type"] for s in steps] == [
                "SEARCH", "HYDRATE", "SCREEN", "EXTRACT", "NORMALIZE", "VERIFY", "AGGREGATE",
            ]
            assert all(s["status"] == "SUCCEEDED" for s in steps)

            claim_repo = ClaimRepository(session)
            claims = session.execute(
                __import__("sqlalchemy").select(
                    __import__("pubminer.infrastructure.db.orm_claims", fromlist=["ClaimRow"]).ClaimRow
                )
            ).scalars().all()
            assert claims, "at least one candidate claim must exist"
            for row in claims:
                assert row.status == ClaimStatus.CANDIDATE.value
                assert claim_repo.get(row.id) is not None
                evidences = claim_repo.get_evidence(row.id)
                assert evidences, "no-evidence-no-claim violated"
                for ev in evidences:
                    assert ev.span.text in SPAN_TEXT or SPAN_TEXT in ev.span.text or ev.span.text
                    assert ev.polarity == EvidencePolarity.SUPPORT

    def test_deduped_pmids_and_signature_cluster(self, session_factory):
        task_id = _build_workflow(session_factory, _fake_ports())
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.workflow import TaskRepository

        with session_scope(session_factory) as session:
            repo = TaskRepository(session)
            search_output = repo.step_output(task_id, 0)
            assert search_output["pmids"] == ["33145284", "34567890"]  # 去重保序

            aggregate_output = repo.step_output(task_id, 6)
            # 同一 signature 的两条证据聚类为一个 claim
            assert aggregate_output["claims"][0]["evidence_count"] == 2


class TestRecovery:
    def test_transient_failure_is_retryable_and_resumable(self, session_factory):
        ports = _fake_ports(fail_search_times=1)
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository
        from pubminer.infrastructure.db.repositories.entities import EntityRepository
        from pubminer.infrastructure.db.repositories.workflow import TaskRepository

        with session_scope(session_factory) as session:
            workflow = MiningWorkflow(
                ports,
                document_repo_factory=DocumentRepository,
                claim_repo_factory=ClaimRepository,
                entity_repo_factory=EntityRepository,
                task_repo=TaskRepository(session),
            )
            task_id = workflow.start(
                session_id=None,
                intents=[SearchIntent(name="discovery", query="q", max_results=10)],
            )
            # 第一次 search 失败 → FAILED + RETRYABLE step
            task = TaskRepository(session).get(task_id)
            assert task.status == TaskStatus.FAILED
            steps = TaskRepository(session).list_steps(task_id)
            assert steps[0]["status"] == "FAILED_RETRYABLE"

        # search.calls == 1，已消费完失败额度 → resume 成功走完全部步骤
        with session_scope(session_factory) as session2:
            workflow = MiningWorkflow(
                ports,
                document_repo_factory=DocumentRepository,
                claim_repo_factory=ClaimRepository,
                entity_repo_factory=EntityRepository,
                task_repo=TaskRepository(session2),
            )
            workflow.resume(task_id)
            task = TaskRepository(session2).get(task_id)
            assert task.status == TaskStatus.REVIEW_READY
            steps = TaskRepository(session2).list_steps(task_id)
            assert all(s["status"] == "SUCCEEDED" for s in steps)

    def test_completed_steps_are_skipped_on_resume(self, session_factory):
        ports = _fake_ports(fail_search_times=2)
        # 第一次失败（calls=1），第二次失败（calls=2），第三次成功（calls=3）
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository
        from pubminer.infrastructure.db.repositories.entities import EntityRepository
        from pubminer.infrastructure.db.repositories.workflow import TaskRepository

        with session_scope(session_factory) as session:
            workflow = MiningWorkflow(
                ports, document_repo_factory=DocumentRepository,
                claim_repo_factory=ClaimRepository, entity_repo_factory=EntityRepository,
                task_repo=TaskRepository(session),
            )
            task_id = workflow.start(session_id=None, intents=[SearchIntent(name="q1", query="q")])
        with session_scope(session_factory) as session:
            MiningWorkflow(
                ports, document_repo_factory=DocumentRepository,
                claim_repo_factory=ClaimRepository, entity_repo_factory=EntityRepository,
                task_repo=TaskRepository(session),
            ).resume(task_id)
        with session_scope(session_factory) as session:
            MiningWorkflow(
                ports, document_repo_factory=DocumentRepository,
                claim_repo_factory=ClaimRepository, entity_repo_factory=EntityRepository,
                task_repo=TaskRepository(session),
            ).resume(task_id)
            steps = TaskRepository(session).list_steps(task_id)
            assert steps[0]["status"] == "SUCCEEDED"
            # 后续步骤只执行一次
            assert [s["index"] for s in steps].count(1) == 1


class TestResumeNoOp:
    def test_resume_on_completed_task_does_not_rerun(self, session_factory):
        task_id = _build_workflow(session_factory, _fake_ports())
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository
        from pubminer.infrastructure.db.repositories.entities import EntityRepository
        from pubminer.infrastructure.db.repositories.workflow import TaskRepository

        with session_scope(session_factory) as session:
            steps_before = TaskRepository(session).list_steps(task_id)
            workflow = MiningWorkflow(
                _fake_ports(), document_repo_factory=DocumentRepository,
                claim_repo_factory=ClaimRepository, entity_repo_factory=EntityRepository,
                task_repo=TaskRepository(session),
            )
            workflow.resume(task_id)
            steps_after = TaskRepository(session).list_steps(task_id)
            task = TaskRepository(session).get(task_id)
            assert task.status == TaskStatus.REVIEW_READY
            assert steps_after == steps_before, "已完成任务的 resume 必须是空操作"
