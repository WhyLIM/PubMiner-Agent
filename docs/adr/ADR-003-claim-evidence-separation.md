# ADR-003: Claim 与 Evidence 分离
状态: accepted
决策: Claim 是规范化命题（canonical_signature 聚类键）；Evidence 必须绑定
passage 级 EvidenceSpan。同一 claim 可同时保存 SUPPORT/CONTRADICT/NO_EFFECT/UNCERTAIN。
强制: domain 层 EvidenceSpan 校验 text_hash；无 span 文本的 Evidence 拒绝创建。
