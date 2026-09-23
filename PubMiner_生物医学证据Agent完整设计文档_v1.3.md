# PubMiner 生物医学证据 Agent 完整设计文档

Agent first 与可信证据底座实施设计 v1.3

| **项目** | **内容**                                                       |
|----------|----------------------------------------------------------------|
| 文档定位 | 生物医学 Evidence Agent 的产品、领域、数据、工作流与实施基线   |
| 审计仓库 | WhyLIM/PubMiner-webui · WhyLIM/PubMiner · WhyLIM/PubEx         |
| 目标版本 | MVP Biomarker Evidence Agent → V1 Cross paper Evidence Agent   |
| 核心原则 | Agent 自主研究，工具受控执行，证据原文可追溯，关键结论由人确认 |
| 审计日期 | 2026-09-22；产品定位修订 2026-09-23                            |
| 文档状态 | Agent first 修订完成，可进入实施拆解                           |

本设计不是从零重写方案。它保留三个仓库中已经验证的 PubMed 检索、PMC BioC、开放获取解析、结构化抽取、任务跟踪和前端交互能力，将其组合成一个能够理解研究目标、自主规划检索、迭代验证并解释证据缺口的生物医学 Evidence Agent。证据平台不是独立产品终点，而是保证 Agent 结果可追溯、可审核和可复现的内部底座。

## 执行摘要

结论：产品采用 Agent first、platform backed 的形态。用户面对的是能够规划、检索、筛选、抽取、跨论文验证、说明不确定性并请求确认的 PubMiner Evidence Agent；内部由确定性工作流、typed tools、Evidence Schema、版本与人工审核机制约束其行动。以 PubMiner-webui 中较新的 Python 后端作为迁移起点，将其从前端仓库剥离到 PubMiner；PubMiner 成为 Agent orchestrator、业务后端与工作流引擎，PubEx 成为无业务状态的文献获取解析 SDK，PubMiner-webui 提供 Agent workspace、证据浏览与审核交互。

| **决策** | **建议**                                                                    | **原因**                                                             |
|----------|-----------------------------------------------------------------------------|----------------------------------------------------------------------|
| 产品定位 | PubMiner Evidence Agent                                                     | 以研究目标驱动自主检索与验证，同时输出可复核证据链                   |
| 后端主线 | 以 PubMiner-webui/PubMiner 的异步客户端与任务存储代码为 seed，迁入 PubMiner | 现有代码比独立 PubMiner 更新，已有 BioC、OA resolver、任务重试与缓存 |
| PubEx    | 冻结单文件程序；拆出兼容导入器，不继续扩展                                  | 具备历史批处理价值，但 SSL 全局绕过、CSV 状态和单文件架构不适合生产  |
| 数据层   | SQLite/CSV 迁移至 PostgreSQL + pgvector + 对象存储                          | Claim/Evidence/Review/Version/Provenance 需要事务、一致性与可重处理  |
| 智能层   | 有界 Agent loop + 确定性 workflow + typed tools                             | 保留自主规划和迭代能力，同时限制工具权限、预算和发布边界             |
| 发布门槛 | No Evidence No Claim；人工批准后才 Published                                | 保障 grounding、责任边界和可审计性                                   |

### 首个可交付结果

首个 12–16 周版本聚焦“胰腺癌预后 biomarker”一类任务：用户以自然语言给出研究目标，Agent 主动确认关键约束，生成可编辑计划，迭代调用 PubMed、PMC、PubTator、实体解析与证据抽取工具；当覆盖不足或出现冲突时改写查询并继续验证，最终返回带逐条原文引用、支持与反对证据、覆盖说明和待确认问题的研究结果，并把候选 Claim 送入人工审核。

| **成功指标** | **基线与目标**                                                |
|--------------|---------------------------------------------------------------|
| 效率         | 每条 validated record 从约 20–30 分钟降至 5 分钟以内          |
| 召回         | 内部 gold set 的关键论文 Recall@50/100 达到项目门槛           |
| Grounding    | 生产 Claim 100% 绑定原始 evidence span 与稳定 offset          |
| 可靠性       | 禁止模型自造 canonical identifier；关键错误率持续下降         |
| 可运营性     | 每个 run、tool call、prompt、model、rule 与 human edit 可追溯 |
| Agent 完成度 | 目标澄清、计划、工具调用、停止原因和最终综合均可见且可重放    |

## 1 文档范围与设计假设

本文覆盖 Agent 产品边界、三仓库代码审计、Agent loop、目标架构、领域模型、数据模型、API、LLM 与工具层、WebUI、质量评测、安全版权、运维、迁移计划和模块级改造清单。它不包含具体云厂商采购、最终 UI 视觉稿、完整数据库 DDL 或某一癌种的专家评分规则；这些应在实施阶段作为 ADR、migration 和 versioned rule package 补齐。

| **假设**                               | **设计含义**                                                    |
|----------------------------------------|-----------------------------------------------------------------|
| 初期团队规模有限                       | 采用模块化单体 + worker，不先拆微服务                           |
| 内部已有人工整理数据                   | 优先转成 gold set、seed claims 和回归数据                       |
| 全文许可不统一                         | 原文、许可与衍生知识分层存储和发布                              |
| 模型与供应商会变化                     | 业务只依赖 LLM Gateway 接口，不依赖某 SDK                       |
| 用户希望以研究目标而非固定表单驱动任务 | Agent 负责澄清目标、制定计划和选择工具；系统保存结构化 TaskSpec |
| 数据库建设以准确与可追溯为核心         | Recall 优先，但 production publication 必须经人工审核           |

## 2 代码审计基线

审计基于三个仓库默认分支的只读快照。提交 SHA 用于重现本次判断；后续代码变化应触发增量审计。

| **仓库**       | **提交**                                 | **现状概括**                                                                                     |
|----------------|------------------------------------------|--------------------------------------------------------------------------------------------------|
| PubMiner-webui | 13a24d29779bc5c170f5f68cde3785ea181913bd | Next.js 16 + React 19 前端；内嵌 FastAPI/Python package；SQLite task store；Zhipu 抽取；CSV 输出 |
| PubMiner       | 0de6716ed38ca87447edd72ef346f6974f1240e4 | 较早的模块化 CLI；多 LLM 配置；PDF/OCR/Sci-Hub；同步式流程；配置较多                             |
| PubEx          | ebb2a0eddd906726c0767f613c06d182b078e6bd | 单文件 PubMed 批量抓取器；History、引用关系、CSV 断点续传                                        |

### 2.1 PubMiner webui 审计

| **领域** | **现有资产**                                                                   | **缺口与风险**                                       | **处置**                                            |
|----------|--------------------------------------------------------------------------------|------------------------------------------------------|-----------------------------------------------------|
| 前端     | 搜索、PMID 导入、文章选择、任务进度、CSV 预览、OA PDF 状态                     | 单页工作台；没有 Evidence/Review/Admin；前端类型重复 | 保留组件与设计系统，重构为模块路由和服务端资源模型  |
| API      | /api/search、fetch-metadata、OA resolve/download、extract、task、retry、result | api_server.py 过大；未版本化；路由直接编排依赖       | 迁入 PubMiner/api/v1，拆 router/application/service |
| 任务     | SQLiteTaskStore、article/chunk 状态、retry、search session                     | 仅单机线程模型；表结构面向 CSV task                  | 迁移 PostgreSQL task/run/step，worker 执行          |
| 获取     | AsyncPubMedClient、PMC BioC、section parser、OA resolver                       | Document offset 和许可记录不足                       | 下沉 PubEx SDK，统一 Document Model                 |
| 抽取     | Pydantic 动态 schema、缓存、Zhipu client                                       | 供应商耦合；schema 面向列而非 Claim/Evidence         | 引入 LLM Gateway、TaskSchema、Evidence schema       |
| 数据库   | Prisma 示例只有 User/Post；实际后端另用 SQLite                                 | 双 ORM/双事实源风险                                  | 删除示例 Prisma schema；前端不直连业务 DB           |
| 测试     | pyproject 指向 tests，但仓库几乎无有效测试                                     | 关键解析、重试、抽取无回归保障                       | 建立 unit/contract/golden/regression 四层测试       |

### 2.2 PubMiner 审计

