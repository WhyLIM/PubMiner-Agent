# ADR-011: 业务只依赖 LLMPort / ToolRegistry 端口
状态: accepted (2026-09-23)
决策: workflow/agent 只面向 Protocol 端口（LLMPort、tool registry、document port）；
Zhipu/OpenAI 等是 integrations/llm/providers 下的 adapter。测试用 fake provider。
