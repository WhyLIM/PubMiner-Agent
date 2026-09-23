"""Entity 聚合：实体、别名、identifier、mention、resolution。

不变量（ADR-006）：canonical identifier 只能由 resolver/tool 返回；
`IdentifierSource` 必须记录来源；LLM 输出不得创建 EntityIdentifier。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class EntityType(str, Enum):
    GENE = "GENE"
    PROTEIN = "PROTEIN"
    DISEASE = "DISEASE"
    DRUG = "DRUG"
    VARIANT = "VARIANT"
    SPECIES = "SPECIES"
    PROCESS = "PROCESS"
    OTHER = "OTHER"


class IdentifierSource(str, Enum):
    """identifier 的合法来源。LLM 不在列表中。"""

    PUBTATOR = "pubtator"
    MESH_RESOLVER = "mesh-resolver"
    NCBI_GENE_RESOLVER = "ncbi-gene-resolver"
    UNIPROT_RESOLVER = "uniprot-resolver"
    HGNC_RESOLVER = "hgnc-resolver"
    CURATOR = "curator"


class EntityIdentifier(BaseModel):
    """一个 ontology 下的 identifier。必须带来源与 ontology 版本。"""

    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    namespace: str = Field(..., description="如 MESH / NCBIGene / UniProt")
    value: str = Field(..., description="如 D010190 / 5290 / P04637")
    ontology_version: str = Field(..., description="ontology 版本，可追溯")
    source: IdentifierSource
    resolved_at: datetime = Field(default_factory=lambda: datetime.now())
    score: float | None = Field(None, description="resolver 置信分；仅用于排序，不是事实真值")

    @model_validator(mode="after")
    def _check_value(self) -> "EntityIdentifier":
        if not self.value.strip():
            raise ValueError("identifier value must be non-empty")
        return self


class EntityAlias(BaseModel):
    alias: str
    language: str = "en"
    is_canonical: bool = False


class Entity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EntityType
    canonical_name: str
    aliases: list[EntityAlias] = Field(default_factory=list)
    identifiers: list[EntityIdentifier] = Field(default_factory=list)
    ontology_version: str = Field(..., description="实体解析使用的 ontology 版本")

    @property
    def primary_identifier(self) -> EntityIdentifier | None:
        """按来源优先级返回主 identifier。"""
        priority = [
            IdentifierSource.NCBI_GENE_RESOLVER,
            IdentifierSource.HGNC_RESOLVER,
            IdentifierSource.UNIPROT_RESOLVER,
            IdentifierSource.MESH_RESOLVER,
            IdentifierSource.PUBTATOR,
            IdentifierSource.CURATOR,
        ]
        for source in priority:
            for identifier in self.identifiers:
                if identifier.source == source:
                    return identifier
        return self.identifiers[0] if self.identifiers else None


class Mention(BaseModel):
    """文中提及：必须定位到 passage。"""

    id: UUID = Field(default_factory=uuid4)
    document_version_id: UUID
    passage_id: UUID
    text: str
    start_char: int
    end_char: int
    entity_type: EntityType
    extractor: str = Field(..., description="pubtator | llm-extractor@version 等")
    score: float | None = None

    @model_validator(mode="after")
    def _check_range(self) -> "Mention":
        if self.end_char <= self.start_char:
            raise ValueError("mention span must be non-empty")
        return self


class Resolution(BaseModel):
    """mention → entity 的消歧结果；歧义必须进入 review 而不是硬选。"""

    id: UUID = Field(default_factory=uuid4)
    mention_id: UUID
    candidates: list[UUID] = Field(..., description="resolver 返回的候选 entity id，按分数排序")
    chosen_entity_id: UUID | None = Field(
        None, description="确定选择；歧义未决时为 None 并 needs_review=True"
    )
    needs_review: bool = False
    resolver: str = Field(..., description="resolver 名称@版本")
    reason: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Resolution":
        if not self.candidates:
            raise ValueError("resolution requires resolver candidates")
        if self.chosen_entity_id is None and not self.needs_review:
            raise ValueError("unresolved mention must be flagged needs_review")
        if (
            self.chosen_entity_id is not None
            and self.chosen_entity_id not in self.candidates
        ):
            raise ValueError("chosen entity must be one of resolver candidates (ADR-006)")
        return self
