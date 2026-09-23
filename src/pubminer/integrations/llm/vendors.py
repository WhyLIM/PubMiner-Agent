"""厂商注册表：默认端点、默认模型与 thinking 参数风格（依据各官方文档）。

thinking 参数形态（官方文档核对于 2026-09）：
- zhipu   : chat completions `thinking: {"type": "enabled"|"disabled"}`（GLM-4.5+/4.7 轮级思考）
- qwen    : DashScope 兼容模式 `enable_thinking: true|false`（非流式下关闭需显式 False）
- openai  : completions `reasoning_effort: "minimal"|"low"|"medium"|"high"`；
            responses `reasoning: {"effort": ...}`（仅推理模型接受）
- anthropic: messages `thinking: {"type": "enabled", "budget_tokens": N}`；
            启用时 temperature 必须为 1（或省略），budget_tokens < max_tokens
- moonshot: `thinking: {"type": ...}`（kimi-k2.6 默认开思考）
- deepseek/minimax: 默认不注入 payload（DeepSeek V3.2 见官方 guides/thinking_mode；
            MiniMax M2 交错思考常开）
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VendorSpec:
    key: str
    display: str
    default_model: str
    base_urls: dict[str, str]  # 协议 -> base url（"responses" | "anthropic" | "completions"）
    thinking_style: str  # zhipu | qwen | openai | anthropic | none
    notes: str = ""


VENDORS: dict[str, VendorSpec] = {
    "zhipu": VendorSpec(
        key="zhipu", display="智谱 GLM（国内 open.bigmodel.cn）", default_model="glm-4-flash",
        base_urls={
            "responses": "https://open.bigmodel.cn/api/paas/v4",
            "completions": "https://open.bigmodel.cn/api/paas/v4",
            "anthropic": "https://open.bigmodel.cn/api/anthropic",
        },
        thinking_style="zhipu",
    ),
    "zhipu-coding": VendorSpec(
        key="zhipu-coding", display="智谱 GLM Coding Plan", default_model="glm-4-flash",
        base_urls={
            "responses": "https://open.bigmodel.cn/api/coding/paas/v4",
            "completions": "https://open.bigmodel.cn/api/coding/paas/v4",
        },
        thinking_style="zhipu",
        notes="coding 网关当前仅暴露 completions；anthropic 协议走 zhipu 条目的 /api/anthropic",
    ),
    "zai": VendorSpec(
        key="zai", display="Z.ai（国际）", default_model="glm-4-flash",
        base_urls={
            "responses": "https://api.z.ai/api/paas/v4",
            "completions": "https://api.z.ai/api/paas/v4",
            "anthropic": "https://api.z.ai/api/anthropic",
        },
        thinking_style="zhipu",
    ),
    "deepseek": VendorSpec(
        key="deepseek", display="DeepSeek", default_model="deepseek-chat",
        base_urls={"completions": "https://api.deepseek.com"},
        thinking_style="none",
        notes="V3.2 起支持 thinking，形态以官方 guides/thinking_mode 为准；默认用模型变体（deepseek-chat/reasoner）",
    ),
    "openai": VendorSpec(
        key="openai", display="OpenAI", default_model="gpt-4o-mini",
        base_urls={
            "responses": "https://api.openai.com/v1",
            "completions": "https://api.openai.com/v1",
        },
        thinking_style="openai",
    ),
    "anthropic": VendorSpec(
        key="anthropic", display="Anthropic", default_model="claude-sonnet-4-5",
        base_urls={"anthropic": "https://api.anthropic.com"},
        thinking_style="anthropic",
    ),
    "moonshot": VendorSpec(
        key="moonshot", display="Moonshot Kimi", default_model="kimi-k2.6",
        base_urls={
            "responses": "https://api.moonshot.ai/v1",
            "completions": "https://api.moonshot.ai/v1",
            "anthropic": "https://api.moonshot.ai",
        },
        thinking_style="zhipu",
    ),
    "minimax": VendorSpec(
        key="minimax", display="MiniMax", default_model="MiniMax-M2",
        base_urls={
            "completions": "https://api.minimax.io/v1",
            "anthropic": "https://api.minimax.io/anthropic",
        },
        thinking_style="none",
        notes="M2 交错思考常开，无关闭参数",
    ),
    "qwen": VendorSpec(
        key="qwen", display="通义 Qwen（DashScope 兼容模式）", default_model="qwen-plus",
        base_urls={"completions": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
        thinking_style="qwen",
    ),
    "custom": VendorSpec(
        key="custom", display="自定义端点", default_model="",
        base_urls={},  # 必须显式提供 PUBMINER_LLM_BASE_URL
        thinking_style="none",
    ),
}


def thinking_payload(
    thinking_style: str, mode: str, *, protocol: str = "completions", reasoning_effort: str = "medium"
) -> dict:
    """按厂商风格返回需要合并进请求 payload 的 thinking 相关键。

    mode: "default"（厂商默认，不注入任何键）| "off" | "on"
    仅 completions / responses 两层支持 payload 注入；anthropic 层见
    AnthropicProvider 的 thinking_mode/thinking_budget。
    """
    if mode == "default":
        return {}
    on = mode == "on"
    if thinking_style == "zhipu":
        return {"thinking": {"type": "enabled" if on else "disabled"}}
    if thinking_style == "qwen" and protocol == "completions":
        return {"enable_thinking": on}
    if thinking_style == "openai":
        effort = reasoning_effort if on else "minimal"
        if protocol == "responses":
            return {"reasoning": {"effort": effort}}
        return {"reasoning_effort": effort}
    return {}
