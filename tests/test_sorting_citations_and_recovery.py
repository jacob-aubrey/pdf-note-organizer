"""Citation and bounded AI recovery tests ported from sorter releases 1.3.1/1.3.2."""
import json
import unittest
from unittest.mock import Mock, MagicMock, patch
from note_organizer.sorting import core_logic as core

class CitationTests(unittest.TestCase):
    def test_surname_counts_and_particles(self):
        cases = [
            (["Jane Smith"], "Smith"),
            (["Jane Smith", "Jacob Aubrey"], "Smith_and_Aubrey_et_al"),
            (["Jane Smith", "Jacob Aubrey", "Jo Doe"], "Smith_et_al"),
            (["Smith, Jane", "Aubrey, Jacob"], "Smith_and_Aubrey_et_al"),
            (["Jonathan De Roo"], "De_Roo"),
            (["Smith J. A."], "Smith"),
        ]
        for authors, prefix in cases:
            with self.subTest(authors=authors):
                d = core.normalize_document_details({"creators": authors, "journal": "Journal", "year": "2026", "document_type": "journal_article"}, "paper.pdf")
                self.assertEqual(core.build_proposed_filename(d, ".pdf"), prefix + "_Journal_2026.pdf")
                d["is_supplementary_material"] = True
                self.assertEqual(core.build_proposed_filename(d, ".pdf"), prefix + "_Journal_2026_SI.pdf")

    def extraction(self, complete=False):
        return core.DocumentExtraction(text="Supporting Information\nA Long Technical Title\nAuthors: Jane Smith and Jacob Aubrey\n" + ("Journal: Journal\nYear: 2026\n" if complete else ""), metadata={}, document_format="PDF")

    def test_complete_si_uses_local_fields_without_ai(self):
        with patch.object(core, "extract_document", return_value=self.extraction(True)), patch.object(core, "_load_genai") as load:
            d = core.get_document_details("supp.pdf", "unused", allow_cloud_ai=True, allow_online_metadata_lookup=False)
        load.assert_not_called()
        self.assertEqual(core.build_proposed_filename(d, ".pdf"), "Smith_and_Aubrey_et_al_Journal_2026_SI.pdf")
        self.assertEqual(d["missing_citation_fields"], [])

    def test_incomplete_si_uses_ai_only_for_missing_fields(self):
        self.assertTrue(core._load_genai())
        client = MagicMock()
        client.models.generate_content.return_value.text = json.dumps({"creators": ["Wrong Name"], "journal": "Journal", "year": "2026", "document_type": "journal_article"})
        with patch.object(core, "extract_document", return_value=self.extraction()), patch.object(core.genai, "Client", return_value=client):
            d = core.get_document_details("supp.pdf", "test-key", allow_cloud_ai=True, allow_online_metadata_lookup=False)
        client.models.generate_content.assert_called_once()
        client.close.assert_called_once()
        self.assertEqual(core.build_proposed_filename(d, ".pdf"), "Smith_and_Aubrey_et_al_Journal_2026_SI.pdf")
        self.assertEqual(d["missing_citation_fields"], [])

    def test_ai_disallowed_keeps_missing_fields_explicit(self):
        with patch.object(core, "extract_document", return_value=self.extraction()), patch.object(core, "_load_genai") as load:
            d = core.get_document_details("supp.docx", "test-key", allow_cloud_ai=False, allow_online_metadata_lookup=False)
        load.assert_not_called()
        self.assertEqual(core.build_proposed_filename(d, ".docx"), "Smith_and_Aubrey_et_al_UnknownJournal_UnknownYear_SI.docx")
        self.assertTrue(d["needs_review"])
        self.assertEqual(d["missing_citation_fields"], ["journal", "year"])

    def test_wrapped_si_byline_has_six_people_and_no_creation_year(self):
        text = ("Supporting Information:\nAn Example Study of Carefully Prepared\nMaterials with a Long Wrapped\nTitle\n"
                "Morgan James Smith, Taylor Alex Aubrey, Alex Example,\n"
                "Jordan Robin Lee Doe, Harry Brown, and Jonathan De Roo\u2217\nDepartment of Chemistry\nContents\nReferences 2020")
        extraction = core.DocumentExtraction(text=text, metadata={"creation_date": "D:20260101"})
        with patch.object(core, "extract_document", return_value=extraction):
            d = core.get_basic_document_details("supp.pdf")
        self.assertEqual(len(d["creators"]), 6)
        self.assertEqual(d["creators"][0], "Morgan James Smith")
        self.assertEqual(d["creators"][-1], "Jonathan De Roo")
        self.assertEqual(d["year"], "Unknown")
        self.assertEqual(core.build_proposed_filename(d, ".pdf"), "Smith_et_al_UnknownJournal_UnknownYear_SI.pdf")

class ServiceError(Exception):
    def __init__(self, code):
        self.code = code

class RecoveryTests(unittest.TestCase):
    def metadata(self, errors):
        core._load_genai()
        client = MagicMock()
        client.models.generate_content.side_effect = errors
        extraction = core.DocumentExtraction(text="Supporting Information\nA Long Example Article Title\nAuthors: Jane Smith\n", metadata={}, document_format="PDF")
        with patch.object(core, "extract_document", return_value=extraction), patch.object(core.genai, "Client", return_value=client), patch.object(core.time, "sleep") as sleep:
            details = core.get_document_details("supp.pdf", "fake", allow_cloud_ai=True, allow_online_metadata_lookup=False)
        return details, client, sleep

    def test_overload_retries_once_and_recovers(self):
        response = Mock(text=json.dumps({"journal":"Journal", "year":"2026", "document_type":"journal_article"}))
        d, client, sleep = self.metadata([ServiceError(503), response])
        self.assertEqual(client.models.generate_content.call_count, 2)
        sleep.assert_called_once_with(1.0)
        self.assertEqual(core.build_proposed_filename(d, ".pdf"), "Smith_Journal_2026_SI.pdf")
        self.assertFalse(d.get("ai_retry_available",False))
        client.close.assert_called_once()

    def test_persistent_overload_is_explained_and_bounded(self):
        d, client, sleep = self.metadata([ServiceError(503)] * 3)
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertTrue(d["ai_retry_available"])
        self.assertIn("AI temporarily unavailable",d["review_reasons"][0])
        self.assertIn("journal, year",d["review_reasons"][0])
        self.assertEqual(d["document_type_label"],"Supporting Information")
        client.close.assert_called_once()

    def test_invalid_key_and_quota_are_not_automatically_retried(self):
        for code in (400,401,403,429):
            with self.subTest(code=code):
                d, client, sleep = self.metadata([ServiceError(code)])
                client.models.generate_content.assert_called_once()
                sleep.assert_not_called()
                self.assertTrue(d["ai_retry_available"])

    def test_title_joins_opening_lines_and_stops_before_authors_and_contents(self):
        text="Supporting Information:\nMechanism-Guided Preparation of Early\nTransition Metals to Access Novel Oxo\nClusters\nJane Smith, John Doe, Alex Brown\nDepartment of Chemistry\nContents\n3.3 TGA of clusters . . . . . . . S-23"
        self.assertEqual(core._title_from_text(text), "Mechanism-Guided Preparation of Early Transition Metals to Access Novel Oxo Clusters")
        self.assertEqual(core._title_from_text("Quantum Materials\nJane Smith\nAbstract"), "Quantum Materials")
        self.assertEqual(core._title_from_text("A Long Example Article Title\nAuthors: Jane Smith\nJournal: Example"), "A Long Example Article Title")
        self.assertEqual(core._title_from_text("Contents\n3.3 Long contents item . . . S-23"), "")
