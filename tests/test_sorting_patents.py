"""Synthetic patent front pages; identifiers and people are test data."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from note_organizer.sorting import core_logic as core
from note_organizer.sorting.patent_metadata import extract_patent_fields, normalize_patent_number

GRANT = """US009123456B2
(12) United States Patent
Li et al.
(10) Patent No.: US 9,123,456 B2
(45) Date of Patent: Sep. 1, 2015
(54) SYNTHETIC TEST DEVICE
(72) Inventors: Wei Li, Boston, MA (US); Jane Smith,
Cambridge, MA (US); Alex Jones, Austin, TX (US)
(73) Assignee: Example Corporation, Boston, MA (US)
(21) Appl. No.: 12/345,678
(22) Filed: Jan. 2, 2009
(65) Prior Publication Data
US 2014/0123456 A1 May 1, 2014
(56) References Cited
Journal of Tests doi:10.1234/other.work 2001
(57) ABSTRACT
This device refers to supporting information in another work.
"""
APPLICATION = GRANT.replace("(12) United States Patent", "(19) United States\n(12) Patent Application Publication").replace("Patent No.: US 9,123,456 B2", "Pub. No.: US 2014/0123456 A1").replace("(45) Date of Patent: Sep. 1, 2015", "(43) Pub. Date: May 1, 2014")

class PatentTests(unittest.TestCase):
    def details(self, text=GRANT):
        extraction = core.DocumentExtraction(text=text, metadata={"author": "Wrong PDF Company", "creation_date": "2000"})
        return core._basic_details_from_extraction(Path("unhelpful.pdf"), extraction)

    def test_grant_uses_inventors_issue_year_and_full_number(self):
        d=self.details()
        self.assertEqual(d["document_type"], "patent")
        self.assertEqual(d["document_type_label"], "Patent")
        self.assertEqual(d["inventors"], ["Wei Li", "Jane Smith", "Alex Jones"])
        self.assertEqual(d["year"], "2015")
        self.assertEqual(d["issue_date"], "2015-09-01")
        self.assertEqual(d["assignee"], "Example Corporation, Boston, MA (US)")
        self.assertEqual(d["identifier"], {"patent": "US9123456B2"})
        self.assertEqual(d["title"], "SYNTHETIC TEST DEVICE")
        self.assertFalse(d["needs_review"])
        self.assertFalse(d["is_supplementary_material"])
        self.assertEqual(core.build_proposed_filename(d, ".pdf"), "Li_et_al_US_Patent_2015_US9123456B2.pdf")

    def test_application_uses_publication_year_and_identifier(self):
        d=self.details(APPLICATION)
        self.assertEqual(d["document_type"], "patent_application")
        self.assertEqual(d["publication_date"], "2014-05-01")
        self.assertEqual(d["issue_date"], "")
        self.assertEqual(core.build_proposed_filename(d, ".pdf"), "Li_et_al_US_Patent_Application_2014_US20140123456A1.pdf")

    def test_missing_inventor_never_uses_assignee_or_pdf_author(self):
        d=self.details(GRANT.replace("(72) Inventors:", "(74) Attorney:"))
        self.assertEqual(d["creators"], [])
        self.assertTrue(d["needs_review"])
        self.assertTrue(core.build_proposed_filename(d, ".pdf").startswith("UnknownInventor_US_Patent"))

    def test_missing_kind_code_is_not_invented(self):
        d=self.details(GRANT.replace("9,123,456 B2", "9,123,456"))
        self.assertEqual(d["patent_number"], "US9123456")
        self.assertEqual(d["patent_kind_code"], "")

    def test_single_and_two_inventors_follow_existing_paper_style(self):
        for inventors, expected in ((["Wei Li"], "Li"), (["Wei Li", "Jane Smith"], "Li_and_Smith_et_al")):
            d=core.normalize_document_details({**extract_patent_fields(GRANT), "inventors": inventors}, "test.pdf")
            self.assertTrue(core.build_proposed_filename(d, ".pdf").startswith(expected+"_US_Patent_"))

    def test_papers_and_citations_are_not_patents(self):
        for text in ("Abstract\nJournal of Materials\nWe cite United States Patent US 9,123,456 B2 from 2015.", "References\n"+GRANT[GRANT.index("(10)"):], "US9123456B2", "A paper about patent applications. Published in 2015."):
            self.assertEqual(extract_patent_fields(text), {})
            self.assertNotIn(core.infer_document_type(text), {"patent", "patent_application"})

    def test_complete_patent_skips_doi_and_cloud(self):
        with patch.object(core,"extract_document",return_value=core.DocumentExtraction(text=GRANT)), patch.object(core,"_doi_details_for_document") as doi, patch.object(core,"_load_genai") as ai:
            d=core.get_document_details("test.pdf", "test-key", allow_cloud_ai=True)
        doi.assert_not_called()
        ai.assert_not_called()
        self.assertEqual(d["patent_number"], "US9123456B2")

    def test_ai_can_fill_inventors_but_not_overwrite_verified_identity(self):
        text=GRANT.replace("(72) Inventors:", "(74) Attorney:")
        response={"document_type":"web_or_other", "inventors":["Wei Li"], "creators":["Wrong Assignee"], "patent_number":"US9999999B1", "year":"2009", "issue_date":"2009-01-02"}
        client=Mock()
        client.models.generate_content.return_value.text=json.dumps(response)
        with patch.object(core,"extract_document",return_value=core.DocumentExtraction(text=text)), patch.object(core,"_doi_details_for_document") as doi, patch.object(core,"_load_genai",return_value=True), patch.object(core,"genai",Mock(Client=Mock(return_value=client))), patch.object(core,"genai_types",Mock()):
            d=core.get_document_details("test.pdf","test-key",allow_cloud_ai=True)
        doi.assert_not_called()
        self.assertEqual(d["inventors"],["Wei Li"])
        self.assertEqual(d["patent_number"],"US9123456B2")
        self.assertEqual(d["year"],"2015")
        self.assertEqual(d["document_type"],"patent")

    def test_ai_only_patent_fields_and_date_normalize(self):
        d=core.normalize_document_details({"document_type":"patent_application_publication", "inventors":["Wei Li"], "assignee":"Example Corp", "publication_date":"May 1, 2014", "issue_date":"2015-09-01", "year":"2009", "patent_number":"US 2014/0123456 A1"}, "test.pdf")
        self.assertEqual(d["year"],"2014")
        self.assertEqual(d["primary_creator"],"Wei Li")
        self.assertTrue(core.build_proposed_filename(d, ".pdf").endswith("US20140123456A1.pdf"))

    def test_invalid_identifier_is_reviewable_and_safe(self):
        d=core.normalize_document_details({"document_type":"patent","inventors":["Wei Li"],"patent_number":"../../secret","year":"2015"},"test.pdf")
        self.assertTrue(d["needs_review"])
        self.assertIn("UnknownPatentNumber",core.build_proposed_filename(d, ".pdf"))
        core.validate_document_filename(core.build_proposed_filename(d, ".pdf"),".pdf")

    def test_non_us_country_is_not_renamed_us(self):
        d=core.normalize_document_details({"document_type":"patent","inventors":["Wei Li"],"patent_number":"EP1234567B1","issue_date":"2015-09-01"},"test.pdf")
        self.assertEqual(core.build_proposed_filename(d, ".pdf"),"Li_EP_Patent_2015_EP1234567B1.pdf")

    def test_journal_styles_fall_back_and_custom_tokens_work(self):
        d=self.details()
        for style in ("journal_compact","journal_detailed"):
            self.assertEqual(core.build_proposed_filename(d, ".pdf",filename_format=style),core.build_proposed_filename(d, ".pdf"))
        self.assertEqual(core.build_proposed_filename(d, ".pdf",filename_format="custom",custom_template="{author_last}_{patent_country}_{patent_number}_{year}"),"Li_US_US9123456B2_2015.pdf")

    def test_number_normalization_keeps_kind_and_application_zeros(self):
        for raw, expected in (("US 2014/0000123 A1","US20140000123A1"),("US D123,456 S1","USD123456S1"),("US RE45,123 E1","USRE45123E1"),("US 5,123,456 A","US5123456A")):
            self.assertEqual(normalize_patent_number(raw),expected)
        self.assertEqual(normalize_patent_number("US123"),"")

    def test_missing_date_does_not_use_filing_or_reference_year(self):
        d=self.details(GRANT.replace("Sep. 1, 2015", "Unreadable"))
        self.assertEqual(d["document_type"], "patent")
        self.assertEqual(d["year"], "Unknown")
        self.assertTrue(d["needs_review"])
        self.assertIn("UnknownYear",core.build_proposed_filename(d,".pdf"))

    def test_explicitly_missing_inventors_never_become_company_creators(self):
        d=core.normalize_document_details({"document_type":"patent", "inventors":[], "creators":["Example Corporation"], "patent_number":"US9123456B2"},"test.pdf")
        self.assertEqual(d["creators"],[])
        self.assertTrue(d["needs_review"])

    def test_filename_alone_does_not_classify_a_document(self):
        d=core._basic_details_from_extraction(Path("US9123456B2.pdf"),core.DocumentExtraction(text="An ordinary report"))
        self.assertNotIn(d["document_type"],{"patent","patent_application"})

    def test_synthetic_pdf_extraction_to_filename(self):
        import tempfile
        from tests.sorting_fixtures import verify_patent_support
        with tempfile.TemporaryDirectory() as directory:
            verify_patent_support(Path(directory))

    def test_legacy_inventor_code_and_notice_do_not_pollute_assignee(self):
        text=GRANT.replace("(72) Inventors:","(75) Inventors:").replace("(21) Appl.","( * ) Notice: Patent term adjusted by 200 days.\n(21) Appl.")
        d=self.details(text)
        self.assertEqual(d["inventors"][0],"Wei Li")
        self.assertEqual(d["assignee"],"Example Corporation, Boston, MA (US)")
