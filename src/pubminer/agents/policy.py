"""行动策略与停止策略（设计文档 §8.1 / ADR-005）。

红线（禁止动作）：任意代码执行、未注册网络请求、猜测 identifier、
修改 approved claim、自动 publish —— 通过动作白名单 + tool registry 授权双重强制。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pubminer.domain.agents import (
    AGENT_ACTION_TYPES,
    AgentSession,
    CoverageSnapshot,
    StopReason,
    StopReasonKind,
)


@dataclass
class DecisionProposal:
    """决策器提出的一个候选行动（尚未过策略门）。"""

    action_type: str
    tool_name: str | None = None
    arguments: dict = field(default_factory=dict)
    rationale: str = ""
    expected_information_gain: str = ""
    step_id: str | None = None
    flags_goal_change: bool = False  # 决策器认为目标需要实质改变 → 必须人工确认
    flags_conflict: bool = False     # 证据冲突无法解析 → 必须人工确认

    def validate_type(self) -> None:
        if self.action_type not in AGENT_ACTION_TYPES:
            raise ValueError(f"unknown action type: {self.action_type}")


class ActionPolicy:
    """策略门：轮次/成本/来源/人工确认。返回放行或受限停止。"""

    #: 触发人工确认的单次成本占预算比例
    COST_CONFIRM_RATIO = 0.25

    def __init__(self, session: AgentSession) -> None:
        self.session = session

    # ---------------------------------------------------------- budget state

    def turns_exhausted(self) -> bool:
        return self.session.budget_state.turns >= self.session.budget.max_turns

    def cost_exhausted(self) -> bool:
        return self.session.budget_state.cost_usd >= self.session.budget.max_cost_usd

    def articles_exhausted(self) -> bool:
        return self.session.budget_state.articles_considered >= self.session.budget.max_articles

    def searches_exhausted(self) -> bool:
        return self.session.budget_state.search_runs >= self.session.budget.max_search_runs

    # ---------------------------------------------------------- gate check

    def check(self, proposal: DecisionProposal) -> DecisionProposal | StopReason:
        """校验候选行动。返回放行的 proposal 或受限 StopReason。

        - 超预算 → 建议受限停止（由 orchestrator 决定是否 STOP）
        - 需要人工确认 → 强制改写为 ASK_HUMAN
        - 动作类型不在白名单 → 拒绝（ValueError 由上层记录为 rejected_by_policy）
        """
        proposal.validate_type()

        if self.turns_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_TURNS, message="max turns reached")
        if self.cost_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_COST, message="max cost reached")
        if self.articles_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_SOURCES, message="max articles reached")
        if self.searches_exhausted() and proposal.action_type == "SEARCH":
            return StopReason(kind=StopReasonKind.LIMIT_SOURCES, message="max search runs reached")

        if self.requires_confirmation(proposal):
            proposal.action_type = "ASK_HUMAN"
            proposal.tool_name = "AskHumanTool"
            proposal.flags_goal_change = proposal.flags_goal_change
        return proposal

    def requires_confirmation(self, proposal: DecisionProposal) -> bool:
        """§8.1 必须请求确认的情形。"""
        if proposal.flags_goal_change:
            return True
        if proposal.flags_conflict:
            return True
        remaining = self.session.budget.max_cost_usd - self.session.budget_state.cost_usd
        estimated = float(proposal.arguments.get("estimated_cost_usd", 0) or 0)
        if remaining > 0 and estimated >= remaining * (1 / (1 + self.COST_CONFIRM_RATIO)):
            return True
        return False


class StopPolicy:
    """停止条件评估（§8.1 正常/受限/失败停止）。"""

    def evaluate(
        self,
        session: AgentSession,
        coverage: CoverageSnapshot,
        *,
        proposal: DecisionProposal | None = None,
    ) -> StopReason | None:
        """返回 StopReason 表示应当停止；None 表示继续。"""
        # 正常停止：关键问题全覆盖 + 无未决缺口 + 决策器提议停止
        if proposal is not None and proposal.action_type == "STOP":
            if all(q.covered for q in coverage.questions) and not coverage.unresolved_gaps:
                return StopReason(kind=StopReasonKind.NORMAL, message="coverage satisfied; marginal gain low")
            return StopReason(
                kind=StopReasonKind.LIMIT_TURNS,
                message="agent proposed stop but coverage gaps remain",
            )

        # 受限停止由 ActionPolicy 的预算检查产出；这里做兜底
        policy = ActionPolicy(session)
        if policy.turns_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_TURNS, message="max turns reached")
        if policy.cost_exhausted():
            return StopReason(kind=StopReasonKind.LIMIT_COST, message="max cost reached")
        if policy.articles_exhausted():
            return StopReason(
                kind=StopReasonKind.LIMIT_SOURCES, message="max articles reached"
            )
        return None