| **可保留**                                                                  | **需要重构**                                                                             | **建议删除或隔离**                                                                   |
|-----------------------------------------------------------------------------|------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| QueryManager、配置思路、文本预处理/section filter、extractor 抽象、示例场景 | 将 fetcher/downloader/extractor 迁为 adapters；改用 Pydantic v2 domain DTO；统一异步 I/O | SciHubDownloader 不进入产品路径；全局 SSL 弱化策略；Flask 依赖；与新版后端重复的实现 |
| 多模型 provider 配置经验、日志和输出字段映射                                | 实现独立 LLM Gateway 与 provider adapter；prompt/version 入库                            | 直接由业务类选择 provider、自由文本 JSON 解析、CSV 作为主数据                        |
| PDF/OCR 作为受控 fallback 的经验                                            | 改造成 permission-scoped ingestion tool，并记录 source/license/hash                      | 默认抓取未确认许可全文、浏览器下载作为主路径                                         |

### 2.3 PubEx 审计

PubEx 的价值在于成熟的批量 PubMed 元数据抓取、NCBI History、断点续传与引用字段；但实现是一个约数百行的单文件脚本，状态由 CSV 和本地日志隐式表达，还全局关闭证书验证。它适合被拆解，不适合继续作为 SDK 核心。

| **动作** | **对象**                                              | **说明**                                                             |
|----------|-------------------------------------------------------|----------------------------------------------------------------------|
| 保留     | 字段映射、History 分页、retry/backoff、断点续传语义   | 转为测试用例和适配层行为                                             |
| 重构     | PubMedFetcher                                         | 拆为 SearchClient、MetadataClient、CitationClient；返回 typed models |
| 新增     | Legacy CSV Importer                                   | 将既有 CSV 导入 documents/document_identifiers，并保留来源           |
| 删除     | ssl.\_create_unverified_context、全局 warning disable | 不得进入生产代码；TLS 问题应显式失败和治理                           |
| 冻结     | PubEx.py 新功能开发                                   | 仅接受安全修复；待迁移完成后归档                                     |

### 2.4 三仓库目标职责

| **仓库**       | **目标职责**                                                    | **明确不负责**                           |
|----------------|-----------------------------------------------------------------|------------------------------------------|
| PubMiner       | 领域模型、API、workflow、任务、Claim/Evidence、审核、发布、审计 | 前端组件、底层文档解析细节、任意代码执行 |
| PubEx          | 文献获取与 Document 解析 SDK；PubMed/PMC/PubTator adapters      | 用户、审核、业务 task、发布状态、Web API |
| PubMiner-webui | Research、Literature、Evidence、Review、Tasks、Admin UI         | 直连数据库、模型调用、文献解析           |

### 2.5 远端默认分支复核与工程规模

2026-09-22 通过只读 Git 远端重新 fetch 并校验 origin/main：三个仓库的远端 HEAD 均与本地审计 SHA 一致，且只有 main 远端分支可见。该结果说明本设计引用的是当时公开默认分支的最新状态，不包含未推送代码、私有分支或未授权仓库内容。

| **仓库**       | **远端 HEAD** | **最近提交日期** | **tracked files** | **代码规模**                       | **自动化测试**                       |
|----------------|---------------|------------------|-------------------|------------------------------------|--------------------------------------|
| PubMiner-webui | 13a24d2       | 2026-04-05       | 95                | Python 8,099 LOC；TS/TSX 6,979 LOC | 无测试代码；仅有 test_pmids 示例数据 |
| PubMiner       | 0de6716       | 2025-11-14       | 49                | Python 10,291 LOC                  | 0                                    |
| PubEx          | ebb2a0e       | 2025-10-14       | 4                 | Python 699 LOC                     | 0                                    |

复核后的关键判断没有改变，但实施优先级更明确：先建立测试与安全基线，再迁移功能。当前三个仓库合计约 18,000 行 Python 和约 7,000 行前端 TypeScript，却没有可执行的 unit、contract、golden 或 regression 测试套件；任何大规模重构都必须先用 characterization tests 固定现有行为。

### 2.6 结构热点与可验证证据

| **热点文件**                          | **规模**  | **代码证据**                                        | **设计影响**                                            |
|---------------------------------------|-----------|-----------------------------------------------------|---------------------------------------------------------|
| PubMiner-webui/PubMiner/api_server.py | 890 LOC   | 10 个业务路由；路由内创建依赖并调度 BackgroundTasks | 优先拆 router/application service；后台任务迁 worker    |
| pubminer/cli/main.py                  | 1,094 LOC | CLI 重复 search/session/task/LLM 编排               | CLI 与 API 共用 application commands，不再复制 workflow |
| pubminer/core/task_store.py           | 536 LOC   | 手写 SQLite DDL、ALTER 补列、JSON text 字段         | 以 Alembic + SQLAlchemy repositories 替代               |
| pubminer/core/extraction_tasks.py     | 549 LOC   | 直接依赖 SQLiteTaskStore 与 ZhipuExtractor          | 引入 ports；workflow 不依赖 provider/store 实现         |
| pubminer/fetcher/pubmed_client.py     | 749 LOC   | 搜索、metadata、citation 等职责集中                 | 拆 SearchClient、MetadataClient、CitationClient         |
| pubminer/downloader/oa_pdf.py         | 888 LOC   | 多来源解析、下载、许可与缓存混合                    | 拆 resolver、source adapters、policy、cache             |
| tasks-section.tsx                     | 954 LOC   | 轮询、状态映射、诊断与操作同组件                    | 拆 task query、step timeline、diagnostics、actions      |
| search-results-section.tsx            | 861 LOC   | 分页、筛选、OA 解析和批量下载混合                   | 拆 results table、filters、OA panel、selection model    |
| PubMiner/core/pdf_downloader.py       | 1,891 LOC | 内置 Sci-Hub 路径和多种下载策略                     | 生产路径移除 Sci-Hub；合法 OA fallback 独立化           |
| PubEx/PubEx.py                        | 699 LOC   | 单文件、CSV 状态、全局关闭 TLS 校验                 | 冻结并拆 legacy importer；安全问题先修                  |

### 2.7 必须先处理的安全与架构债务

| **级别** | **问题**                           | **代码位置**                                  | **完成定义**                                                                      |
|----------|------------------------------------|-----------------------------------------------|-----------------------------------------------------------------------------------|
| P0       | 全局禁用 TLS/证书验证              | PubEx.py；PubMiner/core/pubmed_fetcher.py     | 删除全局 override；证书错误分类、可观测、不可静默降级                             |
| P0       | Sci-Hub 进入默认产品下载链路       | PubMiner/core/pdf_downloader.py 与配置        | 生产构建无相关代码/配置；仅保留合法 OA source policy                              |
| P0       | 几乎无自动化测试                   | 三个仓库                                      | 最小 characterization suite 覆盖 PubMed parse、BioC parse、task state、CSV import |
| P1       | 模型供应商硬耦合                   | ZhipuExtractor 在 API/CLI/workflow 直接实例化 | 业务只依赖 LLMPort；Zhipu 变成 provider adapter                                   |
| P1       | 进程内 BackgroundTasks 执行长任务  | api_server.py                                 | 任务提交与执行分离；重启后任务可恢复                                              |
| P1       | SQLite 与 CSV 承担系统事实源       | task_store.py 与 exporter                     | PostgreSQL 成为主数据；CSV 只作导出                                               |
| P1       | 前端 Prisma 示例与业务 SQLite 并存 | prisma/schema.prisma                          | 删除示例表与无效脚本；前端不拥有业务数据库                                        |

## 3 Agent 产品定义与用户场景

### 3.1 产品定位

PubMiner Evidence Agent 是面向生物医学研究团队与数据库建设者的研究智能体。用户通过自然语言提出研究目标，Agent 负责澄清约束、制定计划、选择工具、监测覆盖、处理冲突并综合结论；后台证据底座负责保存 Document、Passage、Entity、Claim、Evidence、Review 与完整 provenance。产品体验以 Agent 为中心，可信性由平台能力提供，而不是把聊天文本直接当作研究结论。

| **角色**        | **主要任务**                                       | **权限边界**                             |
|-----------------|----------------------------------------------------|------------------------------------------|
| Researcher      | 与 Agent 对话、确认计划、浏览证据、追问和导出报告  | 不能发布或修改已批准事实                 |
| Curator         | 审核 evidence、修订 claim、合并/拆分实体           | 可提交审批，不自动发布                   |
| Senior reviewer | 解决冲突、批准、废弃或退回                         | 可改变 reviewed/approved 状态            |
| Admin           | 管理 schema、ontology、prompt、model、rule、source | 不能绕过审计日志                         |
| Evidence Agent  | 规划、选择工具、评估覆盖、提出下一步和综合结果     | 受预算、工具权限、schema 与发布门禁约束  |
| System worker   | 执行 typed tool 和确定性 workflow step             | 不能自行规划、删除生产数据或自动 publish |

### 3.2 核心场景

