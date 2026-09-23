# ADR-005: 有界 Agent orchestrator + typed tools + 确定性状态机
状态: accepted
决策: Agent 只能选择 registry 中注册的 typed tool 与 workflow command；
轮次/成本/来源/权限/人工确认/停止条件全部显式建模（domain/agents.py）。
禁止: 任意代码执行、未注册网络请求、修改 approved claim、自动 publish。
