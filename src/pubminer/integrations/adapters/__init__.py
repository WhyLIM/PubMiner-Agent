"""真实端口适配器：pubex 客户端、LLM 端口、实体 resolver。"""
from pubminer.integrations.adapters.goal_parse import GoalParseAdapter
from pubminer.integrations.adapters.llm_ports import LlmExtractPort, LlmScreenPort, LlmVerifyPort
from pubminer.integrations.adapters.pubmed import PubexCitationAdapter, PubexHydrateAdapter, PubexSearchAdapter
from pubminer.integrations.adapters.resolver import EntrezGeneResolver

__all__ = [
    "GoalParseAdapter",
    "PubexCitationAdapter",
    "PubexSearchAdapter",
    "PubexHydrateAdapter",
    "LlmScreenPort",
    "LlmExtractPort",
    "LlmVerifyPort",
    "EntrezGeneResolver",
]