Disease: Pancreatic ductal adenocarcinoma  
Task: Prognostic biomarker  
Year: 2020–2026  
Validation: Independent cohort required

Agent 将自然语言目标转换为结构化 TaskSpec，在关键约束缺失时提出澄清问题；随后生成多个 search intent，检索并筛选文献，抽取 biomarker、疾病、角色、方向、endpoint、cohort、assay 与统计量，调用 resolver 返回 canonical ID，形成 evidence-backed candidate claims。当证据覆盖不足、独立验证缺失或出现矛盾时，Agent 生成新的检索动作；满足停止条件后综合结论并把高风险项送入 curator queue。

| **阶段**  | **用户可见输出**                       | **持久化对象**                         |
|-----------|----------------------------------------|----------------------------------------|
| Clarify   | 目标理解、缺失约束和待确认问题         | agent_session、message、task_draft     |
| Plan      | 任务解释、检索意图、限制条件           | task、task_schema_version、plan        |
| Search    | 查询式、召回数、来源与批次             | search_run、query、document_identifier |
| Screen    | relevant/irrelevant/uncertain 与理由   | screening_decision                     |
| Extract   | 结构化字段与高亮原文                   | mention、extraction、passage           |
| Normalize | 候选 canonical entity 与歧义           | entity、alias、identifier、resolution  |
| Verify    | support/contradict/no effect/uncertain | claim、evidence、verification          |
| Review    | Accept/Edit/Reject/Needs review        | review、revision、provenance_event     |
| Publish   | 版本化知识记录                         | publication、claim_status              |

### 3.3 Agent 体验原则

| **原则**     | **产品行为**                                                                      |
|--------------|-----------------------------------------------------------------------------------|
| 目标驱动     | 用户描述研究目标，Agent 将其转成可检查的 TaskSpec，而不是要求用户先理解数据库字段 |
| 计划可见     | 执行前展示计划、数据源、关键假设和预算；用户可修改或批准                          |
| 行动可解释   | 每次工具调用显示目的、输入摘要、结果数量和对计划的影响，不展示伪造的内部思维过程  |
| 证据先于结论 | 最终回答的关键陈述必须引用 EvidenceSpan，并区分支持、反对、无效应与不确定         |
| 主动但有界   | Agent 可改写查询和追加验证，但受轮次、成本、来源、权限和停止条件约束              |
| 人在关键节点 | 高风险歧义、冲突结论和发布动作必须由用户或 curator 确认                           |

### 3.4 非目标

- MVP 不做任意 shell 或 general-purpose code execution。

- MVP 采用一个有界 Evidence Agent，不引入多 Agent 协作、角色扮演或自我修改。

- 不把 Neo4j、自动假设生成、fine-tuning 作为首期依赖。

- 不把 LLM confidence 当作事实真值或发布依据。

- 不重新发布无许可全文；公开面仅发布允许范围内的 snippet 与衍生结构化知识。

- 不要求第一版覆盖所有 biomedical relation；先做 biomarker task family。

## 4 设计原则与关键 ADR

| **编号** | **决策**                                                            | **理由**                                                     |
|----------|---------------------------------------------------------------------|--------------------------------------------------------------|
| ADR-001  | 模块化单体 + 独立 worker                                            | 降低分布式复杂度，同时隔离长任务                             |
| ADR-002  | PostgreSQL 为系统事实源                                             | 事务、JSONB、FTS、版本、审计和 pgvector 可满足 MVP           |
| ADR-003  | Claim 与 Evidence 分离                                              | 同一 claim 可有支持、相反、无效应和不确定证据                |
| ADR-004  | Document 原文与 derived annotation 分离                             | 支持重处理、模型比较、许可管理和不可变来源                   |
| ADR-005  | 有界 Agent orchestrator + typed tools + deterministic state machine | Agent 决定研究动作，工具和状态转换保持可测试、可授权和可回放 |
| ADR-006  | identifier 只能由 resolver/tool 返回                                | 禁止模型猜 NCBI Gene、MeSH、UniProt 等 ID                    |
| ADR-007  | pipeline release 整体版本化                                         | 模型、prompt、schema、normalizer、rule 共同决定结果          |
| ADR-008  | 人工批准后发布                                                      | 建立生产知识的责任边界                                       |
| ADR-009  | 先 PostgreSQL FTS + pgvector                                        | 规模和查询压力证明需要时再上 OpenSearch/Neo4j                |

## 5 目标系统架构

目标形态采用 Agent 交互层、应用工作流层和基础设施集成层。PubMiner-webui 提供对话、计划、行动轨迹、证据与审核界面；PubMiner 中的 Agent Orchestrator 维护目标、计划、覆盖状态、预算和下一动作，确定性 workflow 负责可恢复执行；worker 执行长任务，PubEx 作为 package 提供文献获取解析能力。所有生产状态进入 PostgreSQL，原始 XML、PDF、BioC 和导出文件进入对象存储，Redis 只承担队列与短期缓存。

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr class="header">
<th><strong>交互层</strong></th>
<th><strong>应用与工作流层</strong></th>
<th><strong>基础设施与集成层</strong></th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>PubMiner-webui<br />
Agent Workspace · Evidence · Review · Tasks · Admin</td>
<td>FastAPI API v1<br />
Agent Orchestrator<br />
Workflow State Machine<br />
Policy/Rule Engine<br />
LLM Gateway</td>
<td>PostgreSQL + pgvector<br />
Redis queue/cache<br />
S3/MinIO<br />
NCBI/PMC/PubTator<br />
Model providers</td>
</tr>
<tr class="even">
<td>只通过 versioned REST/SSE</td>
<td>只依赖 domain ports</td>
<td>通过 typed adapters 与 source policy</td>
</tr>
</tbody>
</table>

### 5.1 模块依赖规则

```text
api -> application -> domain
agent -> workflows -> application -> domain
workers -> workflows -> application -> domain
integrations -> domain ports
infrastructure -> repositories/interfaces
PubEx -> document DTOs and source adapters
webui -> /api/v1 only
```

domain 不得导入 FastAPI、SQLAlchemy、OpenAI、Entrez 或前端类型。Agent Orchestrator 只能选择 registry 中允许的 typed tool 和 workflow command，不直接执行网络请求、SQL 或任意代码。API 不直接写 ORM model；它调用 application command/query handler。

### 5.2 建议目录

```text
PubMiner/
  src/pubminer/
    domain/{agents,documents,entities,claims,evidence,reviews,tasks}
    application/{commands,queries,services,policies}
    agents/{orchestrator,planner,coverage,stopping,synthesis}
    workflows/{mining,verification,reprocessing}
    integrations/{ncbi,pubtator,llm,storage}
    infrastructure/{db,queue,cache,telemetry}
    api/v1/{agent_sessions,tasks,documents,claims,evidence,reviews,search}
  migrations/  prompts/  rules/  tests/

PubEx/
  src/pubex/{models,parsers,clients,normalizers}
  tests/{unit,contract,golden}

PubMiner-webui/
  src/app/{agent,evidence,review,tasks,admin}
  src/features/  src/shared/api/
```

## 6 领域模型

| **聚合**     | **核心字段**                                                           | **不变量**                                          |
|--------------|------------------------------------------------------------------------|-----------------------------------------------------|
| AgentSession | goal、messages、plan versions、budget、coverage、stop reason           | 每个动作关联 plan step、tool call 或 human decision |
| Document     | source identifiers、metadata、license、content hash、sections/passages | 每个 passage 有稳定位置与 source text               |
| Entity       | type、canonical name、identifiers、aliases、ontology version           | canonical identifier 来源可追溯，不能由 LLM 创建    |
| Claim        | subject、predicate、object/value、context、signature、status           | canonical signature 唯一表达语义聚类键              |
| Evidence     | claim、document、passage、polarity、study attributes、statistics       | 必须指向 passage；不得只有 summary                  |
| Review       | target、decision、before/after、reviewer、reason                       | 修改追加记录，不覆盖模型输出                        |
| Task         | schema、request、state、priority、owner                                | 状态转换受 workflow 定义约束                        |
| Run          | pipeline release、step attempts、tool calls、cost、trace               | 可重放并区分 source 与 derived output               |

### 6.1 Document Model 与稳定定位

```text
Document
├─ metadata
├─ sections[]
│  └─ paragraphs[]
│     └─ sentences[]
└─ annotations[]
```

稳定定位至少包含 document_id、content_version、section_id、paragraph_id、sentence_id、start_char、end_char。offset 必须相对于已保存且 content-hash 固定的 canonical text；清洗算法变化应产生新 content_version，而不是静默改变 offset。

