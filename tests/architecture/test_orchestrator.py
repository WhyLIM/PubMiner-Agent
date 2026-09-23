"""PR-009 测试：有界 orchestrator —— 白名单、预算、人工确认、停止原因。

全部使用 ScriptedDecider + fake executor，不触网、不依赖 LLM。
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from pubminer.agents import (
    BoundedEvidenceAgent,
    CoverageEvaluator,
    DecisionProposal,
    LLMDecider,
    ScriptedDecider,
    StopPolicy,
)
from pubminer.domain.agents import (
    AgentSession,
    Budget,
    BudgetDelta,
    BudgetState,
    CoverageItem,
    CoverageSnapshot,
    StopReasonKind,
    TaskSpec,
)
from pubminer.domain.evidence import Evidence, EvidencePolarity
from pubminer.application.ports import ToolExecutionResult

REPO_ROOT = Path(__file__).resolve().parents[2]


def _session(**budget) -> AgentSession:
    defaults = {"max_turns": 10, "max_articles": 100, "max_cost_usd": 5.0, "max_search_runs": 10}
    defaults.update(budget)
    return AgentSession(goal="PDAC prognostic biomarkers", budget=Budget(**defaults))


def _coverage(*, covered=True, session_id=None, turn=0, support=2) -> CoverageSnapshot:
    return CoverageSnapshot(
        session_id=session_id or uuid4(),
        turn=turn,
        questions=[CoverageItem(question="q", support_count=support, covered=covered)],
        support_count=support,
    )


class FakeExecutor:
    """回放预设执行结果。"""

    def __init__(self, results: list[tuple[bool, str, BudgetDelta, CoverageSnapshot]] | None = None):
        self.results = results or []
        self.calls: list[str] = []

    def execute(self, session, proposal):
        self.calls.append(proposal.action_type)
        if self.results:
            ok, summary, delta, coverage = self.results.pop(0)
        else:
            ok, summary, delta, coverage = (
                True, "ok", BudgetDelta(turns=1), _coverage(session_id=session.id),
            )
        return ToolExecutionResult(tool_name=proposal.tool_name or proposal.action_type, ok=ok, summary=summary), delta, coverage


class MemoryRecorder:
    def __init__(self):
        self.actions = []
        self.statuses = []
        self.coverages = []

    def record_action(self, session_id, action):
        self.actions.append(action)

    def save_coverage(self, session_id, snapshot):
        self.coverages.append(snapshot)

    def save_budget_state(self, session_id, budget_state):
        pass

    def update_status(self, session_id, status, stop_reason=None):
        self.statuses.append((status, stop_reason))


class TestAllowedActions:
    def test_agent_runs_scripted_actions_in_order(self):
        session = _session()
        decider = ScriptedDecider([
            DecisionProposal(action_type="SEARCH", tool_name="PubMedSearchTool", step_id="s1",
                             arguments={"query": "pdac biomarker"}),
            DecisionProposal(action_type="EXTRACT", tool_name="ExtractionTool", step_id="s2"),
        ])
        executor = FakeExecutor()
        agent = BoundedEvidenceAgent(session, decider=decider, executor=executor)
        result = agent.run()

        # STOP 由 orchestrator 直接记录（不走 executor），只执行前两个动作
        assert executor.calls == ["SEARCH", "EXTRACT"]
        assert result.stop_reason.kind == StopReasonKind.NORMAL
        assert result.status.value == "COMPLETED"
        # 每个 action 绑定 plan 版本并带理由
        assert all(a.plan_version >= 1 for a in result.actions)

    def test_unknown_action_type_is_hard_denied(self):
        session = _session()
        decider = ScriptedDecider([DecisionProposal(action_type="EXECUTE_SQL")])
        agent = BoundedEvidenceAgent(
            session, decider=decider, executor=FakeExecutor(),
        )
        result = agent.run()
        assert result.stop_reason.kind == StopReasonKind.PERMISSION_DENIED
        assert result.status.value == "FAILED"
        assert result.actions == []  # 非法行动绝不产生已执行 action


class TestBudgetStops:
    def test_turn_limit_stops_with_explicit_reason(self):
        session = _session(max_turns=2)
        script = [DecisionProposal(action_type="SEARCH"), DecisionProposal(action_type="SCREEN"),
                  DecisionProposal(action_type="EXTRACT")]
        executor = FakeExecutor()
        agent = BoundedEvidenceAgent(session, decider=ScriptedDecider(script), executor=executor)
        result = agent.run()

        assert result.stop_reason.kind == StopReasonKind.LIMIT_TURNS
        assert result.status.value == "LIMITED"
        assert executor.calls == ["SEARCH", "SCREEN"]  # 第三次不再执行
        assert result.budget_state.turns == 2

    def test_cost_limit_stops(self):
        session = _session(max_cost_usd=1.0)
        executor = FakeExecutor(results=[(
            True, "costly", BudgetDelta(turns=1, cost_usd=1.5), _coverage(session_id=session.id),
        )])
        agent = BoundedEvidenceAgent(
            session,
            decider=ScriptedDecider([DecisionProposal(action_type="HYDRATE")]),
            executor=executor,
        )
        result = agent.run()
        assert result.stop_reason.kind == StopReasonKind.LIMIT_COST
        assert result.status.value == "LIMITED"

    def test_article_limit_stops(self):
        session = _session(max_articles=10)
        executor = FakeExecutor(results=[(
            True, "42 articles", BudgetDelta(turns=1, articles=50), _coverage(session_id=session.id),
        )])
        agent = BoundedEvidenceAgent(
            session,
            decider=ScriptedDecider([DecisionProposal(action_type="SEARCH")]),
            executor=executor,
        )
        result = agent.run()
        assert result.stop_reason.kind == StopReasonKind.LIMIT_SOURCES


class TestHumanConfirmation:
    def test_goal_change_forces_ask_human_and_pause(self):
        session = _session()
        decider = ScriptedDecider([
            DecisionProposal(action_type="SYNTHESIZE", flags_goal_change=True, rationale="goal shift"),
        ])
        agent = BoundedEvidenceAgent(session, decider=decider, executor=FakeExecutor())
        result = agent.run()

        assert result.stop_reason.kind == StopReasonKind.AWAITING_HUMAN
        assert result.status.value == "WAITING_HUMAN"
        # 最后一个 action 是被策略改写后的 ASK_HUMAN
        assert result.actions[-1].action_type == "ASK_HUMAN"

    def test_conflict_forces_ask_human(self):
        session = _session()
        decider = ScriptedDecider([
            DecisionProposal(action_type="SYNTHESIZE", flags_conflict=True),
        ])
        agent = BoundedEvidenceAgent(session, decider=decider, executor=FakeExecutor())
        result = agent.run()
        assert result.stop_reason.kind == StopReasonKind.AWAITING_HUMAN


class TestStopReasons:
    def test_normal_stop_requires_full_coverage(self):
        session = _session()
        agent = BoundedEvidenceAgent(
            session,
            decider=ScriptedDecider([DecisionProposal(action_type="STOP", rationale="done")]),
            executor=FakeExecutor(),
            initial_coverage=_coverage(covered=True),
        )
        result = agent.run()
        assert result.stop_reason.kind == StopReasonKind.NORMAL
        assert result.stop_reason.is_normal

    def test_stop_with_gaps_becomes_reported_limit(self):
        session = _session()
        agent = BoundedEvidenceAgent(
            session,
            decider=ScriptedDecider([DecisionProposal(action_type="STOP")]),
            executor=FakeExecutor(),
            initial_coverage=_coverage(covered=False, support=0),
        )
        result = agent.run()
        # 提前停止但覆盖有缺口 → 明确报告为受限，不允许伪装成 NORMAL
        assert result.stop_reason.kind == StopReasonKind.LIMIT_TURNS
        assert "gaps remain" in result.stop_reason.message

    def test_executor_failure_stops_with_reason(self):
        session = _session()
        executor = FakeExecutor(results=[(False, "ncbi down", BudgetDelta(), _coverage(session_id=session.id))])
        agent = BoundedEvidenceAgent(
            session,
            decider=ScriptedDecider([DecisionProposal(action_type="SEARCH")]),
            executor=executor,
        )
        result = agent.run()
        assert result.status.value == "FAILED"
        assert result.actions[-1].status == "failed"

    def test_unrecoverable_decider_failure(self):
        class ExplodingDecider:
            def decide(self, session, coverage):
                raise RuntimeError("provider exploded")

        session = _session()
        agent = BoundedEvidenceAgent(session, decider=ExplodingDecider(), executor=FakeExecutor())
        result = agent.run()
        assert result.status.value == "FAILED"
        assert result.stop_reason.kind == StopReasonKind.SOURCE_UNAVAILABLE


class TestRecorderPersistence:
    def test_actions_and_status_recorded(self):
        session = _session()
        recorder = MemoryRecorder()
        agent = BoundedEvidenceAgent(
            session,
            decider=ScriptedDecider([DecisionProposal(action_type="SEARCH")]),
            executor=FakeExecutor(),
            recorder=recorder,
        )
        agent.run()
        assert len(recorder.actions) == 2  # SEARCH + STOP
        assert recorder.statuses[-1][0] == "COMPLETED"
        assert recorder.coverages  # coverage 快照已保存


class TestLLMDeciderContract:
    def test_llm_decider_with_fake_provider(self):
        import json

        from pubminer.application.ports import LLMRequest
        from pubminer.integrations.llm import FakeLLMProvider, LLMGateway, PromptRegistry

        payload = json.dumps({
            "action_type": "EXPAND_QUERY",
            "rationale": "recall marginal",
            "expected_information_gain": "independent validation cohort",
            "arguments": {"query": "pdac validation cohort"},
        })
        llm = LLMGateway(FakeLLMProvider(responder=lambda s, u, t: (payload, 10, 10)))
        decider = LLMDecider(llm, PromptRegistry(REPO_ROOT / "prompts"))

        session = _session()
        session.task_spec = TaskSpec(goal_text="g", disease="PDAC", task="prognostic_biomarker")
        proposal = decider.decide(session, _coverage(session_id=session.id))
        assert proposal.action_type == "EXPAND_QUERY"
        assert proposal.arguments["query"] == "pdac validation cohort"

    def test_llm_decider_rejects_unknown_action(self):
        import json

        from pubminer.integrations.llm import FakeLLMProvider, LLMGateway, PromptRegistry

        payload = json.dumps({"action_type": "DEPLOY_MODEL"})
        llm = LLMGateway(FakeLLMProvider(responder=lambda s, u, t: (payload, 5, 5)))
        decider = LLMDecider(llm, PromptRegistry(REPO_ROOT / "prompts"))
        with pytest.raises(ValueError, match="unknown action type"):
            decider.decide(_session(), _coverage())
