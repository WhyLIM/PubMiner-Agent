"""Agent 会话应用命令：澄清、计划、行动的入口（API 层调用这些，不直接写 ORM）。"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from pubminer.domain.agents import (
    AgentAction,
    AgentMessage,
    AgentSession,
    Budget,
    CoverageSnapshot,
    Plan,
    TaskSpec,
)
from pubminer.infrastructure.db.repositories.agents import AgentSessionRepository


class CreateSessionInput(BaseModel):
    goal: str = Field(min_length=1)
    user_id: str = "anonymous"
    limits: dict = Field(default_factory=dict, description="max_turns/max_articles/max_cost_usd/max_search_runs")


class TaskSpecInput(BaseModel):
    disease: str | None = None
    task: str | None = None
    validation_requirement: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    publication_types: list[str] = Field(default_factory=list)


class AgentSessionService:
    """会话生命周期命令。API 层不接触仓储与 ORM。"""

    def __init__(self, repository: AgentSessionRepository) -> None:
        self.repository = repository

    def create_session(self, data: CreateSessionInput) -> AgentSession:
        agent_session = AgentSession(
            goal=data.goal,
            user_id=data.user_id,
            budget=Budget(**{k: v for k, v in data.limits.items() if k in Budget.model_fields}),
        )
        return self.repository.create(agent_session)

    def post_message(self, session_id: UUID, role: str, content: str, kind: str = "text",
                     payload: dict | None = None) -> AgentMessage:
        """记录一条交互（用户澄清回答 / agent 追问 / 报告）。"""
        message = AgentMessage(
            session_id=session_id, role=role, content=content, kind=kind,  # type: ignore[arg-type]
            payload=payload or {},
        )
        return self.repository.add_message(session_id, message)

    def bind_task_spec(self, session_id: UUID, spec_input: TaskSpecInput, goal_text: str) -> TaskSpec:
        """澄清完成后把 TaskSpec 绑定到会话并落库。"""
        row_spec = TaskSpec(
            goal_text=goal_text,
            disease=spec_input.disease,
            task=spec_input.task,
            validation_requirement=spec_input.validation_requirement,
            year_from=spec_input.year_from,
            year_to=spec_input.year_to,
            publication_types=spec_input.publication_types,
        )
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise LookupError(f"session {session_id} not found")
        agent_session.task_spec = row_spec
        # 直接更新行的 task_spec 字段
        from sqlalchemy import update as sa_update
        from pubminer.infrastructure.db.orm_agents import AgentSessionRow

        self.repository.session.execute(
            sa_update(AgentSessionRow)
            .where(AgentSessionRow.id == session_id)
            .values(task_spec=row_spec.model_dump(mode="json"), updated_at=agent_session.updated_at)
        )
        self.repository.session.flush()
        return row_spec

    def submit_plan(self, session_id: UUID, plan: Plan) -> Plan:
        return self.repository.append_plan(session_id, plan)

    def approve_plan(self, session_id: UUID, plan_version: int) -> None:
        """用户批准当前计划（人批准后才允许进入 RUNNING）。"""
        plan = self.repository.get(session_id)
        if plan is None:
            raise LookupError(f"session {session_id} not found")
        latest = plan.latest_plan
        if latest is None or latest.version != plan_version:
            raise ValueError(f"plan version {plan_version} is not the latest")
        latest.approved_by_human = True
        # 重新落一次（追加不允许；直接 update 该版本的 approved 标记）
        from sqlalchemy import update as sa_update
        from pubminer.infrastructure.db.orm_agents import AgentPlanRow

        self.repository.session.execute(
            sa_update(AgentPlanRow)
            .where(AgentPlanRow.session_id == session_id, AgentPlanRow.version == plan_version)
            .values(approved_by_human=True)
        )
        self.repository.session.flush()

    def record_action(self, session_id: UUID, action: AgentAction) -> None:
        self.repository.record_action(session_id, action)

    def save_coverage(self, session_id: UUID, snapshot: CoverageSnapshot) -> None:
        self.repository.save_coverage(session_id, snapshot)

    def load_for_replay(self, session_id: UUID) -> AgentSession:
        """重放：载入完整会话（消息、计划版本序列、行动序列、预算状态）。"""
        agent_session = self.repository.get(session_id)
        if agent_session is None:
            raise LookupError(f"session {session_id} not found")
        return agent_session