### 6.2 Claim 与 Evidence

```text
GENE:ABC1 | PROGNOSTIC | DISEASE:PDAC | HIGH_EXPRESSION | POOR_OS
```

| **对象**   | **示例**                          | **说明**                             |
|------------|-----------------------------------|--------------------------------------|
| Claim      | ABC1 高表达与 PDAC 较差总生存相关 | 规范化命题，不等同于某篇论文结论     |
| Evidence A | SUPPORT，multivariate HR 2.1      | 保留原文 span、cohort、assay、统计量 |
| Evidence B | NO_EFFECT，验证队列未显著         | 不能丢弃“不支持”结果                 |
| Evidence C | CONTRADICT，高表达与较好 OS 相关  | 触发 conflict review                 |

### 6.3 Agent Session 与行动记录

AgentSession 保存用户目标、澄清记录、TaskSpec、计划版本、行动建议、工具调用、覆盖评估、预算消耗、用户干预和停止原因。AgentMessage 是交互记录，不是事实源；可发布知识只能来自通过 schema 校验并绑定 EvidenceSpan 的领域对象。每个 AgentAction 必须指向触发它的 plan step，并记录预期信息增益和实际结果摘要。

### 6.4 发布状态机

```text
CANDIDATE -> REVIEWED -> APPROVED -> PUBLISHED -> DEPRECATED
     |            |
     +-> REJECTED +-> NEEDS_REVISION
```

Agent 只能创建 CANDIDATE 和提交 review request。APPROVED 与 PUBLISHED 需要显式角色权限。已发布记录的修订通过新 version 完成；禁止 worker 直接 UPDATE approved claim 或 DELETE production data。

## 7 数据库设计

MVP 使用 PostgreSQL。ORM 推荐 SQLAlchemy 2 + Alembic；读写模型可共享数据库但分离 repository。向量只是检索索引，不是事实源。大文本和原始文件进入对象存储，数据库保存内容哈希、位置、许可与 URI。

| **表组** | **主要表**                                                                                            | **说明**                                  |
|----------|-------------------------------------------------------------------------------------------------------|-------------------------------------------|
| Agent    | agent_sessions, agent_messages, agent_plans, agent_actions, coverage_snapshots                        | 保存目标、计划版本、行动、预算与停止原因  |
| 文献     | documents, document_identifiers, document_versions, sections, passages, document_assets               | PMID/PMCID/DOI 去重；原文分版本           |
| 实体     | entities, entity_aliases, entity_identifiers, mentions, resolutions                                   | 支持多 ontology version 与歧义            |
| 知识     | claims, claim_contexts, evidence, evidence_statistics, claim_clusters                                 | Claim/Evidence 分离；signature 建唯一索引 |
| 流程     | tasks, task_steps, runs, run_steps, tool_calls, search_runs                                           | 记录状态、重试、输入输出摘要              |
| 质量     | reviews, review_revisions, evaluation_sets, evaluation_items                                          | 人审修改成为 gold data                    |
| 版本     | prompt_versions, model_versions, schema_versions, ontology_versions, rule_versions, pipeline_releases | 所有 derived output 绑定 release          |
| 治理     | provenance_events, permissions, source_policies, licenses                                             | append-only 事件与版权策略                |

### 7.1 关键表字段

| **表**            | **关键字段**                                                                                                                                 |
|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| agent_sessions    | id, user_id, goal, task_schema_id, status, budget_jsonb, stop_reason, created_at, updated_at                                                 |
| agent_actions     | id, session_id, plan_version, action_type, tool_call_id, rationale_summary, expected_gain, status                                            |
| claims            | id, subject_entity_id, predicate, object_entity_id/object_value, disease_id, context_jsonb, canonical_signature, status, version             |
| evidence          | id, claim_id, document_id, passage_id, polarity, study_design, population_jsonb, assay_jsonb, effect_jsonb, extraction_run_id, review_status |
| passages          | id, document_version_id, section_path, start_char, end_char, source_text, text_hash, embedding                                               |
| runs              | id, task_id, pipeline_release_id, status, started_at, ended_at, cost, trace_id                                                               |
| provenance_events | id, aggregate_type, aggregate_id, event_type, actor_type, actor_id, payload_jsonb, occurred_at                                               |

### 7.2 去重与索引

- Document：PMID、PMCID、DOI 唯一索引；缺失时用 normalized title + year + authors 指纹并进入人工确认。

- Claim：canonical_signature + context schema version；不要用 embedding 作为唯一去重依据。

- Evidence：document_version_id + passage_id + claim_id + extraction_run_id；允许不同 pipeline 并存。

- 检索：GIN(tsvector) 支持关键词，pgvector 支持语义召回，B-tree 支持状态、PMID、时间与外键。

- 所有可变业务对象带 version 或 xmin 乐观锁，避免并发审核覆盖。

### 7.3 从 SQLite CSV 迁移

| **来源**                        | **迁移目标**                          | **规则**                                          |
|---------------------------------|---------------------------------------|---------------------------------------------------|
| search_sessions                 | search_runs + search_results          | 保存原 query、PMID 顺序、时间和 source            |
| tasks/task_articles/task_chunks | tasks + runs + task_steps + run_steps | 状态映射并保留旧 task_id                          |
| extraction_cache                | derived_artifacts/cache_entries       | 增加 prompt/model/schema/text hash                |
| CSV result                      | documents + legacy_extractions        | 先原样存 archive，再映射 typed fields；不直接发布 |
| PubEx CSV                       | legacy_import_batches + documents     | 字段映射报告必须可审计                            |

## 8 Agent 与工作流设计

系统分为外层 Agent loop 和内层确定性 workflow。外层 Agent 根据研究目标、当前证据覆盖和预算选择下一项受控动作；内层 workflow 执行检索、解析、筛选、抽取、标准化和验证，并返回结构化结果。Agent 不直接操作网络、数据库或文件系统，也不能绕过状态机。

| **Agent loop** | **职责**                                | **输出**                                 |
|----------------|-----------------------------------------|------------------------------------------|
| UNDERSTAND     | 解析目标并识别缺失条件                  | TaskSpec draft 或 clarification question |
| PLAN           | 制定多阶段研究计划和预算                | versioned plan 与 search intents         |
| ACT            | 选择一个允许的 tool 或 workflow command | AgentAction 与 typed result              |
| OBSERVE        | 更新覆盖、冲突、失败和成本状态          | CoverageSnapshot                         |
| REFLECT        | 判断继续检索、改写查询、请求人工或停止  | next action 与理由摘要                   |
| SYNTHESIZE     | 生成逐条引用证据的结论和缺口说明        | Evidence Report 与 candidate claims      |

| **Step**  | **输入**                   | **输出**                               | **失败策略**                         |
|-----------|----------------------------|----------------------------------------|--------------------------------------|
| PLAN      | task request + TaskSchema  | structured plan + intents              | schema validation；人工补充关键约束  |
| SEARCH    | intents + source policy    | search runs + document ids             | 限流、重试、query rewrite            |
| HYDRATE   | document ids               | metadata + abstract/full text          | 保留 partial；许可不足降级 abstract  |
| SCREEN    | document + criteria        | relevant/irrelevant/uncertain          | 低置信或 uncertain 进入全文/人工     |
| EXTRACT   | document passages          | typed extraction + spans               | JSON schema retry；禁止无 span claim |
| NORMALIZE | mentions                   | resolver candidates + canonical entity | 歧义送 review；禁止猜 ID             |
| VERIFY    | candidate claim + evidence | polarity/entailment/attributes         | 冲突与缺失均显式记录                 |
| AGGREGATE | verified evidence          | claim cluster + coverage               | signature + rule-based grouping      |
| REVIEW    | queue item                 | decision + revision                    | 乐观锁；记录 before/after            |
| PUBLISH   | approved version           | published claim                        | 权限与完整性门禁                     |

### 8.1 Agent 自主性与停止条件

| **控制项**   | **规则**                                                                         |
|--------------|----------------------------------------------------------------------------------|
| 允许自主决定 | 查询改写、来源选择、文献批次、全文请求、验证顺序和低风险重试                     |
| 必须请求确认 | 研究目标发生实质变化、预算显著增加、实体歧义影响结论、证据冲突无法解析           |
| 禁止动作     | 任意代码执行、未注册网络请求、猜测 identifier、修改 approved claim、自动 publish |
| 正常停止     | 关键问题均有证据覆盖；新增检索边际收益低；达到用户设定的充分性阈值               |
| 受限停止     | 达到轮次、成本、时间或来源限额；必须明确报告未完成范围                           |
| 失败停止     | 必要来源持续不可用、schema 无法满足或权限不足；返回可恢复状态和建议              |

