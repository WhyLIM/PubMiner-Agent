# ADR-009: 先 PostgreSQL FTS + pgvector
状态: accepted
决策: MVP 检索 = 外部召回（PubMed/PubTator）+ PG tsvector + pgvector 语义召回；
不引入 OpenSearch/Neo4j。
