import ssl
import subprocess
import sys
from pathlib import Path

import pytest

from pubex.errors import (
    PubExError,
    PubExHTTPError,
    PubExMaxRetriesExceeded,
)
from pubex.normalizers.pmid import normalize_pmids
from pubex.io.legacy_csv import (
    iter_legacy_articles,
    legacy_row_to_article,
    read_legacy_pmids,
    write_legacy_csv,
)
from pubex.models.article import LEGACY_CSV_COLUMNS
from pubex.parsers.medline import medline_record_to_article

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


class TestPmidNormalization:
    def test_clean_dedupe_preserve_order(self):
        assert normalize_pmids([" 123 ", "123", 456, None, "nan", "", "NA", "abc", "456"]) == ["123", "456"]

    def test_empty_input(self):
        assert normalize_pmids([]) == []


class TestLegacyCsvRoundTrip:
    def _sample_article(self):
        return medline_record_to_article(
            {
                "PMID": "33145284",
                "TI": "Example title",
                "PT": ["Journal Article", "Review"],
                "DP": "2021 Jan 5",
                "FAU": ["Zhang, Wei"],
                "AU": ["Zhang W"],
                "AB": "Example abstract.",
                "LA": ["eng"],
                "LID": "10.1371/journal.pone.0245341 [doi]",
                "PMC": "PMC7756730",
                "SO": "PLoS One. 2021 Jan 5;16(1):e0245341",
            },
            cited_by_pmids=["35100001"],
            reference_pmids=["28765432", "27654321"],
        )

    def test_write_read_roundtrip(self, tmp_path):
        article = self._sample_article()
        out = write_legacy_csv([article], tmp_path / "out.csv")
        assert out.exists()
        assert (tmp_path / "out_backup.csv").exists()

        assert read_legacy_pmids(out) == {"33145284"}

        rows = list(iter_legacy_articles(out))
        assert len(rows) == 1
        restored = legacy_row_to_article(rows[0])
        assert restored.identifiers.pmid == "33145284"
        assert restored.identifiers.doi == "10.1371/journal.pone.0245341"
        assert restored.identifiers.pmcid == "PMC7756730"
        assert restored.authors == ["Zhang W"]
        assert restored.publication_type == ["Journal Article", "Review"]
        assert restored.cited_by_pmids == ["35100001"]
        assert restored.reference_pmids == ["28765432", "27654321"]
        # 还原后再导出与原始行完全一致（逐字节稳定）
        assert restored.to_legacy_row() == article.to_legacy_row()

    def test_missing_article_defaults_na_in_csv(self, tmp_path):
        import pandas as pd

        from pubex.models.identifiers import ArticleIdentifiers

        bare = medline_record_to_article({"PMID": "1"})
        out = write_legacy_csv([bare], tmp_path / "bare.csv")
        df = pd.read_csv(out, keep_default_na=False)
        assert list(df.columns) == list(LEGACY_CSV_COLUMNS)
        assert df.loc[0, "Title"] == "NA"
        assert df.loc[0, "cited"] == 0


class TestImportSafety:
    def test_import_does_not_mutate_global_ssl(self):
        """PR-001 安全保证延续到 SDK 包：import pubex 不改全局 SSL 工厂。"""
        code = (
            "import ssl, sys\n"
            f"sys.path.insert(0, r'{SRC_ROOT}')\n"
            "before = ssl._create_default_https_context\n"
            "import pubex\n"
            "after = ssl._create_default_https_context\n"
            "sys.exit(0 if before is after else 1)\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr[-300:]


class TestErrorParity:
    def test_hierarchy(self):
        assert issubclass(PubExHTTPError, PubExError)
        assert issubclass(PubExMaxRetriesExceeded, PubExError)
        err = PubExHTTPError(503, "unavailable", retryable=True)
        assert err.status_code == 503 and err.retryable

    def test_identifiers_require_source(self):
        from pubex.models.identifiers import ArticleIdentifiers

        with pytest.raises(ValueError):
            ArticleIdentifiers().identity_key()
