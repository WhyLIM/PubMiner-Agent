"""共享异步重试：typed 异常分类 + 指数退避；证书失败快速失败。"""
from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiohttp import ClientError

from pubex.errors import (
    PubExHTTPError,
    PubExMaxRetriesExceeded,
    PubExNetworkError,
    PubExRateLimitError,
    PubExTLSVerificationError,
)

logger = logging.getLogger("pubex.retry")

T = TypeVar("T")

_RETRYABLE_STATUS = {500, 502, 503, 504}


def classify_client_error(exc: BaseException) -> PubExTLSVerificationError | PubExNetworkError | None:
    """把 aiohttp/ssl 层异常归类为 typed PubEx 错误；None 表示不识别。"""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return PubExTLSVerificationError(str(exc))
    text = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in text.upper() or "certificate verify failed" in text.lower():
        return PubExTLSVerificationError(text)
    if isinstance(exc, ClientError):
        return PubExNetworkError(text)
    if isinstance(exc, (OSError, TimeoutError, asyncio.TimeoutError)):
        return PubExNetworkError(text)
    return None


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_wait: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """执行异步操作并按分类重试。

    - 429 → PubExRateLimitError，按 Retry-After/backoff 重试
    - 5xx → PubExHTTPError(retryable=True)，指数退避重试
    - 4xx → PubExHTTPError(retryable=False)，立即抛出
    - TLS 证书失败 → PubExTLSVerificationError，立即抛出，不降级
    - 其他网络错误 → PubExNetworkError，重试
    - 重试耗尽 → PubExMaxRetriesExceeded
    """
    last_error: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except PubExHTTPError:
            raise
        except PubExTLSVerificationError:
            raise
        except BaseException as exc:  # noqa: BLE001 — 统一归类后决定是否重试
            classified = classify_client_error(exc)
            if classified is None:
                raise
            if isinstance(classified, PubExTLSVerificationError):
                logger.error("TLS 证书校验失败，禁止降级重试: %s", classified)
                raise classified from exc
            last_error = classified
            if attempt >= max_retries:
                break
            wait = base_wait * (2**attempt)
            logger.warning("%s，%.1fs 后重试（第 %d/%d 次）", classified, wait, attempt + 1, max_retries)
            await sleep(wait)
    raise PubExMaxRetriesExceeded(max_retries, last_error)


def http_error_from_status(status: int, message: str = "") -> PubExHTTPError:
    if status == 429:
        return PubExRateLimitError(message or "rate limited")
    return PubExHTTPError(status, message or f"HTTP {status}", retryable=status in _RETRYABLE_STATUS)
