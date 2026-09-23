"""PR-004 contract test：PubMed XML 解析与 BioC 解析（固定 fixture，离线）。"""
import json
from pathlib import Path

import pytest
from Bio import Entrez

from pubex.clients.pubmed_parse import parse_pubmed_record
from pubex.models.document import Passage, content_hash
from pubex.parsers.bioc import BiocSectionParser, SectionType

FIXTURES = Path(__file__).parent


@pytest.fixture(scope="module")
def parsed_record():
    with (FIXTURES / "pubmed_article.xml").open("rb") as handle:
        data = Entrez.read(handle)
    (article,) = data["PubmedArticle"]
    return parse_pubmed_record(article)


class TestPubMedRecordContract:
    def test_identifiers(self, parsed_record):
        assert parsed_record.pmid == "33145284"
        assert parsed_record.pmcid == "PMC7756730"
        assert parsed_record.doi == "10.1371/journal.pone.0245341"
        assert parsed_record.has_pmc_fulltext is True

    def test_bibliographic_fields(self, parsed_record):
        assert parsed_record.title.startswith("KRAS gene status")
        assert parsed_record.authors == ["Zhang Wei", "Ito Takashi"]
        assert parsed_record.first_author == "Zhang Wei"
        assert "Example University Hospital" in parsed_record.affiliation
        assert parsed_record.journal == "PLoS ONE"
        assert parsed_record.journal_abbrev == "PLoS One"
        assert parsed_record.year == 2021
        assert parsed_record.volume == "16"
        assert parsed_record.issue == "1"
        assert parsed_record.pages == "e0245341"

    def test_structured_abstract(self, parsed_record):
        assert parsed_record.abstract.startswith("BACKGROUND:")
        assert "HR 2.1" in parsed_record.abstract or "hazard" in parsed_record.abstract.lower()

    def test_keywords_mesh_language_grants(self, parsed_record):
        assert parsed_record.keywords == ["PDAC", "KRAS"]
        assert parsed_record.mesh_terms == ["Pancreatic Neoplasms"]
        assert parsed_record.language == "eng"
        assert "NCI NIH HHS: R01CA123456" == parsed_record.grant_list

    def test_status_and_revision(self, parsed_record):
        assert parsed_record.publication_status == "epublish"
        assert parsed_record.last_revision_date == "2020-12-10"

    def test_citation_string(self, parsed_record):
        text = parsed_record.get_citation()
        assert "Zhang Wei" in text and "2021" in text

    def test_pmid_validation_rejects_garbage(self):
        from pydantic import ValidationError

        from pubex.models.pubmed_record import PubMedRecord

        with pytest.raises(ValidationError):
            PubMedRecord(pmid="not-a-pmid", title="x")


@pytest.fixture(scope="module")
def bioc_data():
    return json.loads((FIXTURES / "bioc_document.json").read_text(encoding="utf-8"))


class TestBiocContract:
    def test_section_classification(self, bioc_data):
        parser = BiocSectionParser()
        sections = parser.parse_sections(bioc_data)
        assert SectionType.ABSTRACT in sections
        assert SectionType.INTRODUCTION in sections
        assert SectionType.METHODS in sections
        assert SectionType.RESULTS in sections
        assert SectionType.DISCUSSION in sections
        assert SectionType.CONCLUSION in sections
        # legacy parse_sections 语义：只按长度过滤，references 仍会出现在分类视图
        assert SectionType.REFERENCES in sections

    def test_document_version_excludes_non_body(self, bioc_data):
        parser = BiocSectionParser()
        doc = parser.build_document_version(bioc_data, pmid="33145284", pmcid="PMC7756730")
        paths = {p.section_path for p in doc.passages}
        assert "REFERENCES" not in paths and "ACK" not in paths and "SUPPL" not in paths
        # title 不混入正文，单独存于 title 字段
        assert doc.title.startswith("KRAS gene status")
        for passage in doc.passages:
            assert passage.text != doc.title

    def test_title_extraction(self, bioc_data):
        assert BiocSectionParser.extract_title(bioc_data).startswith("KRAS gene status")

    def test_document_version_stable_offsets(self, bioc_data):
        parser = BiocSectionParser()
        doc = parser.build_document_version(bioc_data, pmid="33145284", pmcid="PMC7756730")

        assert doc.pmcid == "PMC7756730"
        assert doc.text_hash == content_hash(doc.canonical_text)
        assert doc.passages, "body passages must exist"

        # offsets 与 canonical text 严格一致（grounding 的基础）
        for passage in doc.passages:
            slice_text = doc.canonical_text[passage.start_char : passage.end_char]
            assert slice_text == passage.text
            assert passage.text_hash == content_hash(passage.text)
            assert passage.section_path in {"ABSTRACT", "INTRO", "METHODS", "RESULTS", "DISCUSSION", "CONCLUSION", "OTHER"}

    def test_document_version_deterministic(self, bioc_data):
        parser = BiocSectionParser()
        doc1 = parser.build_document_version(bioc_data, pmcid="PMC7756730")
        doc2 = parser.build_document_version(bioc_data, pmcid="PMC7756730")
        assert doc1.text_hash == doc2.text_hash
        assert doc1.passages == doc2.passages

    def test_passage_lookup_by_offset(self, bioc_data):
        parser = BiocSectionParser()
        doc = parser.build_document_version(bioc_data, pmcid="PMC7756730")
        target = doc.passages[2]  # 任选一个 passage
        found = [
            p for p in doc.passages
            if p.start_char <= target.start_char < p.end_char
        ]
        assert found == [target]

    def test_legacy_filtered_text_still_works(self, bioc_data):
        parser = BiocSectionParser()
        text = parser.get_filtered_text(bioc_data)
        assert text.startswith("[ABSTRACT]")
        assert "[METHODS]" in text and "[RESULTS]" in text
        assert "References" not in text.split("\n")[0]

    def test_license_record_defaults_to_unknown_redistribution(self):
        from pubex.models.document import LicenseRecord

        record = LicenseRecord(source="pmc-oa")
        assert record.allows_redistribution is None
        assert record.license is None

    def test_passage_build_hash(self):
        passage = Passage.build("RESULTS", "example text", 10)
        assert passage.end_char == 22
        assert passage.start_char == 10
        assert passage.text_hash == content_hash("example text")
