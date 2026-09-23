# ADR-006: identifier 只能由 resolver/tool 返回
状态: accepted
决策: EntityIdentifier 必须带 IdentifierSource（resolver/curator，LLM 不在列）；
Resolution.chosen 必须来自 candidates；未决必须 needs_review。
