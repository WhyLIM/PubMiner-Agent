# ADR-010: 新架构包与 legacy 模块共存（增量迁移）
状态: accepted (2026-09-23)
背景: 仓库已有 flat 顶层包（core/、extractors/...）与用户未提交的在制品
（text_extractor 重构、docling 缓存）。设计要求保留既有能力并保持向后兼容。
决策:
- 新架构放 src/pubminer（domain/application/agents/workflows/integrations/infrastructure/api），
  与 legacy 顶层包互不导入；
- Sci-Hub 代码归档至 legacy/（PR-002），不从仓库删除；
- 旧 webui 内嵌后端保持只读兼容，能力逐步并入 PubEx SDK；
- 用户在制品文件（core/text_extractor.py 的未提交重构等）一律不触碰。
