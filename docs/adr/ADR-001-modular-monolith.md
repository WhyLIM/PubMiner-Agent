# ADR-001: 模块化单体 + 独立 worker
状态: accepted (2026-09-23)
背景: 团队规模有限，需要隔离长任务（检索/抽取）与 API 进程。
决策: 采用模块化单体（src/pubminer 分层包）+ 后台 worker 执行长任务；不引入微服务/Temporal。
后果: 部署简单；worker 崩溃可恢复依赖数据库状态而非内存队列。
