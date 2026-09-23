"""PubEx: 文献获取与解析 SDK。

职责边界（设计文档 v1.3 §2.4）：
- PubMed / PMC / PubTator 的获取与解析，输出 typed models；
- 不含用户、审核、业务 task、发布状态或 Web API。
"""
from pubex.errors import (
    PubExError,
    PubExHTTPError,
    PubExNetworkError,
    PubExRateLimitError,
    PubExTLSVerificationError,
    PubExMaxRetriesExceeded,
)
from pubex.models import PubMedArticle, ArticleIdentifiers
from pubex import parsers

__version__ = "0.1.0"

__all__ = [
    "PubExError",
    "PubExHTTPError",
    "PubExNetworkError",
    "PubExRateLimitError",
    "PubExTLSVerificationError",
    "PubExMaxRetriesExceeded",
    "PubMedArticle",
    "ArticleIdentifiers",
    "parsers",
    "__version__",
]
