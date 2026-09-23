"""PubMiner Evidence Agent 新架构包。

依赖方向（设计文档 §5.1，违反即架构缺陷）：
    api -> application -> domain
    agent -> workflows -> application -> domain
    integrations/infrastructure -> domain ports

domain 不导入 FastAPI、SQLAlchemy、任何厂商 SDK。
"""
__version__ = "0.1.0"
