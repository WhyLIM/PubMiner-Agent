"""Provider adapters。厂商 SDK 只允许在本包内懒加载。"""
from pubminer.integrations.llm.providers.fake import FakeLLMProvider

__all__ = ["FakeLLMProvider"]
