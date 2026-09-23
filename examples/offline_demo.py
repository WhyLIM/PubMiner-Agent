"""端到端离线样例：不联网、不需要任何 API key，直接运行：

    .venv/Scripts/python examples/offline_demo.py

演示 Evidence Agent 的完整管線：检索 → 水合 → 筛选 → 抽取 → 归一化 →
验证 → 聚合，最后打印带原文 span 的候选结论。生产环境中这些 fake
端口由 integrations/adapters 的真实适配器（pubex 客户端 + LLM +
Gene resolver）替换，见 src/pubminer/api/deps.py:build_container_from_env。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pubminer.domain.documents import Document, DocumentIdentifier, DocumentVersion, EvidenceSpan
from pubminer.domain.evidence import BiomarkerEvidence, EvidencePolarity, Statistics, StudyDesign, VerificationResult
from pubminer.domain.screening import ScreeningDecision, ScreeningLabel
from pubminer.infrastructure.db.base import Base
from pubminer.infrastructure.db.repositories.claims import ClaimRepository
from pubminer.infrastructure.db.repositories.documents import DocumentRepository
from pubminer.infrastructure.db.repositories.entities import EntityRepository
from pubminer.infrastructure.db.repositories.workflow import TaskRepository
from pubminer.workflows import MiningWorkflow, SearchIntent
from pubminer.workflows.ports import HydratedDocument

SPAN = "High KRAS expression was associated with poor overall survival (HR 2.1, 95% CI 1.4-3.2)."


# ---- fake 端口：形状与真实适配器一致（真实版见 integrations/adapters/） ----

def build_fake_ports():
    document = Document(
        identifiers=[DocumentIdentifier(kind="pmid", value="33145284")],
        title="KRAS as a prognostic biomarker in PDAC",
        abstract="Retrospective cohort of 412 resected PDAC patients.",
    )
    hydrated = HydratedDocument(
        document=document,
        version=DocumentVersion(document_id=document.id, canonical_text=SPAN, title=document.title),
        section_spans=[("RESULTS", 0, len(SPAN))],
        fulltext_available=True,
    )

    search = SimpleNamespace(
        search=lambda intent: [{"pmid": "33145284"}]
    )

    class Hydrate:
        def hydrate(self, pmid):
            return hydrated

    class Screen:
        def screen(self, doc, criteria=None):
            return ScreeningDecision(
                document_id=doc.id, label=ScreeningLabel.RELEVANT,
                confidence=0.92, reasons=["PDAC", "survival endpoint"],
            )

    class Extract:
        def extract(self, doc):
            version = doc.version
            canonical = version["canonical_text"] if isinstance(version, dict) else version.canonical_text
            version_id = version["id"] if isinstance(version, dict) else version.id
            start = canonical.find(SPAN)
            return [BiomarkerEvidence(
                biomarker_mention="KRAS", disease_mention="PDAC", role="prognostic",
                direction="HIGH", outcome="overall_survival",
                study_design=StudyDesign.RETROSPECTIVE_COHORT,
                statistics=Statistics(effect_measure="HR", effect_value="2.1", p_value="<0.001"),
                evidence_span=EvidenceSpan.from_text(version_id, uuid4(), SPAN, start, "RESULTS"),
            )]

    class Normalize:
        def resolve(self, mention, entity_type):
            from pubminer.workflows.ports import ResolutionCandidate
            return [ResolutionCandidate(
                entity_id="tmp", name="KRAS", identifier="NCBIGene:3845", score=0.98,
            )], False

    class Verify:
        def verify(self, signature, evidence):
            return VerificationResult(
                polarity=EvidencePolarity.SUPPORT,
                entity_correct=True, disease_correct=True, endpoint_correct=True,
                statistically_significant=True, independent_validation=False,
                reasons=["HR 2.1 显著"],
            )

    return SimpleNamespace(search=search, hydrate=Hydrate(), screen=Screen(),
                           extract=Extract(), normalize=Normalize(), verify=Verify())


def main() -> int:
    # 内存数据库（StaticPool 让所有会话共享同一份数据）
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_scope_like(factory) as session:
        workflow = MiningWorkflow(
            build_fake_ports(),
            document_repo_factory=DocumentRepository,
            claim_repo_factory=ClaimRepository,
            entity_repo_factory=EntityRepository,
            task_repo=TaskRepository(session),
            pipeline_release="offline-demo",
        )
        task_id = workflow.start(
            session_id=None,
            intents=[SearchIntent(name="discovery", query="PDAC KRAS prognostic", max_results=5)],
            screen_criteria="PDAC prognostic biomarker, independent cohort preferred",
        )
        task = TaskRepository(session).get(task_id)

        print(f"task: {task.status.value}")
        for step in TaskRepository(session).list_steps(task_id):
            print(f"  {step['type']:<10} {step['status']}")

        claims = ClaimRepository(session).list_claims()
        print(f"\ncandidate claims: {len(claims)}")
        claim_repo = ClaimRepository(session)
        for claim in claims:
            evidences = claim_repo.get_evidence(claim.id)
            print(f"\n[{claim.status.value}] {claim.canonical_signature}")
            for ev in evidences:
                print(f"  [{ev.polarity.value}] {ev.span.section_path} "
                      f"@{ev.span.start_char}-{ev.span.end_char}: {ev.span.text}")
    print("\n✅ offline demo finished")
    return 0


def session_scope_like(factory):
    """极简事务边界（生产用 infrastructure.db.base.session_scope）。"""
    class _Ctx:
        def __enter__(self):
            self.session = factory()
            return self.session

        def __exit__(self, *exc):
            if exc[0] is None:
                self.session.commit()
            else:
                self.session.rollback()
            self.session.close()
            return False
    return _Ctx()


if __name__ == "__main__":
    raise SystemExit(main())
