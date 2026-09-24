"""决策器：LLM 决策（agent-policy prompt）与测试用脚本决策。"""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from pubminer.application.ports import LLMPort, LLMRequest
from pubminer.domain.agents import AgentSession, CoverageSnapshot
from pubminer.agents.policy import DecisionProposal


class _LLMDecision(BaseModel):
    """agent-policy/v1 的 schema 约束输出。"""

    action_type: str
    rationale: str = ""
    expected_information_gain: str = ""
    arguments: dict = Field(default_factory=dict)
    flags_goal_change: bool = False
    flags_conflict: bool = False


class Decision(Protocol):
    def to_proposal(self) -> DecisionProposal: ...


class ActionDecider(Protocol):
    def decide(
        self, session: AgentSession, coverage: CoverageSnapshot
    ) -> DecisionProposal: ...


class ScriptedDecider:
    """测试/回放用：按脚本回放决策序列，最后停留在一项。"""

    def __init__(self, proposals: list[DecisionProposal]) -> None:
        self.proposals = list(proposals)
        self.calls = 0

    def decide(self, session: AgentSession, coverage: CoverageSnapshot) -> DecisionProposal:
        self.calls += 1
        if self.proposals:
            return self.proposals.pop(0)
        return DecisionProposal(action_type="STOP", rationale="script exhausted")


class LLMDecider:
    """用 LLMPort + agent-policy@v1 产生下一动作。"""

    def __init__(self, llm: LLMPort, prompt_registry) -> None:
        self.llm = llm
        self.prompt_registry = prompt_registry

    def decide(self, session: AgentSession, coverage: CoverageSnapshot) -> DecisionProposal:
        prompt = self.prompt_registry.get("agent-policy", "v1")
        user = prompt.render(
            task_spec=session.task_spec.model_dump_json() if session.task_spec else session.goal,
            turn=str(session.turn),
            budget=f"{session.budget_state.turns}/{session.budget.max_turns} turns, "
            f"{session.budget_state.cost_usd}/{session.budget.max_cost_usd} USD",
            coverage=coverage.model_dump_json(exclude={"session_id"}),
        )
        response = self.llm.structured_generate(
            LLMRequest(
                purpose="agent-decide",
                prompt_version="agent-policy@v1",
                system=prompt.system,
                user=user,
                temperature=0.1,
                metadata={"schema_version": prompt.schema_version or ""},
            ),
            _LLMDecision,
        )
        payload = _LLMDecision.model_validate_json(
            response.text[response.text.find("{") : response.text.rfind("}") + 1]
            or response.text
        )
        proposal = DecisionProposal(
            action_type=payload.action_type,
            arguments=payload.arguments,
            rationale=payload.rationale,
            expected_information_gain=payload.expected_information_gain,
            flags_goal_change=payload.flags_goal_change,
            flags_conflict=payload.flags_conflict,
        )
        proposal.validate_type()
        return proposal
