"""api：/api/v1 HTTP 层。

API 不直接写 ORM——只调用 application commands / workflow；前端只依赖本层契约。
"""
from pubminer.api.app import create_app

__all__ = ["create_app"]
