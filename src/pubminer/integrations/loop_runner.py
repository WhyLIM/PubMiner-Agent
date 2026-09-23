"""后台事件循环桥：把 pubex 异步客户端暴露为 workflow 的同步端口。

一个守护线程持有一个常驻 loop；asyncio.Lock/限流状态因此跨调用稳定。
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class LoopRunner:
    """在专用线程中运行事件循环；`run(coro)` 同步等待结果。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever, name="pubminer-asyncio", daemon=True
                )
                self._thread.start()
            return self._loop

    def run(self, coro: Coroutine[Any, Any, T], timeout: float = 120.0) -> T:
        loop = self._ensure()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._loop = None
            self._thread = None
