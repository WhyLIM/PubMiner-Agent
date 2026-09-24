"""Task 仓储：workflow 状态机持久化与恢复。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pubminer.domain.tasks import Task
from pubminer.infrastructure.db.orm_tasks import RunStepRow, TaskRow


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:  # noqa: A003 — 供 workflow 装配层复用同一事务
        return self._session

    def create(self, task: Task) -> Task:
        self.session.add(
            TaskRow(
                id=task.id,
                session_id=task.session_id,
                kind=task.kind,
                request=task.request,
                status=task.status.value,
                priority=task.priority,
                owner=task.owner,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
        )
        self.session.flush()
        return task

    def get(self, task_id: UUID) -> Task | None:
        row = self.session.get(TaskRow, task_id)
        if row is None:
            return None
        return Task(
            id=row.id,
            session_id=row.session_id,
            kind=row.kind,
            request=row.request or {},
            status=row.status,
            priority=row.priority,
            owner=row.owner,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def update_status(self, task_id: UUID, status) -> None:
        row = self.session.get(TaskRow, task_id)
        if row is None:
            raise LookupError(f"task {task_id} not found")
        row.status = status.value if hasattr(status, "value") else str(status)
        row.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    # ------------------------------------------------------------------ steps

    def set_step(self, task_id: UUID, index: int, step_type: str, status: str) -> None:
        row = self._get_or_create_step(task_id, index, step_type)
        row.status = status
        row.started_at = datetime.now(timezone.utc)
        self.session.flush()

    def succeed_step(self, task_id: UUID, index: int, output: dict) -> None:
        row = self._get_step(task_id, index)
        if row is None:
            raise LookupError(f"step {index} of task {task_id} not found")
        row.status = "SUCCEEDED"
        row.output_summary = output
        row.ended_at = datetime.now(timezone.utc)
        self.session.flush()

    def fail_step(self, task_id: UUID, index: int, error: str, *, retryable: bool) -> None:
        row = self._get_step(task_id, index)
        if row is None:
            raise LookupError(f"step {index} of task {task_id} not found")
        row.status = "FAILED_RETRYABLE" if retryable else "FAILED_FINAL"
        row.error = error
        row.ended_at = datetime.now(timezone.utc)
        self.session.flush()

    def step_output(self, task_id: UUID, index: int) -> dict | None:
        row = self._get_step(task_id, index)
        if row is None or row.status != "SUCCEEDED":
            return None
        return dict(row.output_summary or {})

    def first_failed_step_index(self, task_id: UUID) -> int | None:
        """返回第一个需要（重）执行的步骤下标；全部完成时返回 None。"""
        rows = self.session.execute(
            select(RunStepRow)
            .where(RunStepRow.task_id == task_id)
            .order_by(RunStepRow.step_index)
        ).scalars().all()
        for row in rows:
            if row.status in ("FAILED_RETRYABLE", "FAILED_FINAL", "RUNNING", "PENDING"):
                return row.step_index
        return None

    def list_steps(self, task_id: UUID) -> list[dict]:
        rows = self.session.execute(
            select(RunStepRow)
            .where(RunStepRow.task_id == task_id)
            .order_by(RunStepRow.step_index)
        ).scalars().all()
        return [
            {
                "index": r.step_index,
                "type": r.step_type,
                "status": r.status,
                "error": r.error,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ helpers

    def _get_step(self, task_id: UUID, index: int) -> RunStepRow | None:
        return self.session.execute(
            select(RunStepRow).where(
                RunStepRow.task_id == task_id, RunStepRow.step_index == index
            )
        ).scalar_one_or_none()

    def _get_or_create_step(self, task_id: UUID, index: int, step_type: str) -> RunStepRow:
        row = self._get_step(task_id, index)
        if row is None:
            row = RunStepRow(id=uuid.uuid4(), task_id=task_id, step_index=index, step_type=step_type)
            self.session.add(row)
            self.session.flush()
        return row
