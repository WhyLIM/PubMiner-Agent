# PubMiner Evidence Agent

基于 PubMed/PMC 的可信生物医学 Evidence Agent。以自然语言提出研究目标，Agent 自动完成文献检索、筛选、结构化抽取、实体归一化与跨论文验证，生成每条结论都可回溯到论文原文 span 的研究报告；候选结论经人工审核后才可进入发布状态。

## 特性

- **一键研究**：一句话目标 → 自动解析约束 → 检索 → 筛选 → 抽取 → 归一化 → 验证 → 聚合
- **证据锚定**：每条结论绑定论文原文 span（固定 offset + content hash），UI 点击即高亮定位
- **双源归一化**：NCBI Gene + PubTator 3 交叉验证，标识符只来自 resolver，绝不编造
- **四极性验证**：同一结论同时保留 SUPPORT / CONTRADICT / NO_EFFECT / UNCERTAIN 证据
- **人工审核门禁**：冲突优先的审核队列，批量操作，乐观锁防覆盖；Agent 无法自动发布
- **可观测**：真实 workflow 事件流、token 用量、覆盖矩阵、失败断点恢复

## 架构

```
webui (Vue 3 + Element Plus + ECharts)
   │  /api/v1
pubminer (FastAPI)
   ├─ agents/       有界 Orchestrator · 停止策略
   ├─ workflows/    检索→水合→筛选→抽取→归一化→验证→聚合
   ├─ domain/       领域模型与不变量
   └─ api/          /api/v1 · SSE 事件流 · 审核决策
   │
pubex (SDK)  PubMed 检索/元数据 · PMC OA 全文 · 稳定 passage offset
   │
NCBI E-utilities · PMC OA · PubTator 3 · LLM（Responses/Anthropic/Completions 自动协商）
```

## 快速开始

### 1. 后端

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -e ".[db,api,dev]"

copy .env.example .env    # 填入 PUBMED_EMAIL / PUBMINER_LLM_API_KEY 等
set PYTHONUTF8=1
.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.venv\Scripts\pubminer-api        # http://localhost:8001
```

### 2. 前端

```bash
cd webui
pnpm install
pnpm dev                          # http://localhost:3001
```

### 3. 或命令行一键研究

```bash
.venv\Scripts\pubminer-agent --goal "寻找2020年以来胰腺癌预后biomarker，并确认是否存在独立队列验证"
```

## LLM 供应商

`PUBMINER_LLM_VENDOR` 内置支持：`zhipu` · `zhipu-coding` · `zai` · `deepseek` · `openai` · `anthropic` · `moonshot` · `minimax` · `qwen` · `custom`。

协议按 **Responses API → Anthropic Messages → Chat Completions** 优先级自动协商；thinking 模式按厂商官方参数自动映射（`PUBMINER_LLM_THINKING=off|on`）。详见 `.env.example` 注释。

## 示例

```bash
.venv\Scripts\python.exe examples/offline_demo.py   # 零配置离线演示完整管线
.venv\Scripts\python.exe scripts/smoke_llm.py       # LLM 连通性探针
```

## 测试

```bash
.venv\Scripts\python.exe -m pytest tests/            # 194 项：unit + contract + golden + architecture
cd webui && pnpm exec vue-tsc --noEmit && pnpm build # 前端类型检查 + 构建
```

安全门禁内置于测试：src/ 禁止 Sci-Hub 与 TLS 绕过；标识符只能来自 resolver；无 evidence span 不得创建 Claim。

## 文档

- 架构基线：[PubMiner_生物医学证据Agent完整设计文档_v1.3.md](./PubMiner_生物医学证据Agent完整设计文档_v1.3.md)
- 架构决策记录：[docs/adr/](./docs/adr)（ADR-001～012）
- 环境变量说明：[.env.example](./.env.example)
