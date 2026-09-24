"""PubEx typed models。"""
from pubex.models.article import PubMedArticle, LEGACY_CSV_COLUMNS
from pubex.models.document import (
    DocumentVersion,
    LicenseRecord,
    Passage,
    content_hash,
)
from pubex.models.identifiers import ArticleIdentifiers
from pubex.models.pubmed_record import PubMedRecord

# 迁移期兼容别名（PubMiner-webui LiteratureMetadata）
LiteratureMetadata = PubMedRecord

__all__ = [
    "PubMedArticle",
    "LEGACY_CSV_COLUMNS",
    "ArticleIdentifiers",
    "PubMedRecord",
    "LiteratureMetadata",
    "DocumentVersion",
    "Passage",
    "LicenseRecord",
    "content_hash",
]
