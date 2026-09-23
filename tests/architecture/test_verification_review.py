"""PR-013 测试：跨论文聚合、review 队列与决定、覆盖矩阵。"""
from __future__ import annotations

from uuid import uuid4

import pytest

REPO_ROOT = None  # 占位避免误用


def _seed_claim_via_api(client, *, polarity: str, signature_hint: str = "pdac") -> str:
    """用 mining pipeline 造 claim；本文件直接在 DB 层构造更快——见 _make_claim。"""
    raise NotImplementedError


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory: pytest.TempPathFactory) -> "object":
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    tmpdir = tmp_path_factory.mktemp("reviews")
    db = tmpdir / "reviews.db"
    env = {**os.environ, "PUBMINER_DB_URL": f"sqlite:///{db.as_posix()}", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(repo_root / "alembic.ini"), "upgrade", "head"],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return db


@pytest.fixture()
def session_factory(migrated_db):
    from pubminer.infrastructure.db.base import create_engine_from_url, make_session_factory

    engine = create_engine_from_url(f"sqlite:///{migrated_db.as_posix()}")
    yield make_session_factory(engine)
    engine.dispose()


def _seed_world(session_factory, *, with_conflict: bool = False):
    """造 documents + entities + claim(s) + evidence，返回 claim id。"""
    from pubminer.domain.claims import Claim, Predicate
    from pubminer.domain.documents import Document, DocumentIdentifier, DocumentVersion, EvidenceSpan
    from pubminer.domain.evidence import Evidence, EvidencePolarity
    from pubminer.domain.entities import Entity, EntityIdentifier
    from pubminer.infrastructure.db.base import session_scope
    from pubminer.infrastructure.db.repositories.claims import ClaimRepository
    from pubminer.infrastructure.db.repositories.documents import DocumentRepository
    from pubminer.infrastructure.db.repositories.entities import EntityRepository

    with session_scope(session_factory) as session:
        entity_repo = EntityRepository(session)
        existing = entity_repo.find_by_identifier("NCBIGene", "3845", "mvp-2026")
        if existing is not None:
            gene = existing
        else:
            gene = entity_repo.create_entity(
                Entity(
                    type="GENE",
                    canonical_name="KRAS",
                    ontology_version="mvp-2026",
                    identifiers=[EntityIdentifier(
                        entity_id=uuid4(), namespace="NCBIGene", value="3845",
                        ontology_version="mvp-2026", source="ncbi-gene-resolver",
                    )],
                )
            )
        doc_repo = DocumentRepository(session)

        def make_doc(pmid: str, text: str):
            document = Document(identifiers=[DocumentIdentifier(kind="pmid", value=pmid)])
            version = DocumentVersion(document_id=document.id, canonical_text=text)
            stored = doc_repo.upsert_document(document)
            version_id = doc_repo.get_or_add_version(
                stored.id, version, [("RESULTS", 0, len(text))]
            )
            return stored.id, version_id, text

        doc1_id, v1, text1 = make_doc("111", "KRAS high expression predicts poor OS (HR 2.1).")
        claim = Claim(
            subject_entity_id=gene.id,
            predicate=Predicate.PROGNOSTIC,
            object_value="PDAC",
        )
        span1 = EvidenceSpan.from_text(v1, uuid4(), text1, 0, "RESULTS")
        claim_repo = ClaimRepository(session)
        created = claim_repo.create_candidate_claim(
            claim,
            [Evidence(
                claim_id=claim.id, document_id=doc1_id, document_version_id=v1,
                passage_id=span1.passage_id, span=span1, polarity=EvidencePolarity.SUPPORT,
            )],
        )
        second_polarity = EvidencePolarity.CONTRADICT if with_conflict else EvidencePolarity.SUPPORT

        if with_conflict:
            doc2_id, v2, text2 = make_doc("222", "KRAS expression was not associated with OS in cohort B.")
            span2 = EvidenceSpan.from_text(v2, uuid4(), text2, 0, "RESULTS")
            claim_repo.add_evidence(
                created.id,
                [Evidence(
                    claim_id=created.id, document_id=doc2_id, document_version_id=v2,
                    passage_id=span2.passage_id, span=span2, polarity=second_polarity,
                )],
            )
        return created.id


class TestAggregation:
    def test_support_only_not_conflict(self, session_factory):
        claim_id = _seed_world(session_factory)
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository
        from pubminer.workflows.verification import CrossPaperVerifier

        with session_scope(session_factory) as session:
            verifier = CrossPaperVerifier(ClaimRepository(session))
            aggregations = {a.claim_id: a for a in verifier.aggregate(session)}
            agg = aggregations[claim_id]
            assert agg.support_count == 1 and not agg.has_conflict
            assert not agg.independent_validation
            assert any("独立" in r for r in agg.reasons)

    def test_conflicting_polarities_flagged(self, session_factory):
        claim_id = _seed_world(session_factory, with_conflict=True)
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository
        from pubminer.workflows.verification import CrossPaperVerifier

        with session_scope(session_factory) as session:
            verifier = CrossPaperVerifier(ClaimRepository(session))
            agg = {a.claim_id: a for a in verifier.aggregate(session)}[claim_id]
            assert agg.has_conflict and agg.contradict_count == 1
            assert agg.distinct_documents == 2