### 8.2 Query Planner

```json
{
  "disease": "pancreatic cancer",
  "task": "biomarker_disease",
  "role": "prognostic",
  "validation_requirement": "independent_validation",
  "publication_types": ["clinical study", "cohort"]
}
```

Planner 产出 broad discovery、clinical evidence、survival evidence、validation evidence 和 review/citation expansion 等 intent。每次 query rewrite 都保存父查询、理由、差异和结果覆盖；达到预算、覆盖或边际收益阈值后停止。

### 8.3 Screening

```json
{"relevant": true, "confidence": 0.91, "reasons": ["PDAC", "survival outcome", "biomarker expression"], "study_type": "retrospective_cohort", "needs_fulltext": true}
```

Screening 优化目标优先降低 false negative。RELEVANT 进入抽取，IRRELEVANT 保留理由，UNCERTAIN 自动请求全文或人工复核。模型 confidence 仅用于队列优先级，不用于事实判断。

### 8.4 抽取 标准化与跨论文验证

| **模块**      | **LLM 允许做**                                  | **LLM 禁止做**                   |
|---------------|-------------------------------------------------|----------------------------------|
| Extraction    | 从给定 passage 填充 schema、返回 evidence span  | 脱离原文补全事实或统计量         |
| Normalization | 在 resolver 候选间基于上下文消歧                | 生成数据库 identifier            |
| Verification  | 判断原文是否 entail claim、方向/endpoint/显著性 | 把 confidence 转成 truth         |
| Synthesis     | 总结支持/冲突/缺口并引用 evidence               | 强制合成唯一结论或隐藏 no-effect |

跨论文验证先按 canonical signature 聚类 Claim，再比较疾病亚型、population、assay、endpoint、分析类型和随访范围，避免把不可比研究强行合并。Agent 应主动搜索独立验证、相反结果和 no effect 证据；综合输出必须列出各极性证据、研究独立性、不可比较原因和尚未覆盖的问题。

### 8.5 Human in the loop

Review Queue 按 low confidence、conflict、high impact、random QA、stale ontology、independent validation 等策略排序。审核界面左侧显示原文与高亮 span，右侧显示结构化 Claim、entity resolution、study attributes、statistics 和历史版本；Accept/Edit/Reject/Needs Review 均要求可追溯的 decision。

## 9 LLM Gateway Prompt 与工具

| **接口**            | **用途**                        | **必备元数据**                            |
|---------------------|---------------------------------|-------------------------------------------|
| generate            | 非结构化辅助文本                | provider, model, temperature, token usage |
| structured_generate | schema constrained output       | schema version, validation attempts       |
| embed               | article/passage/claim embedding | embedding model/version/dimension         |
| rerank              | 检索候选排序                    | query, candidates, model, score           |

Gateway 通过 provider adapters 支持 OpenAI、Anthropic、Gemini、Azure、Zhipu 或本地模型。业务代码不 import 厂商 SDK。每个调用记录 model_version、prompt_version、schema_version、input hash、output hash、tokens、cost、latency 与 error category。

### 9.1 Prompt 资产

```text
prompts/
  agent-policy/v1/
  planner/v1/
  coverage/v1/
  screening/v1/
  extraction/biomarker/v2/
  verification/v1/
  synthesis/v1/
```

每个 prompt 包含 name、version、schema_version、model_requirements、examples、negative cases 和 test_cases。production 只能引用已发布 pipeline release，不能隐式使用 latest。

### 9.2 Tool Registry

| **Tool**                 | **权限**                        | **输出**                        |
|--------------------------|---------------------------------|---------------------------------|
| PubMedSearchTool         | read external metadata          | SearchResultPage                |
| PMCFulltextTool          | read licensed/allowed content   | DocumentVersion + LicenseRecord |
| PubTatorTool             | read annotations                | EntityCandidates + Relations    |
| EntityResolverTool       | read ontology                   | CanonicalEntityCandidate\[\]    |
| ExtractionTool           | create derived candidate only   | StructuredExtraction            |
| CreateCandidateClaimTool | create candidate                | Claim CANDIDATE                 |
| SubmitReviewTool         | create review request           | ReviewItem                      |
| AskHumanTool             | pause session and request input | ClarificationRequest            |
| PublishClaimTool         | privileged human role only      | PublishedClaimVersion           |

## 10 API 设计

API 使用 /api/v1，资源名复数，长任务返回 202 + task_id。状态更新首选 SSE；WebSocket 只在双向实时协作成为刚需时加入。所有 mutation 支持 request id / idempotency key；分页使用 cursor。

| **方法** | **路径**                                  | **用途**                        |
|----------|-------------------------------------------|---------------------------------|
| POST     | /api/v1/agent/sessions                    | 创建 Evidence Agent 会话        |
| POST     | /api/v1/agent/sessions/{id}/messages      | 发送研究目标、追问或确认        |
| GET      | /api/v1/agent/sessions/{id}               | 读取计划、覆盖、预算与当前状态  |
| GET      | /api/v1/agent/sessions/{id}/events        | SSE 返回行动和证据事件          |
| POST     | /api/v1/agent/sessions/{id}/actions/pause | 暂停或恢复 Agent                |
| POST     | /api/v1/tasks                             | 创建研究或重处理任务            |
| GET      | /api/v1/tasks/{id}                        | 任务状态和可见步骤              |
| POST     | /api/v1/tasks/{id}/actions/cancel         | 请求安全取消                    |
| GET      | /api/v1/tasks/{id}/events                 | SSE 进度事件                    |
| POST     | /api/v1/search                            | 传统文献搜索                    |
| GET      | /api/v1/documents/{id}                    | 元数据、版本、许可与 sections   |
| GET      | /api/v1/claims                            | 按疾病/实体/角色/状态筛选       |
| GET      | /api/v1/claims/{id}/evidence              | 支持、相反、无效应、不确定证据  |
| POST     | /api/v1/reviews/{id}/decision             | Accept/Edit/Reject/Needs Review |
| GET      | /api/v1/schemas                           | 可用 TaskSchema 和版本          |

### 10.1 创建 Agent 会话示例

```http
POST /api/v1/agent/sessions
Content-Type: application/json

{
  "goal": "寻找 2020 年以来胰腺癌预后 biomarker，并确认是否存在独立队列验证",
  "limits": {"max_articles": 200, "max_cost_usd": 20}
}

201 Created
{"session_id": "agt_...", "status": "CLARIFYING", "next": "ASK_HUMAN"}
```

### 10.2 错误模型

```json
{"error": {"code": "ONTOLOGY_AMBIGUOUS", "message": "Multiple gene candidates", "retryable": false, "details": {}}, "request_id": "req_..."}
```

错误必须区分 retryable、user action required、source unavailable、policy denied 与 invariant violation。不得把 provider 原始错误或 secret 返回浏览器。

## 11 Agent first WebUI 信息架构

| **模块**        | **主任务**                                       | **关键视图**                                            |
|-----------------|--------------------------------------------------|---------------------------------------------------------|
| Agent Workspace | 提出目标、确认计划、观察行动、追问和接收综合结果 | Conversation、Plan、Activity、Coverage、Evidence Report |
| Literature      | 传统搜索与收藏                                   | Filters、Results、Saved searches、Document detail       |
| Evidence        | 按 Disease/Biomarker/Claim 浏览                  | Evidence matrix、study table、conflict view             |
| Review          | 生产审核                                         | Pending、Uncertain、Conflict、High impact、Random QA    |
| Tasks           | 查看真实执行过程                                 | SEARCH/SCREEN/EXTRACT/VERIFY step、retry、cost          |
| Admin           | 配置系统资产                                     | Schemas、Ontologies、Prompts、Models、Rules、Sources    |

### 11.1 Agent Workspace

桌面端主入口采用 Agent Workspace，而不是任务配置表单。左侧保留对话与澄清问题，中间显示可编辑研究计划、当前行动、来源、覆盖和成本，右侧显示与当前结论关联的 EvidenceSpan、论文属性及冲突状态。用户可以批准计划、暂停、继续、修改目标、限制来源、要求查找反证或把具体项送入审核。界面展示行动理由摘要和工具结果，不模拟或暴露模型的隐藏思维过程。

| **区域**     | **必须能力**                                                |
|--------------|-------------------------------------------------------------|
| Conversation | 研究目标、Agent 澄清、用户追问、结论摘要与未决问题          |
| Plan         | 计划版本、步骤状态、预算、用户批准与范围变更                |
| Activity     | 真实 tool/workflow 事件、来源、输入摘要、命中数、错误与重试 |
| Coverage     | 关键问题、支持/反对/无效应数量、独立验证和证据缺口          |
| Evidence     | 点击结论定位原文 span，查看实体解析、统计量和研究属性       |

