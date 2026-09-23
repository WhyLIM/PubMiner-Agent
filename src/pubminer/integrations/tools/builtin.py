"""设计文档 §9.2 的内建 typed tools 声明。

handler 在 api/workflows 装配时绑定；本模块只定义权限边界。
"""
from __future__ import annotations

from pubminer.integrations.tools.registry import ToolRole, ToolSpec

_AGENT_ONLY = frozenset({ToolRole.AGENT})
_HUMAN_ONLY = frozenset({ToolRole.CURATOR, ToolRole.SENIOR_REVIEWER})
_SYSTEM_ONLY = frozenset({ToolRole.SYSTEM})


def builtin_tool_specs() -> list[ToolSpec]:
    """返回 §9.2 表格中全部 typed tools 的声明。"""
    return [
        ToolSpec(
            name="PubMedSearchTool",
            description="PubMed esearch；返回 SearchResultPage",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM}),
            permission="read_external",
        ),
        ToolSpec(
            name="PMCFulltextTool",
            description="PMC OA BioC 全文；返回 DocumentVersion + LicenseRecord",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM}),
            permission="read_external",
        ),
        ToolSpec(
            name="PubTatorTool",
            description="PubTator 实体/关系标注；返回 EntityCandidates + Relations",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM}),
            permission="read_external",
        ),
        ToolSpec(
            name="EntityResolverTool",
            description="ontology resolver 候选；返回 CanonicalEntityCandidate[]",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM}),
            permission="read_ontology",
        ),
        ToolSpec(
            name="ExtractionTool",
            description="schema 约束抽取；只能产生 derived candidate",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM}),
            permission="write_candidate",
        ),
        ToolSpec(
            name="CreateCandidateClaimTool",
            description="创建 CANDIDATE claim（必须绑定 evidence）",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM}),
            permission="write_candidate",
        ),
        ToolSpec(
            name="SubmitReviewTool",
            description="提交 review request",
            allowed_roles=frozenset({ToolRole.AGENT, ToolRole.SYSTEM, ToolRole.CURATOR}),
            permission="create_review",
        ),
        ToolSpec(
            name="AskHumanTool",
            description="暂停会话并请求用户输入/确认",
            allowed_roles=_AGENT_ONLY,
            permission="ask_human",
        ),
        ToolSpec(
            name="PublishClaimTool",
            description="发布已批准 claim 版本；仅限人工特权角色，禁止 Agent 调用",
            allowed_roles=_HUMAN_ONLY,
            permission="publish",
            requires_confirmation=True,
        ),
    ]
