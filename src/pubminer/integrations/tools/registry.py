"""Typed tool registry（设计文档 §9.2 / ADR-005）。

红线：
- Agent 只能调用 registry 中注册的 tool；未注册 = 策略拒绝；
- 每个工具声明权限范围；角色越权 = 策略拒绝；
- PublishClaimTool 仅限人工特权角色。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pubminer.application.ports import LLMError

logger = logging.getLogger("pubminer.tools")


class ToolPermissionError(LLMError):
    """工具未注册或角色越权。"""


class ToolRole(str, Enum):
    AGENT = "agent"            # Evidence Agent（有界）
    CURATOR = "curator"        # 人工审核
    SENIOR_REVIEWER = "senior_reviewer"
    SYSTEM = "system"          # worker


@dataclass(frozen=True)
class ToolSpec:
    """一个 typed tool 的声明。handler 由 adapter 绑定。"""

    name: str
    description: str
    allowed_roles: frozenset[ToolRole]
    permission: str = "read"  # read | write_candidate | create_review | publish | ask_human
    requires_confirmation: bool = False
    output_schema: str | None = None


@dataclass
class ToolResult:
    tool_name: str
    ok: bool
    summary: str
    result_count: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ToolRegistry:
    """注册表 + 授权检查 + 调用审计。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[..., ToolResult]] = {}
        self.audit_log: list[dict[str, Any]] = []

    def register(self, spec: ToolSpec, handler: Callable[..., ToolResult]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name} already registered")
        self._tools[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolPermissionError(f"tool {name!r} is not registered") from None

    def authorize(self, name: str, role: ToolRole) -> ToolSpec:
        """未注册或角色越权都抛 ToolPermissionError。"""
        spec = self.get(name)
        if role not in spec.allowed_roles:
            raise ToolPermissionError(
                f"role {role.value} is not allowed to call {name}"
            )
        return spec

    def call(self, name: str, role: ToolRole, **kwargs: Any) -> ToolResult:
        """授权 → 执行 → 审计。handler 异常转 failed ToolResult。"""
        spec = self.authorize(name, role)
        handler = self._handlers[name]
        try:
            result = handler(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("tool %s failed: %s", name, exc)
            result = ToolResult(tool_name=name, ok=False, summary=str(exc), error=str(exc))
        self.audit_log.append(
            {
                "tool": name,
                "role": role.value,
                "ok": result.ok,
                "summary": result.summary[:500],
                "requires_confirmation": spec.requires_confirmation,
            }
        )
        return result

    def tools_for_role(self, role: ToolRole) -> list[ToolSpec]:
        return [spec for spec in self._tools.values() if role in spec.allowed_roles]

    def __contains__(self, name: str) -> bool:
        return name in self._tools