### 11.2 现有前端迁移

| **现有文件**                 | **迁移目标**                       | **处理**                                                           |
|------------------------------|------------------------------------|--------------------------------------------------------------------|
| search-section.tsx           | features/literature/search         | 保留 query builder，改用 /api/v1/search                            |
| search-results-section.tsx   | features/literature/results        | 保留列表/筛选/分页；Document ID 替代裸 PMID 状态                   |
| extraction-setup-section.tsx | features/agent/task-spec           | 从 custom columns 改为 Agent 澄清后生成的 TaskSchema + constraints |
| tasks-section.tsx            | features/tasks                     | 保留诊断体验，改为 step/run event model                            |
| results-section.tsx          | features/evidence/legacy-export    | 短期保留 CSV；主入口改为 Claim/Evidence                            |
| store.ts                     | feature-local stores + query cache | 拆分大 store；服务端状态由 query library 管理                      |
| lib/api.ts                   | generated API client               | 由 OpenAPI 生成，消除手工重复类型                                  |

### 11.3 Review UI

桌面端采用双栏：左侧为 Document viewer，显示 section 路径、原文与 evidence highlight；右侧为 Claim editor，展示 entity、disease、predicate、direction、endpoint、cohort、assay、statistics、normalization candidates 和 verification notes。底部固定操作区只提供 Accept、Edit and Accept、Reject、Needs Review。移动端只支持阅读，不建议批准。

## 12 Evidence strength 与规则引擎

LLM 只抽取 study attributes，EvidenceRuleEngine 依据领域专家维护的版本化规则计算等级或分数。规则输出必须包含每个加减项与 rule_version，便于解释和回放。

| **属性**                          | **示例权重** |
|-----------------------------------|--------------|
| systematic review / meta-analysis | 5            |
| prospective cohort                | 4            |
| independent validation cohort     | 4            |
| retrospective cohort              | 3            |
| case-control                      | 2            |
| in vitro                          | 1            |
| multivariate adjusted             | +1           |
| independent replication           | +1           |
| large cohort                      | +1           |
| very small sample                 | -1           |
| abstract only                     | -1           |

这些数值只是示例，不应直接进入生产。首个正式规则包应由领域专家给出阈值、适用 task schema、冲突处理和校准数据，并发布为 evidence-rule-v1。

## 13 检索与索引策略

| **阶段**     | **实现**                                                                     |
|--------------|------------------------------------------------------------------------------|
| MVP 外部召回 | PubMed E-utilities + PubTator relation/entity search + PMC 可用性            |
| 本地关键词   | PostgreSQL tsvector/tsquery + GIN；字段加权 title/abstract/body              |
| 本地语义     | pgvector passage embedding；hybrid rank 合并 BM25-like/semantic score        |
| 重排         | contextual summarization + LLM/cross-encoder rerank，用于小候选集            |
| 扩展         | citation traversal、review-to-primary tracing、independent replication query |
| 未来         | 规模或复杂筛选压测证明瓶颈后引入 OpenSearch                                  |

检索评估首先关注 Recall@10/20/50/100 与关键文献漏检；screening 单独衡量 precision、recall、F1 和 false-negative rate。检索与筛选不能混成一个“最终准确率”。

## 14 缓存 重处理 与版本发布

缓存 key 至少包含 content_hash、tool_version、model_version、prompt_version、schema_version 与 normalization/rule version。缓存结果不是生产事实；当 policy、schema 或 source content 变化时必须失效或进入 revalidation。

| **对象**            | **版本策略**                                 |
|---------------------|----------------------------------------------|
| Source document     | 不可覆盖；新内容产生 document_version        |
| Extraction          | v1/v2 并存，分别绑定 run 与 pipeline release |
| Prompt/model/schema | 不可变发布；新版本新记录                     |
| Claim               | 业务 version；published 后修改产生新 version |
| Ontology mapping    | 绑定 ontology_version；升级时批量 re-resolve |
| Evidence rule       | 重新计算派生 score，不覆盖历史 score         |

```text
pipeline-release-1.3 = model:gpt-x + prompt:extract-v7 + schema:biomarker-v2 + normalizer:pubtator-2026-x + rule:evidence-v3
```

## 15 安全 版权 与治理

| **风险**                       | **控制**                                                                         |
|--------------------------------|----------------------------------------------------------------------------------|
| Prompt injection in paper text | 文档内容视为不可信数据；tool instructions 与文献正文隔离                         |
| 越权发布/删除                  | RBAC/ABAC + permission-scoped commands + human approval                          |
| 模型泄露敏感配置               | secret manager；日志脱敏；前端永不接触 provider key                              |
| 全文版权                       | 记录 source、license、retrieval method、usage permission；公开只展示许可允许内容 |
| TLS/下载风险                   | 禁止全局跳过证书校验；域名 allowlist；大小/MIME/hash 校验                        |
| 审计篡改                       | append-only provenance；关键发布事件不可变与定期备份                             |
| 数据删除                       | 软删除/废弃状态；物理删除走受控 retention job                                    |

PMC 可访问不等于可自由再分发。下载与公开展示必须依据具体数据集和文章许可；Open Access Subset 与其他 PMC collection 的使用条件应分别处理。

## 16 可观测性 成本与 SLO

| **层级** | **指标**                                                                          |
|----------|-----------------------------------------------------------------------------------|
| Workflow | searches、retrieved、screened、accepted、fulltext fetched、step retries、failures |
| LLM      | calls、tokens、cost、latency、schema failure、grounding failure                   |
| Claim    | support/contradict/no-effect/uncertain 数、review age、edit history               |
| 业务     | minutes per validated record、acceptance rate、edit rate、critical error rate     |
| 系统     | API p95、queue wait、worker utilization、DB locks、source error rate              |
| 单位经济 | cost per task、article、candidate claim、validated claim                          |

建议 MVP SLO：API 非长任务读请求 p95 \< 800 ms；任务事件延迟 \< 5 s；已入队任务不丢失；每个 published claim 均可在 UI 打开 trace 并定位 evidence span。具体数值在首轮压测后校准。

## 17 测试与评测

| **层级**   | **对象**                                              | **门禁**                       |
|------------|-------------------------------------------------------|--------------------------------|
| Unit       | parser、normalizer、signature、rule、state transition | PR 必须通过                    |
| Contract   | PubMed、PMC、PubTator、LLM schema、storage            | 模拟 + 定期真实 smoke          |
| Golden     | 固定论文的 entity、claim、evidence span、statistics   | pipeline release 必须通过      |
| Regression | model/prompt/workflow/ontology/rule 变化              | 与当前 production release 对比 |
| E2E        | task create → review → publish                        | staging 必须通过               |
| Security   | permissions、injection、unsafe download、secret leak  | 发布前门禁                     |

| **评测面**    | **指标**                                                                            |
|---------------|-------------------------------------------------------------------------------------|
| Agent         | TaskSpec 正确率、plan completion、tool success、有效查询改写率、正常/受限停止准确率 |
| Retrieval     | Recall@10/20/50/100                                                                 |
| Screening     | Precision/Recall/F1；重点 FNR                                                       |
| Extraction    | Entity F1、Relation F1、Attribute F1                                                |
| Normalization | Top-1/Top-k accuracy                                                                |
| Evidence      | span precision/recall；citation entailment                                          |
| Verification  | support/contradict/no-effect/uncertain macro F1                                     |
| Business      | minutes/validated record、human edit rate、critical error rate                      |

## 18 实施路线图

| **阶段**           | **周期** | **范围**                                                                                   | **退出条件**                                                 |
|--------------------|----------|--------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| Phase 0 基线       | 2 周     | 仓库治理、ADR、gold set v0、OpenAPI/domain skeleton、CI                                    | 三个仓库职责锁定；gold set 可运行                            |
| Phase 1 数据底座   | 3–4 周   | Document Model、PostgreSQL、PubEx package、ingestion、migration                            | 旧 PubMed/PMC 流程可写入新 DB                                |
| Phase 2 Agent MVP  | 4–5 周   | Agent session、clarify/plan/act/observe、TaskSchema、screen/extract/normalize、Evidence UI | 自然语言目标可驱动一类 biomarker task 并返回 grounded report |
| Phase 3 验证与质量 | 3–4 周   | 跨论文 verification、coverage、停止条件、rules、conflict、Review UI                        | Agent 能主动查找反证并在正确条件停止；gold regression 达标   |
| Phase 4 V1 强化    | 4–6 周   | citation traversal、aggregation、追问、reprocessing、admin/version UI                      | 可稳定运行多个疾病队列并支持研究者连续追问                   |

