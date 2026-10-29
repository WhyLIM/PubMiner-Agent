"""PR-006 测试：Alembic 迁移可重复 + repositories 读写 roundtrip。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(db_path: Path, *args: str) -> None:
    env = {
        **os.environ,
        "PUBMINER_DB_URL": f"sqlite:///{db_path.as_posix()}",
        "PYTHONUTF8": "1",  # 迁移文件为 UTF-8；中文 Windows 默认 GBK 会解码失败
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stdout}\n{result.stderr}"


@pytest.fixture()
def migrated_db(tmp_path: Path) -> Path:
    db = tmp_path / "migrations.db"
    _alembic(db, "upgrade", "head")
    return db


class TestMigrations:
    def test_upgrade_head_creates_tables(self, migrated_db: Path):
        import sqlite3

        tables = {
            row[0]
            for row in sqlite3.connect(migrated_db).execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        expected = {
            "documents", "document_identifiers", "document_versions", "passages",
            "entities", "entity_identifiers", "mentions", "resolutions",
            "claims", "evidence", "alembic_version",
        }
        assert expected <= tables

    def test_migration_repeatable_down_up(self, tmp_path: Path):
        db = tmp_path / "cycle.db"
        _alembic(db, "upgrade", "head")
        _alembic(db, "downgrade", "base")
        _alembic(db, "upgrade", "head")  # 再执行一次不报错

    def test_double_upgrade_is_idempotent(self, migrated_db: Path):
        # 已在 head，再次 upgrade 不做任何事且不报错
        _alembic(migrated_db, "upgrade", "head")


@pytest.fixture()
def session_factory(migrated_db: Path):
    from pubminer.infrastructure.db.base import make_session_factory
    from pubminer.infrastructure.db.base import create_engine_from_url

    engine = create_engine_from_url(f"sqlite:///{migrated_db.as_posix()}")
    yield make_session_factory(engine)
    engine.dispose()


def _domain_document():
    from pubminer.domain.documents import Document, DocumentIdentifier

    return Document(
        identifiers=[
            DocumentIdentifier(kind="pmid", value="33145284"),
            DocumentIdentifier(kind="doi", value="10.1371/X"),
        ],
        title="KRAS status in PDAC",
        journal="PLoS One",
        year=2021,
    )


class TestTaskOrphanRecovery:
    def test_running_tasks_marked_failed_and_resumable(self, session_factory):
        """进程重启后孤儿任务回收：运行态任务 → FAILED，RUNNING 步 → FAILED_RETRYABLE。"""
        from uuid import uuid4

        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.orm_tasks import RunStepRow, TaskRow
        from pubminer.infrastructure.db.repositories.workflow import TaskRepository

        orphan_id, done_id = uuid4(), uuid4()
        with session_scope(session_factory) as session:
            for tid, status in ((orphan_id, "EXTRACTING"), (done_id, "REVIEW_READY")):
                session.add(TaskRow(id=tid, session_id=None, kind="mining", request={}, status=status))
                session.flush()
            session.add(RunStepRow(task_id=orphan_id, step_index=0, step_type="SEARCH", status="SUCCEEDED"))
            session.add(RunStepRow(task_id=orphan_id, step_index=1, step_type="EXTRACT", status="RUNNING"))
            session.flush()

            recovered = TaskRepository(session).fail_orphaned_runs()
            assert recovered == 1

            orphan = session.get(TaskRow, orphan_id)
            done = session.get(TaskRow, done_id)
            assert orphan.status == "FAILED"
            assert done.status == "REVIEW_READY"  # 终态任务不受影响
            steps = session.execute(
                __import__("sqlalchemy").select(RunStepRow).where(RunStepRow.task_id == orphan_id)
            ).scalars().all()
            by_type = {s.step_type: s for s in steps}
            assert by_type["SEARCH"].status == "SUCCEEDED"
            assert by_type["EXTRACT"].status == "FAILED_RETRYABLE"
            assert "restarted" in by_type["EXTRACT"].error

            # 回收后 first_failed_step_index 命中中断步，「恢复/重跑」可用
            idx = TaskRepository(session).first_failed_step_index(orphan_id)
            assert idx == 1


class TestDocumentRepository:
    def test_upsert_and_dedupe(self, session_factory):
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository
        from pubminer.infrastructure.db.base import session_scope

        doc = _domain_document()
        with session_scope(session_factory) as session:
            first = DocumentRepository(session).upsert_document(doc)
            second = DocumentRepository(session).upsert_document(doc)
            assert first.id == second.id

    def test_add_version_and_passages_roundtrip(self, session_factory):
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository
        from pubminer.domain.documents import DocumentVersion

        version = DocumentVersion(
            document_id=_domain_document().id,
            canonical_text="RESULT TEXT ONE\n\nABSTRACT BODY",
            title="t",
        )
        spans = [("RESULTS", 0, 15), ("ABSTRACT", 17, 30)]
        with session_scope(session_factory) as session:
            repo = DocumentRepository(session)
            doc = repo.upsert_document(_domain_document())
            version_id = repo.add_document_version(doc.id, version, spans)

            stored = repo.get(doc.id)
            assert stored is not None
            assert stored.versions[0].canonical_text == version.canonical_text
            assert stored.versions[0].text_hash == version.text_hash

            # passages 按 span 切片落库，且与 canonical text 一致
            from sqlalchemy import select
            from pubminer.infrastructure.db.orm_documents import PassageRow

            rows = session.execute(
                select(PassageRow).where(PassageRow.document_version_id == version_id)
            ).scalars().all()
            assert len(rows) == 2
            by_path = {r.section_path: r for r in rows}
            assert by_path["RESULTS"].text == "RESULT TEXT ONE"
            assert by_path["ABSTRACT"].text == "ABSTRACT BODY"
            assert version.canonical_text[by_path["ABSTRACT"].start_char : by_path["ABSTRACT"].end_char] == "ABSTRACT BODY"


class TestClaimRepository:
    def _seed(self, session) -> tuple:
        from pubminer.domain.entities import Entity, EntityAlias, EntityIdentifier
        from pubminer.infrastructure.db.repositories.entities import EntityRepository

        repo = EntityRepository(session)
        gene = repo.create_entity(
            Entity(
                type="GENE",
                canonical_name="ABC1",
                ontology_version="hgnc-2026.01",
                aliases=[EntityAlias(alias="ABC1", is_canonical=True)],
                identifiers=[
                    EntityIdentifier(
                        entity_id=uuid4(),
                        namespace="NCBIGene",
                        value="5290",
                        ontology_version="hgnc-2026.01",
                        source="ncbi-gene-resolver",
                        score=0.99,
                    )
                ],
            )
        )
        disease = repo.create_entity(
            Entity(
                type="DISEASE",
                canonical_name="Pancreatic cancer",
                ontology_version="mesh-2026",
                identifiers=[
                    EntityIdentifier(
                        entity_id=uuid4(),
                        namespace="MESH",
                        value="D010190",
                        ontology_version="mesh-2026",
                        source="mesh-resolver",
                    )
                ],
            )
        )
        from pubminer.domain.documents import DocumentVersion
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository

        doc_version = DocumentVersion(
            document_id=_domain_document().id,
            canonical_text="High ABC1 expression predicted poor overall survival (HR 2.1).",
            title="t",
        )
        doc_repo = DocumentRepository(session)
        doc = doc_repo.upsert_document(_domain_document())
        version_id = doc_repo.add_document_version(
            doc.id, doc_version, [("RESULTS", 0, len(doc_version.canonical_text))]
        )
        return gene, disease, doc, version_id, doc_version

    def test_create_claim_with_evidence_and_dedupe(self, session_factory):
        from pubminer.domain.claims import Claim, ClaimContext, Direction, Predicate
        from pubminer.domain.documents import EvidenceSpan
        from pubminer.domain.evidence import Evidence, EvidencePolarity, Statistics
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository

        with session_scope(session_factory) as session:
            gene, disease, doc, version_id, doc_version = self._seed(session)

            span = EvidenceSpan.from_text(
                version_id, uuid4(), doc_version.canonical_text, 0, "RESULTS"
            )
            claim = Claim(
                subject_entity_id=gene.id,
                predicate=Predicate.PROGNOSTIC,
                object_entity_id=disease.id,
                direction=Direction.HIGH,
                context=ClaimContext(disease_entity_id=disease.id, disease_name="PDAC", outcome="overall_survival"),
            )
            evidence = Evidence(
                claim_id=claim.id,
                document_id=doc.id,
                document_version_id=version_id,
                passage_id=span.passage_id,
                span=span,
                polarity=EvidencePolarity.SUPPORT,
                statistics=Statistics(effect_measure="HR", effect_value="2.1", p_value="0.002"),
            )
            repo = ClaimRepository(session)
            created = repo.create_candidate_claim(claim, [evidence])
            again = repo.create_candidate_claim(claim, [evidence])
            assert created.id == again.id  # signature 去重

            loaded = repo.get(created.id)
            assert loaded is not None and loaded.canonical_signature == created.canonical_signature
            stored_evidence = repo.get_evidence(created.id)
            assert len(stored_evidence) == 1
            assert stored_evidence[0].span.text_hash == span.text_hash
            assert stored_evidence[0].statistics.effect_value == "2.1"

    def test_no_evidence_no_claim(self, session_factory):
        from pubminer.domain.claims import Claim, Predicate
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository

        with session_scope(session_factory) as session:
            gene, *_ , doc, version_id, _ = self._seed(session)
            claim = Claim(subject_entity_id=gene.id, predicate=Predicate.PROGNOSTIC, object_value="PDAC")
            with pytest.raises(ValueError, match="no-evidence-no-claim"):
                ClaimRepository(session).create_candidate_claim(claim, [])

    def test_four_polarities_coexist(self, session_factory):
        from pubminer.domain.claims import Claim, Predicate
        from pubminer.domain.documents import EvidenceSpan
        from pubminer.domain.evidence import Evidence, EvidencePolarity
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.claims import ClaimRepository

        with session_scope(session_factory) as session:
            gene, _disease, doc, version_id, doc_version = self._seed(session)
            claim = Claim(subject_entity_id=gene.id, predicate=Predicate.PROGNOSTIC, object_value="PDAC")
            evidences = []
            for polarity in EvidencePolarity:
                span = EvidenceSpan.from_text(version_id, uuid4(), doc_version.canonical_text, 0, "RESULTS")
                evidences.append(
                    Evidence(
                        claim_id=claim.id, document_id=doc.id,
                        document_version_id=version_id, passage_id=span.passage_id,
                        span=span, polarity=polarity,
                    )
                )
            repo = ClaimRepository(session)
            created = repo.create_candidate_claim(claim, evidences[:1])
            repo.add_evidence(created.id, evidences[1:])
            stored = repo.get_evidence(created.id)
            assert {e.polarity for e in stored} == set(EvidencePolarity)
