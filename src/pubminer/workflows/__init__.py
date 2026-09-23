"""workflows：确定性 workflow（mining / verification / reprocessing）。

依赖方向：workflows -> application -> domain；外部能力（pubex 客户端、LLM）
通过本包声明的 Protocol 端口注入，测试用 fake 实现。
"""
from pubminer.workflows.mining import MiningWorkflow, MiningPorts, SearchIntent

__all__ = ["MiningWorkflow", "MiningPorts", "SearchIntent"]
