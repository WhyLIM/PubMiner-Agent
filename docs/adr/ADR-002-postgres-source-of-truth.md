# ADR-002: PostgreSQL 为系统事实源（测试用 SQLite 可移植子集）
状态: accepted (2026-09-23)
背景: Claim/Evidence/Review/Version/Provenance 需要事务、一致性、可重处理。
决策: 生产使用 PostgreSQL（JSONB/GIN/pgvector）。ORM 层只用可移植类型
（sa.JSON with JSONB variant、sa.Uuid 等），因此测试套件可在 SQLite 上运行。
偏离说明: 设计文档要求 PG-only；为让自动化测试零依赖运行，类型层保持双方言兼容，
生产 DDL 仍以 PG 迁移为准（0001-0007 全部只新增表）。
