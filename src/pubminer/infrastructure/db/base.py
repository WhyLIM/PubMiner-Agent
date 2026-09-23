"""声明式基类与可移植类型（ADR-002：生产 PG，测试 SQLite）。"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator

from sqlalchemy import JSON, create_engine as sa_create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

JSONVariant = JSON().with_variant(postgresql.JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


def create_engine_from_url(url: str, *, echo: bool = False) -> Engine:
    """创建 engine；SQLite 打开外键约束。"""
    engine = sa_create_engine(url, echo=echo, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextlib.contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """事务边界：成功提交，异常回滚。"""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
