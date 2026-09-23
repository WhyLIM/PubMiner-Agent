"""测试用 Fake provider：确定性行为，单测不触网、不依赖厂商 SDK。"""
from __future__ import annotations

from typing import Callable

from pubminer.application.ports import LLMUsage


class FakeLLMProvider:
    """按规则回放预设响应。

    Args:
        responder: (system, user, temperature) -> (text, prompt_tokens, completion_tokens)；
            未提供时返回固定 JSON。
        embedder: 可选 embedding 函数。
    """

    name = "fake"
    model = "fake-model-v1"

    def __init__(
        self,
        responder: Callable[[str, str, float], tuple[str, int, int]] | None = None,
        embedder: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        self.responder = responder
        self.embedder = embedder
        self.calls: list[tuple[str, str, float]] = []

    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int) -> tuple[str, LLMUsage]:
        self.calls.append((system, user, temperature))
        if self.responder is not None:
            text, pt, ct = self.responder(system, user, temperature)
        else:
            text, pt, ct = '{"ok": true}', len(system) // 4, len(user) // 4
        return text, LLMUsage(prompt_tokens=pt, completion_tokens=ct)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embedder is None:
            raise NotImplementedError
        return self.embedder(texts)
