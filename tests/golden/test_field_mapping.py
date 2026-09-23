"""Golden test：MEDLINE 字段映射快照。

快照 tests/golden/expected_medline_records.csv 由 legacy PubEx 实现一次性
生成并固化（PR-003 时与 legacy create_record_dict 逐字节对比通过）。
此后任何解析改动都必须显式更新快照才能通过，防止字段映射漂移。
"""
import io
from pathlib import Path

import pandas as pd
import pytest
from Bio import Medline

from pubex.models.article import LEGACY_CSV_COLUMNS
from pubex.parsers.dates import extract_publication_date
from pubex.parsers.medline import medline_record_to_article

FIXTURES = Path(__file__).parent
LINKED = ["35100001", "35100002"]
REFERENCES = ["28765432", "27654321", "26543210"]


def _render(rows: list[dict]) -> str:
    df = pd.DataFrame(rows, columns=LEGACY_CSV_COLUMNS)
    df = df.fillna("NA")
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, na_rep="NA", lineterminator="\n")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def medline_records():
    with (FIXTURES / "medline_records.txt").open(encoding="utf-8") as handle:
        return list(Medline.parse(handle))


class TestGoldenSnapshot:
    def test_rows_match_frozen_legacy_snapshot(self, medline_records):
        rows = [
            medline_record_to_article(
                r, cited_by_pmids=LINKED, reference_pmids=REFERENCES
            ).to_legacy_row()
            for r in medline_records
        ]
        expected = (FIXTURES / "expected_medline_records.csv").read_text(encoding="utf-8")
        assert _render(rows) == expected, (
            "field mapping drifted from the frozen legacy snapshot; "
            "update tests/golden/expected_medline_records.csv only with review"
        )


class TestMappingBehaviour:
    def test_missing_fields_fall_back_to_na(self, medline_records):
        article = medline_record_to_article(medline_records[2])
        row = article.to_legacy_row()
        for column in ("Affiliation", "Abstract", "Keywords", "DOI", "PMC", "Grant List", "F_Author"):
            assert row[column] == "NA", f"{column} should fall back to NA"
        assert row["cited"] == 0 and row["References"] == 0
        assert row["cited_by"] == [] and row["References_PMID"] == []

    def test_date_without_month_day_is_none(self, medline_records):
        article = medline_record_to_article(medline_records[2])
        assert article.publication_date is None
        assert article.to_legacy_row()["Publication Date"] == "NA"

    def test_full_record_publication_date_extracted(self, medline_records):
        article = medline_record_to_article(medline_records[0])
        assert article.publication_date == "2021 Jan 5"
        assert article.year_of_publication == "2021"
        assert article.identifiers.doi == "10.1371/journal.pone.0245341"
        assert article.identifiers.pmcid == "PMC7756730"

    def test_publication_date_extraction_direct(self):
        assert extract_publication_date({"DP": "2021 Jan 5"}) == "2021 Jan 5"
        assert extract_publication_date({"SO": "Gut. 2023 Sep 14;72(9):1-9"}) == "2023 Sep 14"
        assert extract_publication_date({"DP": "2022"}) is None
