# PubMiner Evidence Agent

基于 PubMed/PMC 的可信生物医学 Evidence Agent。以自然语言提出研究目标，Agent 自动完成文献检索、筛选、结构化抽取、实体归一化与跨论文验证，生成每条结论都可回溯到论文原文 span 的研究报告；候选结论经人工审核后才可进入发布状态。

## 特性

- **一键研究**：一句话目标 → LLM 解析约束（含歧义追问）→ 检索 → 三级筛选 → 结构化抽取 → 归一化 → 验证 → 独立验证检测 → 聚合
- **证据锚定**：每条结论绑定论文原文 span（固定 offset + content hash），UI 点击即高亮定位
- **三级筛选级联**：embedding 余弦预筛（万级跳过 80%）→ LLM 摘要筛选 → UNCERTAIN 全文重筛
- **span 二次修复**：LLM 改写导致 span 定位失败时，自动用 mention 锚定窗口重新摘录
- **双源归一化**：NCBI Gene + PubTator 3 交叉验证，缩写歧义自动送审，标识符只来自 resolver
- **迭代扩展**：独立验证未发现时自动经引文扩展（cited-by/references）拉入新文献再验证
- **规则辅助验证**：p 值正则提取 + 显著性关键词预判注入 prompt，减少 UNCERTAIN 率
- **四极性验证**：同一结论同时保留 SUPPORT / CONTRADICT / NO_EFFECT / UNCERTAIN 证据
- **人工审核门禁**：冲突优先的审核队列，多选批量操作，乐观锁防覆盖；Agent 无法自动发布
- **CBD 格式导出**：`GET /api/v1/export/cbd` 输出 Colorectal Cancer Biomarker Database 兼容 JSON

## 架构

```
webui (Vue 3 + Element Plus + ECharts，明暗双主题)
   │  /api/v1
pubminer (FastAPI)
   ├─ agents/         有界 Orchestrator · 停止策略 · 覆盖评估
   ├─ workflows/      挖掘管线（七步 + 引文扩展）· 领域 schema · 解析缓存
   ├─ domain/         领域模型与不变量
   ├─ integrations/   pubex 客户端 · LLM 协商 · Gene/PubTator resolver
   ├─ infrastructure/ SQLAlchemy ORM + Alembic 迁移 + 仓储
   └─ api/            /api/v1 · SSE 事件流 · 审核决策 · CBD 导出
   │
pubex (SDK)           PubMed 检索/元数据 · PMC OA 全文 · 稳定 passage offset
   │
NCBI E-utilities · PMC OA · PubTator 3 · LLM（Responses/Anthropic/Completions 自动协商）
```

## 领域可配置

管线不硬编码研究领域。谓词、方向、签名模板、验证阈值、筛选提示、导出映射全部由 JSON schema 驱动：

```bash
schemas/
├── domains/
│   ├── biomarker.json      # 预后/诊断/预测 biomarker 研究
│   └── drug-target.json    # 药物靶点交互研究
└── extraction_fields/
    ├── colorectal.json     # 结直肠癌：检测方法/分期/位置/样本量/…
    └── generic.json        # 通用（无额外字段）
```

换研究领域 = 新建一个 JSON 文件 + `.env` 设 `PUBMINER_LLM_DOMAIN=新领域名`。详见 [docs/domain-schema-spec.md](docs/domain-schema-spec.md)。

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

| 页面 | 功能 |
|---|---|
| `/` 总览 | 统计卡片 + ECharts 极性/优先级图 + 最近任务 + 待审 TOP |
| `/agent` 工作台 | 一键研究 · 检索式预览/编辑 · 行动轨迹 · 证据高亮 · 覆盖矩阵 |
| `/review` 审核台 | 冲突优先队列 · 原文 span 高亮 · 批量操作 · 乐观锁 |

### 3. 或命令行一键研究

```bash
.venv\Scripts\pubminer-agent --goal "寻找2020年以来胰腺癌预后biomarker，并确认是否存在独立队列验证"
```

## LLM 供应商

`PUBMINER_LLM_VENDOR` 内置支持：`zhipu` · `zhipu-coding` · `zai` · `deepseek` · `openai` · `anthropic` · `moonshot` · `minimax` · `qwen` · `custom`。

协议按 **Responses API → Anthropic Messages → Chat Completions** 优先级自动协商；thinking 模式按厂商官方参数自动映射。详见 `.env.example` 注释。

## 示例

```bash
.venv\Scripts\python.exe examples/offline_demo.py   # 零配置离线演示完整管线
.venv\Scripts\python.exe scripts/smoke_llm.py       # LLM 连通性探针
```

## 测试

```bash
.venv\Scripts\python.exe -m pytest tests/            # 217 项：unit + contract + golden + architecture
cd webui && pnpm exec vue-tsc --noEmit && pnpm build # 前端类型检查 + 构建
```

安全门禁内置于测试：src/ 禁止 Sci-Hub 与 TLS 绕过；标识符只能来自 resolver；无 evidence span 不得创建 Claim。

## 文档

- 架构基线：[PubMiner_生物医学证据Agent完整设计文档_v1.3.md](./PubMiner_生物医学证据Agent完整设计文档_v1.3.md)
- 架构决策记录：[docs/adr/](./docs/adr)（ADR-001～012）
- 领域 Schema 规范：[docs/domain-schema-spec.md](docs/domain-schema-spec.md)
- 环境变量说明：[.env.example](./.env.example)