### 18.1 P0 P1 P2 P3

| **优先级** | **内容**                                                                                              |
|------------|-------------------------------------------------------------------------------------------------------|
| P0         | Agent Session、TaskSpec、Evidence Schema、Document Model、PubMed/PMC/PubTator、Gold Dataset           |
| P1         | 有界 Agent loop、Screening、Structured Extraction、Normalization、Evidence grounding、Agent Workspace |
| P2         | Cross paper Verification、Coverage、Stopping Policy、Claim aggregation、Contradiction、Review UI      |
| P3         | 更多 TaskSchema、更多数据库、Knowledge Graph、多 Agent 协作                                           |

## 19 模块级改造清单

| **仓库与模块**                           | **动作**            | **目标位置/结果**                                                                     |
|------------------------------------------|---------------------|---------------------------------------------------------------------------------------|
| PubMiner-webui/PubMiner/pubminer/fetcher | MOVE + REFACTOR     | PubEx clients/pubmed；typed Document metadata                                         |
| .../downloader/pmc_bioc.py               | MOVE + REFACTOR     | PubEx clients/pmc；license + content version                                          |
| .../downloader/section_parser.py         | KEEP + TEST         | PubEx parsers/bioc；稳定 offsets 与 golden tests                                      |
| .../downloader/oa_pdf.py                 | KEEP LIMITED        | PubEx clients/oa；policy-aware resolver                                               |
| .../extractor/zhipu_client.py            | REPLACE             | PubMiner integrations/llm/providers/zhipu                                             |
| .../extractor/schemas                    | REFACTOR            | PubMiner domain/task_schemas + extraction DTOs                                        |
| .../core/task_store.py                   | MIGRATE             | SQLAlchemy repositories + Alembic                                                     |
| .../core/extraction_tasks.py             | REWRITE             | workflows/mining state machine                                                        |
| PubMiner-webui/PubMiner/api_server.py    | SPLIT               | api/v1 routers + application services                                                 |
| PubMiner agents/\*                       | ADD                 | AgentSession、TaskSpec、planner、coverage、stopping、synthesis；只调用 typed commands |
| PubMiner/core/pubmed_fetcher.py          | MERGE/DEPRECATE     | 能力并入 PubEx；保留回归测试                                                          |
| PubMiner/core/pdf_downloader.py          | ISOLATE             | 受控 fallback ingestion tool                                                          |
| PubMiner/core/scihub_downloader.py       | REMOVE FROM PRODUCT | 不进入生产依赖或默认配置                                                              |
| PubMiner/core/llm_analyzer.py            | REPLACE             | LLM Gateway + prompt registry                                                         |
| PubMiner/extractors/\*                   | ADAPT               | typed extraction interfaces；逐步淘汰旧解析                                           |
| PubEx/PubEx.py                           | FREEZE + EXTRACT    | legacy CLI + CSV importer；核心能力进入 package                                       |
| prisma/schema.prisma                     | DELETE SAMPLE       | 业务 DB 由后端拥有；前端无 Prisma 直连                                                |
| src/lib/api.ts                           | GENERATE            | OpenAPI client                                                                        |
| src/lib/store.ts                         | SPLIT               | feature stores + server-state cache                                                   |
| src/app/agent                            | ADD                 | Agent Workspace；conversation、plan、activity、coverage、evidence                     |

## 20 Migration 设计

| **Migration**          | **内容**                                              | **回滚**                               |
|------------------------|-------------------------------------------------------|----------------------------------------|
| 0001_core_documents    | documents、identifiers、versions、sections、passages  | 只新增表                               |
| 0002_entities          | entities、aliases、identifiers、mentions、resolutions | 只新增表                               |
| 0003_claim_evidence    | claims、evidence、statistics、clusters                | 只新增表                               |
| 0004_agent_sessions    | agent sessions、messages、plans、actions、coverage    | 只新增表                               |
| 0005_workflow          | tasks、runs、steps、tool_calls                        | 只新增表                               |
| 0006_review_versions   | reviews、revisions、version assets                    | 只新增表                               |
| 0007_provenance_policy | provenance、licenses、source policy                   | 只新增表                               |
| data_0001_sqlite       | 导入旧 tasks/search sessions/cache                    | 保留 source snapshot                   |
| data_0002_csv          | 导入 PubMiner/PubEx CSV                               | 进入 legacy_extraction，不自动 publish |

采用 expand–migrate–verify–switch–contract。切换期旧 API 保持只读兼容，双写仅在短时间内使用并通过对账作业比较；不要长期维护两套真相。

## 21 团队与交付治理

| **责任域**         | **建议 owner**                    | **关键产物**                                             |
|--------------------|-----------------------------------|----------------------------------------------------------|
| Domain/Data        | Backend lead + biomedical curator | schema、invariants、migrations、rules                    |
| Retrieval/Document | PubEx maintainer                  | source adapters、parsers、license policy、contract tests |
| AI/Evaluation      | ML engineer + curator             | prompts、gold set、benchmark、pipeline releases          |
| Workflow/API       | Backend engineer                  | state machines、services、API、queue                     |
| Review UX          | Frontend engineer + curator       | review interaction、keyboard flow、accessibility         |
| Platform/Security  | Platform owner                    | deployment、observability、secrets、RBAC、backup         |

每个重大决策写 ADR；每个 pipeline release 附 benchmark report；每个 schema/rule 变更由 curator 和 engineer 双签。产品 backlog 以“降低 validated record 时间并保持关键错误率”为排序原则。

## 22 风险登记册

| **风险**                     | **概率/影响** | **缓解措施**                                                                 |
|------------------------------|---------------|------------------------------------------------------------------------------|
| Agent 偏离研究目标或无限循环 | 中/高         | versioned TaskSpec、允许动作集合、轮次/成本预算、coverage 与 stopping policy |
| Agent 过早停止或虚构覆盖充分 | 中/高         | gold task、关键问题 coverage matrix、停止原因评测、人工抽样                  |
| 检索漏掉关键论文             | 中/高         | gold queries、citation expansion、Recall@100 门禁、人审抽样                  |
| 全文许可误用                 | 中/高         | source policy、license record、OA subset 区分、公开 snippet 门禁             |
| LLM span 或统计量幻觉        | 中/高         | schema + exact span + verifier + no evidence no claim                        |
| 实体误标准化                 | 中/高         | resolver only、top-k 候选、歧义审核、ontology version                        |
| 大文件/长任务成本失控        | 中/中         | 预算、缓存、分级模型、early stop、cost per validated claim                   |
| 三仓库继续重复开发           | 高/中         | 职责冻结、CODEOWNERS、迁移完成后删除重复模块                                 |
| 审核成为瓶颈                 | 中/高         | priority queue、批量键盘操作、active learning、random QA                     |
| 模型升级造成回归             | 高/高         | pipeline release、golden/regression、canary、可回滚                          |

## 23 验收标准

- 用户可用自然语言创建 Agent session；Agent 能澄清缺失约束并生成可编辑、可版本化的研究计划。

- 每个 Agent action 均来自允许的 typed tool 或 workflow command，并记录计划步骤、结果摘要、成本和状态。

- Agent 能根据 coverage、冲突和边际收益决定继续、改写查询、请求人工或停止，并明确报告停止原因。

- 任一 candidate claim 均能跳转到固定 document version 的 evidence span。

- canonical identifier 均有 resolver result 和 ontology version；模型输出不能越过 resolver。

- 同一 claim 能同时保存 SUPPORT、CONTRADICT、NO_EFFECT、UNCERTAIN。

- 人审修改保留模型原输出、before/after、reviewer、时间与理由。

- pipeline release 可重放；旧 extraction 不被覆盖。

- WebUI 以 Agent Workspace 为主入口，清晰展示计划、真实 workflow/tool events、coverage 和证据，而不是伪造或不可审计的 Thinking。

- 旧 PubMiner/PubEx 数据可导入且不会自动进入 Published。

- 关键 benchmark、权限、安全和迁移对账测试全部通过。

## 24 建议的下一步

1.  冻结三个仓库的目标职责和 Agent first 产品定位，创建 ADR-001 至 ADR-009，并在 README 链接。

2.  从现有人工数据库抽取 200–500 篇首批 gold set，定义 biomarker-v2 schema 与 evidence-rule-v1 草案。

