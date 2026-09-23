"""API 装配容器：engine、session factory、服务与端口绑定。

测试注入 fake 端口与临时数据库；生产由 main.py 从环境变量装配。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from pubminer.application.commands.agent_session import AgentSessionService
from pubminer.infrastructure.db.base import create_engine_from_url, make_session_factory
from pubminer.infrastructure.db.repositories.agents import AgentSessionRepository
from pubminer.infrastructure.db.repositories.claims import ClaimRepository
from pubminer.infrastructure.db.repositories.workflow import TaskRepository


def default_db_url() -> str:
    return os.environ.get("PUBMINER_DB_URL", "sqlite:///./pubminer_ea.db")


def build_container_from_env(env: dict | None = None) -> tuple[Container, list[str]]:
    """从环境变量装配完整 Agent 运行时（真实端口）。

    必要项：
      - PUBMED_EMAIL            NCBI 礼仪邮箱（检索/水合/resolver）
      - PUBMED_API_KEY          可选，提高限流
      - PUBMINER_LLM_BASE_URL   OpenAI 兼容端点（如 https://open.bigmodel.cn/api/paas/v4）
      - PUBMINER_LLM_API_KEY    LLM 密钥
      - PUBMINER_LLM_MODEL      模型名（默认 glm-4-flash）
    任一缺失时 workflow_ports=None（任务创建返回 503），notes 给出原因。
    """
    env = dict(os.environ if env is None else env)
    notes: list[str] = []
    missing: list[str] = []

    db_url = env.get("PUBMINER_DB_URL", "sqlite:///./pubminer_ea.db")
    email = env.get("PUBMED_EMAIL", "")
    api_key = env.get("PUBMED_API_KEY") or None
    if not email:
        missing.append("PUBMED_EMAIL")
    llm_base = env.get("PUBMINER_LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    llm_key = env.get("PUBMINER_LLM_API_KEY", "")
    llm_model = env.get("PUBMINER_LLM_MODEL", "glm-4-flash")
    if not llm_key:
        missing.append("PUBMINER_LLM_API_KEY")

    ports: Any = None
    if not missing:
        from types import SimpleNamespace

        from pubminer.integrations.adapters import (
            EntrezGeneResolver,
            LlmExtractPort,
            LlmScreenPort,
            LlmVerifyPort,
            PubexHydrateAdapter,
            PubexSearchAdapter,
        )
        from pubminer.integrations.llm import LLMGateway, PromptRegistry
        from pubminer.integrations.llm.providers.openai_compat import OpenAICompatibleProvider
        from pubminer.integrations.loop_runner import LoopRunner
        from pubminer.integrations.tools import ToolRegistry, ToolResult
        from pubex.clients import AsyncPubMedClient, PMCFulltextClient

        loop = LoopRunner()
        pubmed_client = AsyncPubMedClient(email=email, api_key=api_key, tool_name="PubMinerAgent")
        pmc_client = PMCFulltextClient(cache_dir=env.get("PUBMINER_PMC_CACHE", "./download/pmc_cache"))
        prompt_registry = PromptRegistry.discover()

        gateway = LLMGateway(OpenAICompatibleProvider(llm_key, llm_model, base_url=llm_base))
        registry = ToolRegistry()
        from pubminer.integrations.tools import builtin_tool_specs

        for spec in builtin_tool_specs():
            registry.register(
                spec,
                lambda **kwargs: ToolResult(tool_name="bound", ok=True, summary="wired at assembly"),
            )

        ports = SimpleNamespace(
            search=PubexSearchAdapter(pubmed_client, loop),
            hydrate=PubexHydrateAdapter(pubmed_client, pmc_client, loop),
            screen=LlmScreenPort(gateway, prompt_registry),
            extract=LlmExtractPort(gateway, prompt_registry),
            normalize=EntrezGeneResolver(loop, email=email, api_key=api_key),
            verify=LlmVerifyPort(gateway, prompt_registry),
        )
        notes.append(f"real ports wired: LLM={llm_model}, NCBI as {email}")
    else:
        notes.append("missing env: " + ", ".join(missing) + " -- workflow disabled (503)")

    container = build_container(db_url, workflow_ports=ports)
    container.notes = notes  # type: ignore[attr-defined]
    return container, notes


@dataclass
class Container:
    session_factory: sessionmaker
    workflow_ports: Any = None  # MiningPorts；None 时任务创建返回 503
    pipeline_release: str = "mvp-0.1"
    request_counter: int = 0
    notes: list = field(default_factory=list)

    def next_request_id(self) -> str:
        self.request_counter += 1
        return f"req_{self.request_counter:08d}"

    def session_service(self, session: Session) -> AgentSessionService:
        return AgentSessionService(AgentSessionRepository(session))

    def task_repository(self, session: Session) -> TaskRepository:
        return TaskRepository(session)

    def claim_repository(self, session: Session) -> ClaimRepository:
        return ClaimRepository(session)


def build_container(
    db_url: str | None = None,
    *,
    workflow_ports: Any = None,
    pipeline_release: str = "mvp-0.1",
) -> Container:
    engine = create_engine_from_url(db_url or default_db_url())
    return Container(
        session_factory=make_session_factory(engine),
        workflow_ports=workflow_ports,
        pipeline_release=pipeline_release,
    )
