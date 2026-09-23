"""有界 Evidence Agent Orchestrator（ADR-005）。

有界循环：OBSERVE → DECIDE → POLICY GATE → EXECUTE → RECORD。
- 决策器（LLM 或脚本）只产生候选行动；
- ActionPolicy 强制动作白名单/预算/人工确认；
- 执行通过注入的 executor（PR-010 绑定 workflow commands）；
- 每步通过 recorder 持久化（PR-008 的 repository/service）。
"""
from __future__ import annotations

import logging
from typing import Protocol

from pubminer.application.ports import ToolExecutionResult
from pubminer.agents.coverage import CoverageEvaluator
from pubminer.agents.decider import ActionDecider, DecisionProposal
from pubminer.agents.policy import ActionPolicy, StopPolicy
from pubminer.domain.agents import (
    AgentAction,
    AgentSession,
    AgentStatus,
    BudgetDelta,
    CoverageSnapshot,
    StopReason,
    StopReasonKind,
)

logger = logging.getLogger("pubminer.agent")


class ActionExecutor(Protocol):
    """执行注入：orchestrator 不直接碰网络/DB/工具实现。"""

    def execute(
        self, session: AgentSession, proposal: DecisionProposal
    ) -> tuple[ToolExecutionResult, BudgetDelta, CoverageSnapshot]:
        """执行候选行动，返回 (结果, 预算增量, 新覆盖快照)。"""
        ...


class SessionRecorder(Protocol):
    """持久化注入（对应 infrastructure 的 AgentSessionRepository）。"""

    def record_action(self, session_id, action: AgentAction) -> None: ...

    def save_coverage(self, session_id, snapshot: CoverageSnapshot) -> None: ...

    def save_budget_state(self, session_id, budget_state) -> None: ...

    def update_status(self, session_id, status: str, stop_reason: StopReason | None = None) -> None: ...