3.  在 PubMiner 建立 domain/application/api/workflows/infrastructure 骨架和 PostgreSQL migrations。

4.  把新版 AsyncPubMedClient、PMC BioC parser、OA resolver 迁入 PubEx package，并补 contract/golden tests。

5.  实现 AgentSession → TaskSpec → Plan → Search → Evidence 的最短竖切，再补 Screen、Extract、Normalize、Verify 与 Review。

6.  用一个疾病场景跑通 Agent 基线，记录计划完成率、停止原因、minutes per validated record、漏检和 critical errors，再决定 V2 功能。

### 24.1 建议按 PR 交付的首批工作包

| **PR** | **仓库**         | **范围**                                                 | **验收标准**                                                             |
|--------|------------------|----------------------------------------------------------|--------------------------------------------------------------------------|
| PR-001 | PubEx            | 删除全局 TLS 绕过；为网络错误建立 typed exception        | 默认验证证书；TLS 失败可测试且不会静默继续                               |
| PR-002 | PubMiner         | 隔离 Sci-Hub 代码与配置，不进入 production package       | 生产依赖、配置和运行路径均不引用 Sci-Hub                                 |
| PR-003 | PubEx            | 建立 src/pubex package 与 PubMed typed models            | 旧 CLI 仍可运行；字段映射 golden test 通过                               |
| PR-004 | PubEx            | 迁入 AsyncPubMedClient 与 PMC BioC parser                | contract test 与固定 BioC fixture 通过                                   |
| PR-005 | PubMiner         | 建立 domain/document、entity、claim、evidence 模型       | domain 无 FastAPI、SQLAlchemy、provider import                           |
| PR-006 | PubMiner         | Alembic 0001–0003 与 repositories                        | 可写入 document、passages、claim、evidence；迁移可重复                   |
| PR-007 | PubMiner         | LLMPort、PromptVersion、Tool Registry、Zhipu adapter     | Agent/workflow 单测使用 fake provider 与 fake tools；业务无厂商 SDK      |
| PR-008 | PubMiner         | AgentSession、TaskSpec、plan version 与 AgentAction 模型 | 会话、澄清、计划、预算和行动可持久化与重放                               |
| PR-009 | PubMiner         | 有界 Agent Orchestrator 与 stopping policy               | Agent 只能选择允许动作；轮次、成本、人工确认和停止原因可测试             |
| PR-010 | PubMiner         | MiningWorkflow 最短竖切                                  | Agent 可驱动 Search→Screen→Extract→Normalize→EvidenceReady，失败后可恢复 |
| PR-011 | PubMiner-webui   | OpenAPI client、SSE 与 feature stores                    | 删除 api/store 重复类型；会话事件可恢复；构建与类型检查通过              |
| PR-012 | PubMiner-webui   | Agent Workspace 最小页面                                 | 可输入目标、确认计划、观察行动、暂停并从结论定位 evidence span           |
| PR-013 | PubMiner + webui | 跨论文 verification、coverage 与 Review UI               | 支持四类极性、独立验证、冲突队列及 Accept/Edit/Reject revision           |

### 24.2 重构顺序约束

- PR-001 至 PR-004 先固定输入与解析行为，避免在迁移中丢失元数据和 offset。

- PR-005 与 PR-006 先于新 workflow，确保 Agent 输出有稳定的领域对象和事务边界。

- PR-007 后才能替换 Zhipu 直连；在此之前不得同时扩展更多模型供应商。

- PR-008 与 PR-009 只实现一个 biomarker TaskSchema 和单 Agent，不提前引入多 Agent、Temporal 或 Neo4j。

- PR-010 必须复用已测试的 workflow command，Agent Orchestrator 不得复制检索或抽取实现。

- PR-011 至 PR-013 以生成的 API contract 为准，禁止前端复制后端领域枚举。

## 附录 A 关键 Pydantic 契约示意

```python
class AgentAction(BaseModel):
    session_id: UUID
    plan_version: int
    action_type: Literal[
        "SEARCH", "HYDRATE", "SCREEN", "EXTRACT", "NORMALIZE",
        "VERIFY", "EXPAND_QUERY", "ASK_HUMAN", "SYNTHESIZE", "STOP"
    ]
    tool_name: str | None
    arguments: dict
    expected_information_gain: str
    budget_delta: BudgetDelta


class CoverageSnapshot(BaseModel):
    questions: list[CoverageItem]
    support_count: int
    contradict_count: int
    no_effect_count: int
    independent_validation_found: bool
    unresolved_gaps: list[str]
    recommended_next_action: str | None


class EvidenceSpan(BaseModel):
    document_version_id: UUID
    passage_id: UUID
    start_char: int
    end_char: int
    text: str
    text_hash: str


class BiomarkerEvidence(BaseModel):
    biomarker_mention: str
    disease_mention: str
    role: Literal["prognostic", "diagnostic", "predictive"]
    direction: str | None
    outcome: str | None
    population: Population
    study_design: StudyDesign
    statistics: Statistics | None
    evidence_span: EvidenceSpan


class VerificationResult(BaseModel):
    polarity: Literal["SUPPORT", "CONTRADICT", "NO_EFFECT", "UNCERTAIN"]
    entity_correct: bool | None
    disease_correct: bool | None
    endpoint_correct: bool | None
    statistically_significant: bool | None
    analysis_type: Literal["univariate", "multivariate", "unknown"]
    independent_validation: bool | None
    reasons: list[str]
    needs_human_review: bool
```

## 附录 B 状态与枚举

| **对象**          | **建议枚举**                                                                                                                     |
|-------------------|----------------------------------------------------------------------------------------------------------------------------------|
| Agent session     | DRAFT, CLARIFYING, PLANNED, RUNNING, WAITING_HUMAN, PAUSED, SYNTHESIZING, COMPLETED, LIMITED, FAILED, CANCELLED                  |
| Agent action      | PLAN, SEARCH, HYDRATE, SCREEN, EXTRACT, NORMALIZE, VERIFY, EXPAND_QUERY, ASK_HUMAN, SYNTHESIZE, STOP                             |
| Task              | CREATED, PLANNING, SEARCHING, SCREENING, EXTRACTING, NORMALIZING, VERIFYING, REVIEW_READY, COMPLETED, PARTIAL, FAILED, CANCELLED |
| Screening         | RELEVANT, IRRELEVANT, UNCERTAIN                                                                                                  |
| Evidence polarity | SUPPORT, CONTRADICT, NO_EFFECT, UNCERTAIN                                                                                        |
| Claim status      | CANDIDATE, REVIEWED, APPROVED, PUBLISHED, REJECTED, DEPRECATED                                                                   |
| Review decision   | ACCEPT, EDIT_ACCEPT, REJECT, NEEDS_REVIEW                                                                                        |
| Run step          | PENDING, RUNNING, SUCCEEDED, FAILED_RETRYABLE, FAILED_FINAL, SKIPPED, CANCELLED                                                  |

## 附录 C 参考资料

| **资料**                    | **URL**                                                          | **用途**                        |
|-----------------------------|------------------------------------------------------------------|---------------------------------|
| WhyLIM PubMiner webui       | https://github.com/WhyLIM/PubMiner-webui                         | 代码审计与现有功能基线          |
| WhyLIM PubMiner             | https://github.com/WhyLIM/PubMiner                               | 旧版模块、配置与抽取实现基线    |
| WhyLIM PubEx                | https://github.com/WhyLIM/PubEx                                  | PubMed 批处理与 legacy 数据来源 |
| NCBI E utilities            | https://www.ncbi.nlm.nih.gov/books/NBK25499/                     | 检索参数、History 与使用规则    |
| PubTator 3 API              | https://www.ncbi.nlm.nih.gov/research/pubtator3/api              | 实体、文献与关系检索接口        |
| PubTator 3 paper            | https://academic.oup.com/nar/article/52/W1/W540/7640526          | PubTator 3 能力与研究说明       |
| PMC Open Access Subset      | https://pmc.ncbi.nlm.nih.gov/tools/openftlist/                   | 可重用全文的许可边界            |
| PMC Article Datasets        | https://pmc.ncbi.nlm.nih.gov/tools/textmining/                   | 全文数据集与 text mining 条件   |
| PostgreSQL Full Text Search | https://www.postgresql.org/docs/current/textsearch-controls.html | 本地全文检索实现依据            |

## 附录 D 本设计的决策边界

仓库审计结论以文首提交 SHA 为准。涉及部署规模、模型供应商、具体 evidence score、云成本和用户并发的参数仍需通过 gold set、压测和领域专家评审确定。本文中示例权重、SLO 与周期属于实施起点，而不是不可变承诺。
