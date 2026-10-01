"""覆盖驱动的引文扩展迭代测试：独立验证缺失时自动拉入第二轮文献。"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from pubminer.domain.documents import Document, DocumentIdentifier, DocumentVersion, EvidenceSpan
from pubminer.domain.evidence import BiomarkerEvidence, EvidencePolarity, VerificationResult
from pubminer.domain.screening import ScreeningDecision, ScreeningLabel
from pubminer.domain.tasks import TaskStatus
from pubminer.infrastructure.db.orm_claims import ClaimRow
from pubminer.workflows import MiningWorkflow, SearchIntent
from pubminer.workflows.ports import HydratedDocument, ResolutionCandidate

SPAN_1 = "High KRAS expression was associated with poor overall survival (HR 2.1)."
SPAN_2 = "In an independent validation cohort, KRAS remained a significant prognostic factor (HR 1.9)."

ALEMBIC_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


@pytest.fixture()
def session_factory(tmp_path):
    import os
    import subprocess
    import sys

    db = tmp_path / "expansion.db"
    env = {**os.environ, "PUBMINER_DB_URL": f"sqlite:///{db.as_posix()}", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ALEMBIC_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    from pubminer.infrastructure.db.base import create_engine_from_url, make_session_factory

    engine = create_engine_from_url(f"sqlite:///{db.as_posix()}")
    yield make_session_factory(engine)
    engine.dispose()


def _make_doc(pmid: str, canonical: str) -> HydratedDocument:
    document = Document(identifiers=[DocumentIdentifier(kind="pmid", value=pmid)], title=f"S {pmid}")
    version = DocumentVersion(document_id=document.id, canonical_text=canonical, title=document.title)
    return HydratedDocument(
        document=document, version=version,
        section_spans=[("RESULTS", 0, len(canonical))], fulltext_available=True,
    )


def _extract_from(doc: HydratedDocument):
    version = doc.version["id"] if isinstance(doc.version, dict) else doc.version.id
    canonical = doc.version["canonical_text"] if isinstance(doc.version, dict) else doc.version.canonical_text
    span = EvidenceSpan.from_text(version, uuid4(), canonical, 0, "RESULTS")
    return [BiomarkerEvidence(
        biomarker_mention="KRAS", biomarker_type="gene",
        disease_mention="PDAC", role="prognostic", direction="HIGH",
        evidence_span=span,
    )]


class _Search:
    def __init__(self, pmids):
        self.pmids = pmids

    def search(self, intent):
        return [{"pmid": p} for p in self.pmids]


class _Hydrate:
    def __init__(self, docs):
        self.docs = docs

    def hydrate(self, pmid):
        return self.docs[pmid]


class _Screen:
    def screen(self, document, criteria=None):
        return ScreeningDecision(document_id=document.id, label=ScreeningLabel.RELEVANT)


class _Extract:
    def extract(self, doc):
        return _extract_from(doc)


class _Normalize:
    def resolve(self, mention, entity_type):
        return [ResolutionCandidate(entity_id="t", name="KRAS", identifier="NCBIGene:3845", score=1.0)], False


class _Verify:
    def __init__(self, mark_iv_from_round2=False):
        self.mark_iv_from_round2 = mark_iv_from_round2

    def verify(self, signature, evidence):
        # 第二轮（验证队列文献，span 文本为 SPAN_2）报告独立验证
        round2 = evidence.evidence_span.text == SPAN_2
        return VerificationResult(
            polarity=EvidencePolarity.SUPPORT,
            entity_correct=True, disease_correct=True,
            independent_validation=self.mark_iv_from_round2 and round2,
        )


def _ports(pmids, docs, citations, mark_iv=False):
    return SimpleNamespace(
        search=_Search(pmids), hydrate=_Hydrate(docs), screen=_Screen(),
        extract=_Extract(), normalize=_Normalize(), verify=_Verify(mark_iv),
        citations=citations,
    )


class _Citations:
    def __init__(self, mapping):
        self.mapping = {
            pmid: SimpleNamespace(cited_by=cited, references=[])
            for pmid, cited in mapping.items()
        }

    def fetch_citations(self, pmids):
        return {p: self.mapping.get(p, SimpleNamespace(cited_by=[], references=[])) for p in pmids}


class TestCitationExpansion:
    def test_expansion_round_runs_and_flags_independent_validation(self, session_factory):
        SPAN_3 = "Validation cohort confirmed KRAS as independent prognostic factor (HR 1.9)."
        docs = {"111": _make_doc("111", SPAN_1), "222": _make_doc("222", SPAN_2), "333": _make_doc("333", SPAN_3)}
        ports = _ports(["111"], docs, _Citations({"111": ["222", "333"]}), mark_iv=True)
        # SEARCH 只给第一轮；222 由扩展引入

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
            task_id = workflow.start(
                session_id=None, intents=[SearchIntent(name="q", query="x", max_results=5)],
            )
            repo = TaskRepository(session)
            task = repo.get(task_id)
            steps = repo.list_steps(task_id)

        assert task.status == TaskStatus.REVIEW_READY
        types = [s["type"] for s in steps]
        for expected in ("COVERAGE", "EXPAND", "HYDRATE2", "SCREEN2", "EXTRACT2", "VERIFY2"):
            assert expected in types, expected

        # 扩展步骤产出新 PMID
        with session_scope(session_factory) as session:
            repo = TaskRepository(session)
            expand_index = next(s["index"] for s in steps if s["type"] == "EXPAND")
            expand_output = repo.step_output(task_id, expand_index)
        assert expand_output["expand_pmids"] == ["222", "333"]

        # 同签名合并：单 claim、两条证据（来自两篇文献）、独立验证自动置真
        with session_scope(session_factory) as session:
            claim_rows = session.execute(select(ClaimRow)).scalars().all()
            assert len(claim_rows) == 1
            evidences = ClaimRepository(session).get_evidence(claim_rows[0].id)
            assert len(evidences) == 3
            assert {e.document_id for e in evidences} and all(
                e.study.independent_validation for e in evidences
            )

    def test_independent_validation_found_skips_expansion(self, session_factory):
        docs = {"111": _make_doc("111", SPAN_1)}
        citations = _Citations({"111": ["99999999"]})

        class _VerifyAlwaysIV:
            def verify(self, signature, evidence):
                return VerificationResult(polarity=EvidencePolarity.SUPPORT, independent_validation=True)

        ports = SimpleNamespace(
            search=_Search(["111"]), hydrate=_Hydrate(docs), screen=_Screen(),
            extract=_Extract(), normalize=_Normalize(), verify=_VerifyAlwaysIV(),
            citations=citations,
        )

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
            task_id = workflow.start(
                session_id=None, intents=[SearchIntent(name="q", query="x", max_results=3)],
            )
            steps = TaskRepository(session).list_steps(task_id)

        expand_steps = [s for s in steps if s["type"] == "EXPAND"]
        assert expand_steps and expand_steps[0]["status"] == "SUCCEEDED"
        with session_scope(session_factory) as session:
            output = TaskRepository(session).step_output(task_id, expand_steps[0]["index"])
        assert output == {}  # 门控判定无需扩展