class BoundedEvidenceAgent:
    """单 Agent、有界循环；每个 run 至多 max_iterations 个决策步。"""

    def __init__(
        self,
        session: AgentSession,
        *,
        decider: ActionDecider,
        executor: ActionExecutor,
        recorder: SessionRecorder | None = None,
        coverage_evaluator: CoverageEvaluator | None = None,
        initial_coverage: CoverageSnapshot | None = None,
    ) -> None:
        self.session = session
        self.decider = decider
        self.executor = executor
        self.recorder = recorder
        self.coverage = initial_coverage or CoverageEvaluator().snapshot(
            session.id, session.turn, []
        )
        self.stop_reason: StopReason | None = None

    # ------------------------------------------------------------------ loop

    def run(self, *, max_iterations: int = 100) -> AgentSession:
        """运行有界循环直至停止条件；返回最终会话状态。"""
        iterations = 0
        while self.stop_reason is None and iterations < max_iterations:
            iterations += 1
            if not self.step():
                break
        if self.stop_reason is None:
            self._stop(StopReasonKind.LIMIT_TURNS, "orchestrator max_iterations guard hit")
        return self.session

    def step(self) -> bool:
        """执行一轮；返回 False 表示循环终止。"""
        policy = ActionPolicy(self.session)

        # 1. 预算前置检查（受限停止）
        stop = self._budget_stop(policy)
        if stop is not None:
            self._stop(stop.kind.value, stop.message)
            return False

        # 2. 决策
        try:
            proposal = self.decider.decide(self.session, self.coverage)
        except Exception as exc:
            logger.error("decider failed: %s", exc)
            self._stop(StopReasonKind.SOURCE_UNAVAILABLE, f"decider failed: {exc}")
            return False

        # 3. 策略门（未知动作类型在此显式失败，而不是静默执行）
        try:
            checked = policy.check(proposal)
        except ValueError as exc:
            # 领域枚举无法表达非法动作类型，审计走日志 + PERMISSION_DENIED 停止
            logger.error("policy rejected %r: %s", proposal.action_type, exc)
            self._stop(StopReasonKind.PERMISSION_DENIED, f"policy rejected action: {exc}")
            return False
        if isinstance(checked, StopReason):
            self._stop(checked.kind.value, checked.message)
            return False
        proposal = checked

        # 4. 决策器显式停止（覆盖判定决定 NORMAL 还是 gap 未消的受限停止）
        if proposal.action_type == "STOP":
            self._execute_record_only(proposal)
            stop = StopPolicy().evaluate(self.session, self.coverage, proposal=proposal)
            if stop is None:
                stop = StopReason(kind=StopReasonKind.NORMAL, message="stopped by decider")
            self._stop(stop.kind.value, stop.message)
            return False

        # 5. 执行 + 记录（ASK_HUMAN 走 WAITING_HUMAN 终止）
        return self._execute(proposal, waiting=proposal.action_type == "ASK_HUMAN")

    # ------------------------------------------------------------------ internals

    def _execute(self, proposal: DecisionProposal, *, waiting: bool) -> bool:
        action = AgentAction(
            session_id=self.session.id,
            turn=self.session.budget_state.turns + 1,
            plan_version=self.session.current_plan_version or 1,
            step_id=proposal.step_id,
            action_type=proposal.action_type,
            tool_name=proposal.tool_name,
            arguments=proposal.arguments,
            expected_information_gain=proposal.expected_information_gain,
            budget_delta=BudgetDelta(),
            status="pending",
        )
        try:
            result, delta, coverage = self.executor.execute(self.session, proposal)
        except Exception as exc:
            action.status = "failed"
            action.error = str(exc)
            self._record(action)
            self._stop(StopReasonKind.SOURCE_UNAVAILABLE, f"executor failed: {exc}")
            return False

        action.result_summary = result.summary
        action.budget_delta = delta
        action.status = "succeeded" if result.ok else "failed"
        self._record(action)

        self.session.budget_state.add(delta)
        self.coverage = coverage
        self._recorder_save_coverage()

        if not result.ok:
            self._stop(StopReasonKind.SOURCE_UNAVAILABLE, result.error or "executor failure")
            return False

        if waiting:
            self._stop(
                StopReasonKind.AWAITING_HUMAN,
                proposal.rationale or "human confirmation required",
            )
            return False

        self.session.turn = action.turn
        return True

    def _execute_record_only(self, proposal: DecisionProposal) -> None:
        action = AgentAction(
            session_id=self.session.id,
            turn=self.session.budget_state.turns + 1,
            plan_version=self.session.current_plan_version or 1,
            step_id=proposal.step_id,
            action_type="STOP",
            arguments=proposal.arguments,
            expected_information_gain=proposal.expected_information_gain,
            status="succeeded",
            result_summary=proposal.rationale,
        )
        self._record(action)
        self.session.budget_state.add(BudgetDelta(turns=1))

    def _budget_stop(self, policy: ActionPolicy) -> StopReason | None:
        if policy.turns_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_TURNS, message="max turns reached")
        if policy.cost_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_COST, message="max cost reached")
        if policy.articles_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_SOURCES, message="max articles reached")
        return None

    def _record(self, action: AgentAction) -> None:
        self.session.actions.append(action)
        if self.recorder is not None:
            self.recorder.record_action(self.session.id, action)

    def _recorder_save_coverage(self) -> None:
        if self.recorder is not None:
            self.recorder.save_coverage(self.session.id, self.coverage)
            self.recorder.save_budget_state(self.session.id, self.session.budget_state)

    def _stop(self, kind: str | StopReasonKind, message: str) -> None:
        reason = StopReason(
            kind=StopReasonKind(kind),
            message=message,
        )
        self.stop_reason = reason
        if reason.kind == StopReasonKind.NORMAL:
            self.session.status = AgentStatus.COMPLETED
        elif reason.kind == StopReasonKind.AWAITING_HUMAN:
            self.session.status = AgentStatus.WAITING_HUMAN
        elif reason.is_limited:
            self.session.status = AgentStatus.LIMITED
        else:
            self.session.status = AgentStatus.FAILED
        self.session.stop_reason = reason
        if self.recorder is not None:
            self.recorder.update_status(self.session.id, self.session.status.value, reason)
