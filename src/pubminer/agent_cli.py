"""Evidence Agent 命令行入口：`pubminer-agent --goal "..."`。

端到端跑通：会话（澄清/TaskSpec/计划批准）→ 检索 → 水合 → 筛选 → 抽取
→ 归一化 → 验证 → 聚合 → 覆盖矩阵 + 带 span 的证据报告。
"""
from __future__ import annotations

import argparse
import sys

from pubminer.api.deps import build_container_from_env
from pubminer.api.schemas import CreateSessionRequest
from pubminer.application.commands.agent_session import TaskSpecInput
from pubminer.domain.agents import Plan, PlanStep
from pubminer.settings import load_env_file

from pubminer.workflows.domain_schema import load_domain_by_name


def _ensure_schema(session_factory) -> None:
    """开发便利：SQLite 空库时直接建表（生产请用 alembic）。"""
    from sqlalchemy import inspect

    from pubminer.infrastructure.db.base import Base
    from pubminer.infrastructure.db import orm_claims, orm_agents, orm_documents, orm_entities, orm_tasks, orm_llm_cache  # noqa: F401

    engine = session_factory.kw["bind"]
    if not inspect(engine).has_table("documents"):
        Base.metadata.create_all(bind=engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pubminer-agent", description="PubMiner Evidence Agent 命令行")
    parser.add_argument("--goal", required=True, help="自然语言研究目标")
    parser.add_argument("--disease", default="pancreatic cancer", help="疾病（TaskSpec）")
    parser.add_argument("--task", default="prognostic_biomarker")
    parser.add_argument("--year-from", type=int, default=2020)
    parser.add_argument("--max-results", type=int, default=15)
    parser.add_argument("--domain", default=None, help="领域定义名（schemas/domains/ 下的 JSON 名，默认 biomarker）")
    parser.add_argument("--db", default=None, help="覆盖 PUBMINER_DB_URL")
    args = parser.parse_args(argv)

    loaded = load_env_file()
    if loaded:
        print(f"[agent] loaded {loaded} vars from .env")
    if args.db:
        import os

        os.environ["PUBMINER_DB_URL"] = args.db

    from pubminer.workflows import MiningWorkflow, SearchIntent
    from pubminer.workflows.verification import CrossPaperVerifier

    container, notes = build_container_from_env()
    for note in notes:
        print(f"[agent] {note}")
    if container.workflow_ports is None:
        print("[agent] 运行时未配置完整（见上），无法执行检索任务。", file=sys.stderr)
        return 2

    from pubminer.infrastructure.db.base import session_scope

    with session_scope(container.session_factory) as session:
        _ensure_schema(container.session_factory)

        service = container.session_service(session)
        created = service.create_session(CreateSessionRequest(goal=args.goal, user_id="cli"))
        sid = created.id
        service.post_message(sid, "user", args.goal)
        service.bind_task_spec(
            sid,
            TaskSpecInput(disease=args.disease, task=args.task, year_from=args.year_from),
            goal_text=args.goal,
        )
        plan = service.submit_plan(
            sid,
            Plan(
                version=1,
                rationale="discovery → survival evidence → independent validation",
                steps=[
                    PlanStep(id="s1", action_type="SEARCH"),
                    PlanStep(id="s2", action_type="EXTRACT"),
                ],
            ),
        )
        service.approve_plan(sid, plan.version)

        criteria = f"{args.disease} / {args.task} / independent cohort validation preferred"
        workflow = MiningWorkflow(
            container.workflow_ports,
            document_repo_factory=_repo("documents"),
            claim_repo_factory=_repo("claims"),
            entity_repo_factory=_repo("entities"),
            task_repo=container.task_repository(session),
            domain=(load_domain_by_name(args.domain) if args.domain else None),
            pipeline_release=f"cli-{args.task}",
        )
        task_id = workflow.start(
            session_id=sid,
            intents=[SearchIntent(name="discovery", query=f"{args.disease} {args.task.replace('_', ' ')} biomarker", max_results=args.max_results)],
            screen_criteria=criteria,
            domain=(args.domain),
        )
        task = container.task_repository(session).get(task_id)
        print(f"[agent] task {task_id} -> {task.status.value if task else 'CREATED'}")

        verifier = CrossPaperVerifier(container.claim_repository(session))
        coverage = verifier.coverage_snapshot(session, sid)
        print("\n=== Coverage ===")
        print(f"support={coverage.support_count} contradict={coverage.contradict_count} "
              f"no_effect={coverage.no_effect_count} independent_validation={coverage.independent_validation_found}")
        for gap in coverage.unresolved_gaps:
            print(f"  gap: {gap}")

        claims = container.claim_repository(session).list_claims(limit=20)
        print(f"\n=== Candidate claims ({len(claims)}) ===")
        for claim in claims:
            evidences = container.claim_repository(session).get_evidence(claim.id)
            print(f"\n[{claim.status.value}] {claim.canonical_signature}")
            for ev in evidences[:3]:
                print(f"  - {ev.polarity.value}: “{ev.span.text[:120]}”"
                      f" ({ev.span.section_path} @{ev.span.start_char}-{ev.span.end_char})")
    return 0


def _repo(name: str):
    from pubminer.infrastructure.db.repositories.claims import ClaimRepository
    from pubminer.infrastructure.db.repositories.documents import DocumentRepository
    from pubminer.infrastructure.db.repositories.entities import EntityRepository

    mapping = {
        "documents": DocumentRepository,
        "claims": ClaimRepository,
        "entities": EntityRepository,
    }
    return mapping[name]


if __name__ == "__main__":
    raise SystemExit(main())
