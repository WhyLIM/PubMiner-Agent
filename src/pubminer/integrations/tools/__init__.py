"""Typed tools：声明（ToolSpec）与注册表。handler 在 workflows/api 装配时绑定。"""
from pubminer.integrations.tools.builtin import builtin_tool_specs
from pubminer.integrations.tools.registry import (
    ToolRegistry,
    ToolResult,
    ToolRole,
    ToolSpec,
    ToolPermissionError,
)

__all__ = [
    "ToolRegistry", "ToolResult", "ToolRole", "ToolSpec",
    "ToolPermissionError", "builtin_tool_specs",
]
