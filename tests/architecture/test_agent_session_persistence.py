"""PR-008 测试：会话/澄清/计划/预算/行动 持久化与重放。"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    import os
    import subprocess
    import sys

    tmpdir = tmp_path_factory.mktemp("agents")
    db = tmpdir / "agents.db"
    env = {
        **os.environ,
        "PUBMINER_DB_URL": f"sqlite:///{db.as_posix()}",
        "PYTHONUTF8": "1",
    }
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


class TestAgentSessionPersistence:
    def test_full_lifecycle_persist_and_replay(self, session_factory):
        from pubminer.domain.agents import (
            AgentAction,
            AgentMessage,
            BudgetDelta,
            CoverageItem,
            CoverageSnapshot,
            Plan,
            PlanStep,
            StopReason,
            StopReasonKind,
        )
        from pubminer.application.commands.agent_session import (
            AgentSessionService,
            CreateSessionInput,
            TaskSpecInput,
        )
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.agents import AgentSessionRepository

        with session_scope(session_factory) as session:
            service = AgentSessionService(AgentSessionRepository(session))
            created = service.create_session(
                CreateSessionInput(
                    goal="寻找 2020 年以来胰腺癌预后 biomarker，并确认独立队列验证",
                    user_id="researcher1",
                    limits={"max_turns": 12, "max_articles": 100},
                )
            )
            sid = created.id

            # 澄清消息 + TaskSpec 绑定
            service.post_message(sid, "user", "寻找胰腺癌预后 biomarker")
            service.post_message(
                sid, "agent", "需要确认：疾病与任务类型？", kind="clarification"
            )
            spec = service.bind_task_spec(
                sid,
                TaskSpecInput(disease="PDAC", task="prognostic_biomarker", year_from=2020),
                goal_text="寻找胰腺癌预后 biomarker",
            )
            assert spec.missing_required_fields() == []

            # 计划 v1 → 用户不批准 → 计划 v2 → 批准
            service.submit_plan(
                sid,
                Plan(version=1, steps=[PlanStep(id="s1", action_type="SEARCH", search_intent="broad discovery")]),
            )
            service.submit_plan(
                sid,
                Plan(
                    version=2,
                    steps=[
                        PlanStep(id="s1", action_type="SEARCH"),
                        PlanStep(id="s2", action_type="EXTRACT"),
                    ],
                    rationale="narrow to survival evidence",
                ),
            )
            service.approve_plan(sid, 2)

            # 行动 + 预算 + 覆盖 + 停止
            action = AgentAction(
                session_id=sid, turn=1, plan_version=2, step_id="s1",
                action_type="SEARCH", tool_name="PubMedSearchTool",
                arguments={"query": "pancreatic cancer prognostic biomarker"},
                expected_information_gain="recall broad set",
                budget_delta=BudgetDelta(turns=1, articles=42, search_runs=1),
                status="succeeded", result_summary="42 pmids",
            )
            service.record_action(sid, action)
            service.save_coverage(
                sid,
                CoverageSnapshot(
                    session_id=sid, turn=1,
                    questions=[CoverageItem(question="key question", support_count=3, covered=False)],
                    support_count=3,
                ),
            )
            service.repository.update_status(
                sid, "COMPLETED", StopReason(kind=StopReasonKind.NORMAL, message="coverage satisfied")
            )

        # —— 新事务重放：完整还原 ——
        with session_scope(session_factory) as session2:
            reloaded = AgentSessionService(
                AgentSessionRepository(session2)
            ).load_for_replay(sid)
            assert reloaded.status.value == "COMPLETED"
            assert reloaded.stop_reason is not None and reloaded.stop_reason.is_normal
            assert reloaded.task_spec is not None
            assert reloaded.task_spec.disease == "PDAC"
            assert reloaded.task_spec.year_from == 2020

            # 消息序列保留（澄清可追溯）：直接查 agent_messages
            from sqlalchemy import select
            from pubminer.infrastructure.db.orm_agents import AgentMessageRow

            message_rows = session2.execute(
                select(AgentMessageRow)
                .where(AgentMessageRow.session_id == sid)
                .order_by(AgentMessageRow.created_at)
            ).scalars().all()
            assert [m.kind for m in message_rows] == ["text", "clarification"]
            assert message_rows[1].role == "agent"

            # 计划版本序列：v1 保留，v2 是当前且被批准
            assert [p.version for p in reloaded.plans] == [1, 2]
            assert reloaded.current_plan_version == 2
            assert reloaded.latest_plan.approved_by_human is True
            assert not reloaded.plans[0].approved_by_human

            # 行动序列与预算增量可重放
            assert len(reloaded.actions) == 1
            replayed = reloaded.actions[0]
            assert replayed.action_type == "SEARCH" and replayed.tool_name == "PubMedSearchTool"
            assert replayed.arguments["query"].startswith("pancreatic")
            assert replayed.budget_delta.articles == 42

            # 会话级预算上限仍为用户设定
            assert reloaded.budget.max_turns == 12 and reloaded.budget.max_articles == 100


class TestReplayOrdering:
    def test_actions_order_by_turn(self, session_factory):
        from pubminer.domain.agents import AgentAction, BudgetDelta
        from pubminer.infrastructure.db.base import session_scope
        from pubminer.infrastructure.db.repositories.agents import AgentSessionRepository

        sid = uuid4()
        with session_scope(session_factory) as session:
            repo = AgentSessionRepository(session)
            from pubminer.domain.agents import AgentSession

            repo.create(AgentSession(goal="g", id=sid))
            for turn in (3, 1, 2):
                repo.record_action(
                    sid,
                    AgentAction(
                        session_id=sid, turn=turn, plan_version=1,
                        action_type="SCREEN", budget_delta=BudgetDelta(turns=1),
                    ),
                )

        with session_scope(session_factory) as session2:
            reloaded = AgentSessionRepository(session2).get(sid)
            assert [a.turn for a in reloaded.actions] == [1, 2, 3]
