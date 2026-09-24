# ADR-012: 三仓库整合为单一仓库（取代 ADR-010 的共存安排）
状态: accepted (2026-09-24)

背景: ADR-010 时期新架构包 `src/pubminer` 与 legacy 顶层包共存于原 PubMiner
仓库副本中，三个项目分散在 pubex/、pubminer/、pubminer-webui/ 三个嵌套
git 仓库。用户明确要求所有工作收敛到工作区根目录并去除冗余。

决策:
- 工作区根目录成为唯一 git 仓库；`src/pubminer`（Agent 后端）与
  `src/pubex`（获取解析 SDK）同仓同 pyproject，webui 位于 `webui/`；
- legacy 代码（旧 CLI、Sci-Hub 归档、内嵌旧后端、Prisma 样例）全部移除，
  不再保留归档副本（历史仍可在原上游仓库找到）；
- pubex 的 MEDLINE 字段映射契约由冻结快照 `tests/golden/expected_medline_records.csv`
  承载（生成时与 legacy 实现逐字节比对通过），不再依赖 legacy 源码。

后果: 目录结构扁平、单一 venv/单一测试入口；与上游三个公开仓库的同步
改为人工按需（本仓库不再 push）。
