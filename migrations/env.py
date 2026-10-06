"""Alembic 环境：URL 优先取 PUBMINER_DB_URL；支持离线/在线模式。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 让 alembic 可导入 src/pubminer 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pubminer.infrastructure.db.base import Base  # noqa: E402
from pubminer.infrastructure.db import orm_documents, orm_entities, orm_claims, orm_llm_cache  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if os.environ.get("PUBMINER_DB_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["PUBMINER_DB_URL"])

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=config.get_main_option("sqlalchemy.url", "").startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
