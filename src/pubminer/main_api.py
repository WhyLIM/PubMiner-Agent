"""Evidence Agent API 启动入口：`pubminer-api` 或 `python -m pubminer.main_api`。"""
from __future__ import annotations

import os

from pubminer.settings import load_env_file


def create_default_app():
    from pubminer.api.app import create_app
    from pubminer.api.deps import build_container_from_env

    container, notes = build_container_from_env()
    for note in notes:
        print(f"[pubminer] {note}")
    return create_app(container), container


def _ensure_missing_tables(engine) -> None:
    """开发便利：补建 ORM 中缺失的表（checkfirst，不改动已有表/数据）。

    生产库请用 alembic 迁移管理；此处只兜底 create_all 早期建库后
    新增迁移表被 stamp 跳过的情形（如 resolution_cache / reviews / llm_cache）。
    """
    from sqlalchemy import inspect

    from pubminer.infrastructure.db.base import Base
    from pubminer.infrastructure.db import orm_documents, orm_entities, orm_claims, orm_agents, orm_tasks, orm_cache, orm_reviews, orm_llm_cache  # noqa: F401

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = set(Base.metadata.tables) - existing
    if missing:
        Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables[t] for t in missing])
        print(f"[pubminer] created missing tables: {sorted(missing)}")


def _recover_orphaned_runs(container) -> None:
    """进程启动时回收孤儿任务：上次运行中被重启/崩溃中断的任务统一标 FAILED，
    步骤转 FAILED_RETRYABLE——「恢复/重跑管线」按钮由此可用，否则任务永远挂在执行中。"""
    from pubminer.infrastructure.db.base import session_scope
    from pubminer.infrastructure.db.repositories.workflow import TaskRepository

    try:
        with session_scope(container.session_factory) as session:
            n = TaskRepository(session).fail_orphaned_runs()
        if n:
            print(f"[pubminer] recovered {n} orphaned running task(s) -> FAILED (resumable)")
    except Exception as exc:  # 启动兜底：回收失败不阻断服务
        print(f"[pubminer] orphan recovery skipped: {exc}")


def main() -> None:
    loaded = load_env_file()
    if loaded:
        print(f"[pubminer] loaded {loaded} vars from .env")
    import uvicorn

    app, container = create_default_app()
    _ensure_missing_tables(container.session_factory.kw["bind"])
    _recover_orphaned_runs(container)

    uvicorn.run(app, host=os.environ.get("PUBMINER_HOST", "127.0.0.1"), port=int(os.environ.get("PUBMINER_PORT", "8001")))


if __name__ == "__main__":
    main()
