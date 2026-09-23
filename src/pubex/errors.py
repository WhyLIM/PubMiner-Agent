"""PubEx typed 异常体系（与 legacy PubEx.py 语义一致，作为 SDK 的规范定义）。

原则：证书校验失败可观测、显式失败、不可静默降级；错误分类决定是否可重试。
"""
from __future__ import annotations


class PubExError(Exception):
    """PubEx 错误基类：所有自定义异常都可归类、可观测、不静默降级。"""


class PubExHTTPError(PubExError):
    """NCBI 返回的非 2xx HTTP 状态。retryable 表示是否值得重试。"""

    def __init__(self, status_code: int, message: str, retryable: bool = False):
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(f"HTTP {status_code}: {message}")


class PubExRateLimitError(PubExHTTPError):
    """HTTP 429：请求过于频繁，应按 backoff 重试。"""

    def __init__(self, message: str = "rate limited by NCBI"):
        super().__init__(429, message, retryable=True)


class PubExNetworkError(PubExError):
    """网络层传输失败（连接中断、超时等），通常可重试。"""


class PubExTLSVerificationError(PubExError):
    """TLS/证书校验失败。

    证书问题必须显式失败并暴露原因，禁止重试掩盖或降级为不校验。
    修复方式：更新系统证书、检查代理/中间人设备，而不是关闭校验。
    """


class PubExMaxRetriesExceeded(PubExError):
    """达到最大重试次数后仍失败。"""

    def __init__(self, retries: int, last_error: BaseException | None):
        self.retries = retries
        self.last_error = last_error
        super().__init__(f"达到最大重试次数（{retries}）后仍失败: {last_error}")
