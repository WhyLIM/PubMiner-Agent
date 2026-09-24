# PubMiner Evidence Agent

单一项目仓库：以《生物医学证据 Agent 完整设计文档 v1.3》为基线实现的**可信生物医学 Evidence Agent**。用户以自然语言提出研究目标，Agent 澄清约束、制定计划、调用受控工具检索与分析文献、评估证据覆盖，生成每条关键结论都可定位到论文原文 span 的研究报告；候选结论经人工审核后才可能进入发布状态。

```
D:\Study\Project\PubMiner Agent\
├── src/
│   ├── pubminer/        # Agent 编排与业务后端（唯一业务后端）
│   │   ├── domain/          # 领域模型与不变量（Claim/Evidence/AgentSession…）
│   │   ├── application/     # 端口（LLMPort/ToolRegistry）与会话命令
│   │   ├── agents/          # 有界 Orchestrator、停止策略、覆盖评估
│   │   ├── workflows/       # MiningWorkflow（检索→…→聚合）、跨论文验证
│   │   ├── integrations/    # 真实适配器：pubex 客户端、LLM、Gene resolver
│   │   ├── infrastructure/  # SQLAlchemy ORM + 仓储（migrations/ 配套）
│   │   └── api/             # /api/v1（FastAPI）
│   └── pubex/           # 文献获取解析 SDK（PubMed/PMC，稳定 offset，typed errors）
├── prompts/             # 版本化 prompt 资产（agent-policy/screening/extraction/verification）
├── migrations/          # Alembic 0001–0006（可移植类型：生产 PG / 测试 SQLite）
├── tests/               # 统一测试套件（unit / contract / golden / architecture）
├── docs/adr/            # ADR-001～011
├── webui/               # Vue 3 + Element Plus + ECharts 前端（总览 / · 工作台 /agent · 审核 /review）
├── alembic.ini · pytest.ini · pyproject.toml · .env.example
└── PubMiner_生物医学证据Agent完整设计文档_v1.3.md   # 架构基线
```

## 快速开始

```bash
# 0) 后端环境（Python ≥3.10）
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -e ".[db,api,dev]"

# 1) 配置：复制 .env.example，填 PUBMED_EMAIL 与 PUBMINER_LLM_API_KEY
copy .env.example .env

# 2) 建库 + 启动 API（:8001）
set PUBMINER_DB_URL=sqlite:///./pubminer_ea.db
set PYTHONUTF8=1
.venv/Scripts/python.exe -m alembic -c alembic.ini upgrade head
.venv/Scripts/pubminer-api

# 3a) 命令行端到端
.venv/Scripts/pubminer-agent --goal "寻找2020年以来胰腺癌预后biomarker并确认独立队列验证" --disease "pancreatic cancer"

# 3b) 或前端（:3001，开发态自动代理 /api 到 :8001）
cd webui && pnpm install && pnpm dev
#    总览: http://localhost:3001/          Agent 工作台: http://localhost:3001/agent
#    证据审核: http://localhost:3001/review
```

缺 NCBI/LLM 配置时 API 仍可启动（会话与审核可用；检索任务返回 503 并说明缺哪个变量）。

### LLM 厂商与协议支持

接入层分三层配置（依据 2026-09 各官方文档核对）：

1. **供应商选择**：`PUBMINER_LLM_VENDOR` = zhipu | zhipu-coding | zai | deepseek | openai | anthropic | moonshot | minimax | qwen | custom。base url 内置于 `src/pubminer/integrations/llm/vendors.py` 注册表（各协议端点不同，如智谱 anthropic 走 `/api/anthropic`）；`PUBMINER_LLM_BASE_URL` 仅作覆盖，模型留空用厂商默认。
2. **协议协商**：`PUBMINER_LLM_PROTOCOL=auto`（默认）按 **Responses API → Anthropic Messages → Chat Completions** 优先级运行时探测，粘住首个可用协议；404/405/501 视为协议不可用自动降级，401/429/500 等真实错误不降级直接抛出。
3. **Thinking 控制**：`PUBMINER_LLM_THINKING=default|off|on` 按厂商官方参数自动映射——
   - 智谱 GLM / Moonshot Kimi：`thinking: {"type": "enabled"|"disabled"}`（GLM-4.5+/K2.6 轮级思考）
   - 通义 Qwen（DashScope 兼容）：`enable_thinking: true|false`
   - OpenAI：completions 用 `reasoning_effort`（off→minimal / on→medium）；Responses 用 `reasoning: {effort}`
   - Anthropic：`thinking: {type: enabled, budget_tokens}`，启用时自动移除 temperature 并抬高 max_tokens（budget 见 `PUBMINER_LLM_THINKING_BUDGET`）
   - DeepSeek V3.2 / MiniMax M2：默认不注入（DeepSeek 建议用模型变体；M2 思考常开）

| 厂商 | Responses | Anthropic Messages | Completions（兜底） |
|---|---|---|---|
| OpenAI / Azure | ✅ 原生 | ❌ | ✅ |
| DeepSeek（V4+） | ✅ | ❌ | ✅ |
| 智谱 GLM | ✅ `/api/paas/v4/responses` | ✅ `/api/anthropic` | ✅ |
| Moonshot Kimi | ✅ | ✅ | ✅ |
| MiniMax | 未确认 | ✅ `/anthropic` | ✅ |
| Anthropic | ❌ | ✅ 原生 | ❌ |
| Gemini / Qwen 兼容层、旧网关 | ❌ | ❌ | ✅ |

配置示例见 `.env.example`；`PUBMINER_LLM_PROTOCOL` 可固定为 `responses|anthropic|completions` 跳过探测。协议细节只在 `src/pubminer/integrations/llm/providers/` 内实现（Responses：`POST {base}/responses`；Anthropic：`POST {base}/v1/messages` + `x-api-key`；Completions：`POST {base}/chat/completions`）。

## 示例

```bash
.venv/Scripts/python.exe examples/offline_demo.py
```

零配置离线跑通完整管线（检索→筛选→抽取→归一化→验证→聚合），打印任务步骤与带原文 span 的候选结论；真实适配器如何替换 fake 见 `examples/offline_demo.py` 文件头注释。`tests/test_examples.py` 守护该样例始终可运行。

真实 key 配置好后，先用 LLM 握手探针验证供应商/协议/thinking 配置：

```bash
.venv/Scripts/python.exe scripts/smoke_llm.py   # 打印协商到的协议、模型、延迟、token
```

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests/        # 181 项：unit + contract + golden + architecture + api
cd webui && pnpm exec vue-tsc --noEmit && pnpm build # 前端类型检查 + 构建
```

- `tests/golden`：MEDLINE 字段映射以冻结快照为基线（曾与 legacy 实现逐字节比对），防止解析漂移。
- `tests/architecture/test_security_baseline.py`：门禁——src/ 内禁止 Sci-Hub 与任何 TLS 绕过；import 不改全局 SSL；证书错误快速失败；domain 层无框架/厂商导入。

## 安全与治理红线（实现中已强制）

- 禁止 Sci-Hub、关闭 TLS 校验、未注册网络请求、任意代码执行。
- canonical identifier 只能来自 resolver（ADR-006）；无 evidence span 不得创建 Claim。
- Agent 只能调用注册 typed tools；APPROVED/PUBLISHED 需人工角色；审核记录追加（before/after），不改写模型原始输出。

架构决策详见 `docs/adr/`；产品/数据/工作流设计以设计文档为唯一基线。
