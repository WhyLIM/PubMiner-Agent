"""AgentSession 仓储：会话/澄清/计划/预算/行动/覆盖 持久化与重放。"""
from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy.orm import Session

from pubminer.domain.agents import (
    AgentAction,
    AgentMessage,
    AgentSession,
    Budget,
    BudgetDelta,
    BudgetState,
    CoverageSnapshot,
    Plan,
    PlanStep,
    StopReason,
    StopReasonKind,
    TaskSpec,
)
from pubminer.infrastructure.db.orm_agents import (
    AgentActionRow,
    AgentMessageRow,
    AgentPlanRow,
    AgentSessionRow,
    CoverageSnapshotRow,
)


class AgentSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, agent_session: AgentSession) -> AgentSession:
        row = AgentSessionRow(
            id=agent_session.id,
            user_id=agent_session.user_id,
            goal=agent_session.goal,
            status=agent_session.status.value,
            task_spec=agent_session.task_spec.model_dump(mode="json") if agent_session.task_spec else None,
            budget=agent_session.budget.model_dump(mode="json"),
            budget_state=agent_session.budget_state.model_dump(mode="json"),
            current_plan_version=agent_session.current_plan_version,
            turn=agent_session.turn,
            created_at=agent_session.created_at,
            updated_at=agent_session.updated_at,
        )
        self.session.add(row)
        self.session.flush()
        return self.get(row.id)  # type: ignore[return-value]

    def get(self, session_id: UUID) -> AgentSession | None:
        row = self.session.get(AgentSessionRow, session_id)
        return self._to_domain(row) if row else None

    def add_message(self, session_id: UUID, message: AgentMessage) -> AgentMessage:
        self._require(session_id)
        self.session.add(
            AgentMessageRow(
                id=message.id,
                session_id=session_id,
                role=message.role,
                kind=message.kind,
                content=message.content,
                payload=message.payload,
                created_at=message.created_at,
            )
        )
        self.session.flush()
        return message

    def append_plan(self, session_id: UUID, plan: Plan) -> Plan:
        """追加新计划版本（不覆盖旧版本），并前移 current_plan_version。"""
        self._require(session_id)
        self.session.add(
            AgentPlanRow(
                id=uuid.uuid4(),
                session_id=session_id,
                version=plan.version,
                rationale=plan.rationale,
                steps=[s.model_dump(mode="json") for s in plan.steps],
                approved_by_human=plan.approved_by_human,
                created_at=plan.created_at,
            )
        )
        row = self.session.get(AgentSessionRow, session_id)
        row.current_plan_version = plan.version  # type: ignore[union-attr]
        row.status = "PLANNED"  # type: ignore[assignment]
        self.session.flush()
        return plan

    def record_action(self, session_id: UUID, action: AgentAction) -> AgentAction:
        self._require(session_id)
        self.session.add(
            AgentActionRow(
                id=action.id,
                session_id=session_id,
                turn=action.turn,
                plan_version=action.plan_version,
                step_id=action.step_id,
                action_type=action.action_type,
                tool_name=action.tool_name,
                arguments=action.arguments,
                expected_information_gain=action.expected_information_gain,
                result_summary=action.result_summary,
                budget_delta=action.budget_delta.model_dump(mode="json"),
                status=action.status,
                error=action.error,
                created_at=action.created_at,
            )
        )
        row = self.session.get(AgentSessionRow, session_id)
        row.turn = max(row.turn or 0, action.turn)  # type: ignore[union-attr]
        row.updated_at = action.created_at  # type: ignore[assignment]
        self.session.flush()
        return action

    def save_coverage(self, session_id: UUID, snapshot: CoverageSnapshot) -> CoverageSnapshot:
        self._require(session_id)
        self.session.add(
            CoverageSnapshotRow(
                id=uuid.uuid4(),
                session_id=session_id,
                turn=snapshot.turn,
                snapshot=snapshot.model_dump(mode="json"),
            )
        )
        self.session.flush()
        return snapshot

    def update_status(self, session_id: UUID, status: str, stop_reason: StopReason | None = None) -> None:
        row = self._require(session_id)
        row.status = status  # type: ignore[assignment]
        if stop_reason is not None:
            row.stop_reason = stop_reason.model_dump(mode="json")  # type: ignore[assignment]
        self.session.flush()

    def save_budget_state(self, session_id: UUID, budget_state: BudgetState) -> None:
        row = self._require(session_id)
        row.budget_state = budget_state.model_dump(mode="json")  # type: ignore[assignment]
        self.session.flush()

    # ---------------------------------------------------------------- replay

    def _require(self, session_id: UUID) -> AgentSessionRow:
        row = self.session.get(AgentSessionRow, session_id)
        if row is None:
            raise LookupError(f"agent session {session_id} not found")
        return row

    def _to_domain(self, row: AgentSessionRow) -> AgentSession:
        from pubminer.domain.agents import AgentStatus

        return AgentSession(
            id=row.id,
            user_id=row.user_id,
            goal=row.goal,
            task_spec=TaskSpec.model_validate(row.task_spec) if row.task_spec else None,
            status=AgentStatus(row.status),
            budget=Budget.model_validate(row.budget or {}),
            budget_state=BudgetState.model_validate(row.budget_state or {}),
            plans=[
                Plan(
                    version=p.version,
                    rationale=p.rationale,
                    steps=[PlanStep.model_validate(s) for s in (p.steps or [])],
                    approved_by_human=p.approved_by_human,
                    created_at=p.created_at,
                )
                for p in row.plans
            ],
            actions=[
                AgentAction(
                    id=a.id,
                    session_id=row.id,
                    turn=a.turn,
                    plan_version=a.plan_version,
                    step_id=a.step_id,
                    action_type=a.action_type,
                    tool_name=a.tool_name,
                    arguments=a.arguments or {},
                    expected_information_gain=a.expected_information_gain,
                    result_summary=a.result_summary,
                    budget_delta=BudgetDelta.model_validate(a.budget_delta or {}),
                    status=a.status,
                    error=a.error,
                    created_at=a.created_at,
                )
                for a in row.actions
            ],
            stop_reason=(
                StopReason(
                    kind=StopReasonKind((row.stop_reason or {}).get("kind", "NORMAL")),
                    message=(row.stop_reason or {}).get("message", ""),
                )
                if row.stop_reason
                else None
            ),
            current_plan_version=row.current_plan_version,
            turn=row.turn,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

