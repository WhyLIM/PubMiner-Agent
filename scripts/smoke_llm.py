"""真实 LLM 冒烟：验证 key、协议协商与一次最小补全。

用法：.venv/Scripts/python.exe scripts/smoke_llm.py
"""
from __future__ import annotations

import sys

from pubminer.application.ports import LLMRequest
from pubminer.settings import load_env_file


def main() -> int:
    load_env_file()
    import os

    from pubminer.integrations.llm import LLMGateway
    from pubminer.integrations.llm.providers import build_llm_provider

    api_key = os.environ.get("PUBMINER_LLM_API_KEY", "")
    provider = build_llm_provider(
        api_key,
        os.environ.get("PUBMINER_LLM_MODEL") or None,
        vendor=os.environ.get("PUBMINER_LLM_VENDOR", "zhipu"),
        base_url=os.environ.get("PUBMINER_LLM_BASE_URL") or None,
        protocol=os.environ.get("PUBMINER_LLM_PROTOCOL", "auto"),
        thinking=os.environ.get("PUBMINER_LLM_THINKING", "default"),
    )
    gateway = LLMGateway(provider)
    response = gateway.generate(
        LLMRequest(
            purpose="smoke-ping",
            prompt_version="smoke@v1",
            system="You are a connectivity probe. Reply with exactly: PONG",
            user="ping",
            temperature=0.0,
            max_tokens=256,
        )
    )
    print(f"negotiated protocol : {provider.name if hasattr(provider, 'name') else provider}")
    print(f"model               : {response.model}")
    print(f"latency             : {response.latency_ms} ms")
    print(f"tokens              : {response.usage.prompt_tokens} in / {response.usage.completion_tokens} out")
    print(f"reply               : {response.text.strip()[:80]!r}")
    return 0 if "PONG" in response.text.upper() else 1


if __name__ == "__main__":
    sys.exit(main())
