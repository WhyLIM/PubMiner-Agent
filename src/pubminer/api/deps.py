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
    llm_vendor = env.get("PUBMINER_LLM_VENDOR", "zhipu")
    llm_base_override = env.get("PUBMINER_LLM_BASE_URL") or None
    llm_key = env.get("PUBMINER_LLM_API_KEY", "")
    llm_model = env.get("PUBMINER_LLM_MODEL") or None  # 未填时用厂商默认模型
    llm_protocol = env.get("PUBMINER_LLM_PROTOCOL", "auto")
    llm_thinking = env.get("PUBMINER_LLM_THINKING", "default")
    llm_thinking_budget = int(env.get("PUBMINER_LLM_THINKING_BUDGET", "4096") or 4096)
    if not llm_key:
        missing.append("PUBMINER_LLM_API_KEY")
    from pubminer.integrations.llm.vendors import VENDORS

    if llm_vendor not in VENDORS:
        missing.append(f"PUBMINER_LLM_VENDOR={llm_vendor} 不存在（可用: {', '.join(sorted(VENDORS))}）")
    elif llm_vendor == "custom" and not llm_base_override:
        missing.append("PUBMINER_LLM_BASE_URL (vendor=custom 时必需)")

    ports: Any = None
    if not missing:
        from types import SimpleNamespace

        from pubminer.integrations.adapters import (
            EntrezGeneResolver,
            GoalParseAdapter,
            LlmExtractPort,
            LlmScreenPort,
            LlmVerifyPort,
            PubexCitationAdapter,
            PubexHydrateAdapter,
            PubexSearchAdapter,
        )
        from pubminer.integrations.adapters.pubtator import PubTatorEntityResolver
        from pubminer.integrations.adapters.resolver import CompositeEntityResolver
        from pubminer.integrations.llm import LLMGateway, PromptRegistry
        from pubminer.integrations.llm.providers import build_llm_provider
        from pubminer.integrations.loop_runner import LoopRunner
        from pubminer.integrations.tools import ToolRegistry, ToolResult
        from pubex.clients import AsyncPubMedClient, PMCFulltextClient

        loop = LoopRunner()
        pubmed_client = AsyncPubMedClient(email=email, api_key=api_key, tool_name="PubMinerAgent")
        pmc_client = PMCFulltextClient(cache_dir=env.get("PUBMINER_PMC_CACHE", "./download/pmc_cache"))
        prompt_registry = PromptRegistry.discover()

        protocol = env.get("PUBMINER_LLM_PROTOCOL", "auto").strip().lower()
        # 协商优先级：Responses API -> Anthropic Messages -> Chat Completions
        llm_provider = build_llm_provider(
            llm_key, llm_model, vendor=llm_vendor, base_url=llm_base_override,
            protocol=protocol, thinking=llm_thinking, thinking_budget=llm_thinking_budget,
        )
        gateway = LLMGateway(llm_provider)
        registry = ToolRegistry()
        from pubminer.integrations.tools import builtin_tool_specs

        for spec in builtin_tool_specs():
            registry.register(
                spec,
                lambda **kwargs: ToolResult(tool_name="bound", ok=True, summary="wired at assembly"),
            )

        goal_parser = GoalParseAdapter(gateway, prompt_registry)
        gene_resolver = EntrezGeneResolver(loop, email=email, api_key=api_key)
        pubtator_resolver = PubTatorEntityResolver(loop)
        composite = CompositeEntityResolver(gene_resolver=gene_resolver, pubtator_resolver=pubtator_resolver)

        citations = PubexCitationAdapter(pubmed_client, loop)
        ports = SimpleNamespace(
            search=PubexSearchAdapter(pubmed_client, loop),
            hydrate=PubexHydrateAdapter(pubmed_client, pmc_client, loop),
            screen=LlmScreenPort(gateway, prompt_registry),
            extract=LlmExtractPort(gateway, prompt_registry),
            normalize=composite,
            citations=citations,
            verify=LlmVerifyPort(gateway, prompt_registry),
            goal_parser=goal_parser,
        )
        notes.append(f"real ports wired: vendor={llm_vendor} model={llm_model} "
                     f"protocol={llm_protocol} thinking={llm_thinking}, NCBI as {email}")
    else:
        notes.append("missing env: " + ", ".join(missing) + " -- workflow disabled (503)")

    container = build_container(db_url, workflow_ports=ports)
    container.notes = notes  # type: ignore[attr-defined]

    if ports is not None:
        # 解析缓存：包装 composite resolver（复用同一 session_factory）
        from pubminer.workflows.normalize_cache import CachedEntityResolver

        ports.normalize = CachedEntityResolver(
            ports.normalize, container.session_factory,
            resolver_name=f"composite@{container.pipeline_release}",
        )
        # LLM 结果缓存：抽取/验证按内容哈希跨 run 复用（prompt_version 参与 key）
        from pubminer.workflows.result_cache import CachedExtractPort, CachedVerifyPort

        ports.extract = CachedExtractPort(ports.extract, prompt_version="extraction/biomarker@v1")
        ports.verify = CachedVerifyPort(ports.verify, prompt_version="verification@v1")
        # goal parser 同时暴露给 API 层（parse-goal 端点检查 container.goal_parser）
        container.goal_parser = goal_parser
        # LLM 网关与 prompt 资产暴露给 API 层（证据问答 qa 端点使用）
        container.llm = gateway
        container.prompt_registry = prompt_registry
        # 领域 schema 生成/校准适配器（schemas 端点使用）
        from pubminer.integrations.adapters.schema_generate import SchemaGenerateAdapter

        container.schema_generator = SchemaGenerateAdapter(gateway, prompt_registry)

    # embedding service（万级文献筛选预过滤）
    llm_key = env.get("PUBMINER_LLM_API_KEY", "")
    llm_base = env.get("PUBMINER_LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    embed_model = env.get("PUBMINER_EMBEDDING_MODEL", "embedding-3")
    embed_dims = int(env.get("PUBMINER_EMBEDDING_DIMENSIONS", "2048"))
    if llm_key:
        from pubminer.integrations.llm.providers.embedding import EmbeddingProvider
        from pubminer.workflows.embedding_service import EmbeddingService

        embed_provider = EmbeddingProvider(
            llm_key, embed_model, base_url=llm_base, dimensions=embed_dims,
        )
        container.embedding_service = EmbeddingService(embed_provider.embed)
        notes.append(f"embedding service wired: {embed_model} dim={embed_dims}")

    return container, notes


@dataclass
class Container:
    session_factory: sessionmaker
    workflow_ports: Any = None  # MiningPorts；None 时任务创建返回 503
    goal_parser: Any = None  # 目标解析适配器；None 时 parse-goal 返回 503
    pipeline_release: str = "mvp-0.1"
    request_counter: int = 0
    notes: list = field(default_factory=list)
    embedding_service: Any = None
    llm: Any = None
    prompt_registry: Any = None
    schema_generator: Any = None

    def next_request_id(self) -> str:
        self.request_counter += 1
        return f"req_{self.request_counter:08d}"

    def session_service(self, session: Session) -> AgentSessionService:
        return AgentSessionService(AgentSessionRepository(session))

    def task_repository(self, session: Session) -> TaskRepository:
        return TaskRepository(session)

    def claim_repository(self, session: Session) -> ClaimRepository:
        return ClaimRepository(session)

    def entity_repository(self, session: Session):
        from pubminer.infrastructure.db.repositories.entities import EntityRepository

        return EntityRepository(session)

    def document_repository(self, session: Session):
        from pubminer.infrastructure.db.repositories.documents import DocumentRepository

        return DocumentRepository(session)


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
