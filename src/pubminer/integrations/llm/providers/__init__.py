"""LLM provider adapters。厂商协议细节只允许出现在本包内。

协议优先级：Responses API → Anthropic Messages → Chat Completions。
默认 auto 协商：`build_llm_provider(protocol="auto")` 运行时探测并粘住首个
可用协议；也可用 PUBMINER_LLM_PROTOCOL 固定为 responses|anthropic|completions。
"""
from pubminer.integrations.llm.providers.anthropic import AnthropicProvider
from pubminer.integrations.llm.providers.auto import (
    PROTOCOL_CLASSES,
    PROTOCOL_PRIORITY,
    AutoProtocolProvider,
    build_llm_provider,
)
from pubminer.integrations.llm.providers.base import (
    HttpJsonProvider,
    ProtocolNotSupportedError,
)
from pubminer.integrations.llm.providers.fake import FakeLLMProvider
from pubminer.integrations.llm.providers.openai_compat import OpenAICompatibleProvider
from pubminer.integrations.llm.providers.responses_api import ResponsesApiProvider

__all__ = [
    "FakeLLMProvider",
    "OpenAICompatibleProvider",
    "ResponsesApiProvider",
    "AnthropicProvider",
    "AutoProtocolProvider",
    "HttpJsonProvider",
    "ProtocolNotSupportedError",
    "build_llm_provider",
    "PROTOCOL_CLASSES",
    "PROTOCOL_PRIORITY",
]