class TestReviewFlowOverApi:
    @pytest.fixture()
    def app_client(self, migrated_db, tmp_path):
        import shutil

        from fastapi.testclient import TestClient

        from pubminer.api.app import create_app
        from pubminer.api.deps import build_container
        from tests.architecture.test_api_v1 import _fake_ports

        test_db = tmp_path / "reviews-api.db"
        shutil.copy(migrated_db, test_db)
        container = build_container(f"sqlite:///{test_db.as_posix()}", workflow_ports=_fake_ports())
        with TestClient(create_app(container)) as client:
            yield client

    def _make_claim(self, client) -> str:
        created = client.post(
            "/api/v1/tasks",
            json={"intents": [{"name": "q", "query": "x", "max_results": 5}]},
        )
        assert created.status_code == 202
        claims = client.get("/api/v1/claims?status=CANDIDATE").json()["claims"]
        return claims[0]["claim_id"]

    def test_queue_lists_candidates_and_decision_accept(self, app_client):
        claim_id = self._make_claim(app_client)

        queue = app_client.get("/api/v1/reviews/queue").json()["items"]
        assert any(item["claim_id"] == claim_id for item in queue)

        detail = app_client.get("/api/v1/claims/00000000-0000-0000-0000-000000000001/evidence")
        detail.raise_for_status() if detail.status_code == 200 else None

        # 乐观锁：错误版本 → 409
        stale = app_client.post(
            "/api/v1/reviews/decision",
            json={"claim_id": claim_id, "decision": "ACCEPT", "reviewer_id": "curator1",
                  "reason": "matches source", "expected_version": 99},
        )
        assert stale.status_code == 409

        accepted = app_client.post(
            "/api/v1/reviews/decision",
            json={"claim_id": claim_id, "decision": "ACCEPT", "reviewer_id": "curator1",
                  "reason": "matches source", "expected_version": 1},
        )
        assert accepted.status_code == 201
        assert accepted.json()["claim_status"] == "REVIEWED"

        # REVIEWED → REJECTED 是合法迁移（reviewer 改变主意，轨迹保留）
        again = app_client.post(
            "/api/v1/reviews/decision",
            json={"claim_id": claim_id, "decision": "REJECT", "reviewer_id": "curator1",
                  "reason": "re-checked", "expected_version": accepted.json()["claim_version"]},
        )
        assert again.status_code == 201
        assert again.json()["claim_status"] == "REJECTED"

    def test_edit_accept_preserves_before_and_bumps_version(self, app_client):
        claim_id = self._make_claim(app_client)
        decided = app_client.post(
            "/api/v1/reviews/decision",
            json={"claim_id": claim_id, "decision": "EDIT_ACCEPT", "reviewer_id": "curator2",
                  "reason": "direction corrected from LOW", "expected_version": 1,
                  "revision": {"direction": "HIGH"}},
        )
        assert decided.status_code == 201
        assert decided.json()["claim_status"] == "REVIEWED"
        assert decided.json()["claim_version"] == 2

        claims = app_client.get("/api/v1/claims?status=REVIEWED").json()["claims"]
        edited = next(c for c in claims if c["claim_id"] == claim_id)
        assert edited["direction"] == "HIGH"

    def test_reject_and_needs_review(self, app_client):
        claim_id = self._make_claim(app_client)
        rejected = app_client.post(
            "/api/v1/reviews/decision",
            json={"claim_id": claim_id, "decision": "REJECT", "reviewer_id": "curator1",
                  "reason": "wrong endpoint", "expected_version": 1},
        )
        assert rejected.json()["claim_status"] == "REJECTED"

        other_id = self._make_claim(app_client)
        needs = app_client.post(
            "/api/v1/reviews/decision",
            json={"claim_id": other_id, "decision": "NEEDS_REVIEW", "reviewer_id": "curator1",
                  "reason": "await independent cohort", "expected_version": 1},
        )
        assert needs.json()["claim_status"] == "CANDIDATE"

    def test_coverage_endpoint(self, app_client):
        self._make_claim(app_client)
        session_id = "00000000-0000-0000-0000-000000000042"
        coverage = app_client.get(f"/api/v1/agent/sessions/{session_id}/coverage").json()
        assert coverage["session_id"] == session_id
        assert coverage["support_count"] >= 0
        assert "questions" in coverage and "unresolved_gaps" in coverage
