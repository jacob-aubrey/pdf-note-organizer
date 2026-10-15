"""Every printed-text occurrence remains available without unbounded previews."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from note_organizer.research_search import excerpt, hit_excerpts, search_library
from note_organizer.storage import Store, digest_file


class HitExcerptTests(unittest.TestCase):
    def test_separated_occurrences_keep_exact_original_offsets(self):
        text = "First Tantalum reference. " + "other words " * 40 + "Second tantalum reference. " \
               + "more words " * 40 + "Third TANTALUM reference."
        hits = hit_excerpts(text, "tantalum")
        self.assertEqual([hit["text"] for hit in hits], ["Tantalum", "tantalum", "TANTALUM"])
        self.assertEqual([hit["excerpt_index"] for hit in hits], [0, 1, 2])
        for hit in hits:
            self.assertEqual(text[hit["start"]:hit["end"]], hit["text"])
            self.assertIn(hit["text"], hit["snippet"])
            self.assertLessEqual(hit["snippet_end"] - hit["snippet_start"], 260)
            self.assertFalse(hit["snippet_truncated"])

    def test_nearby_occurrences_share_context_without_losing_count(self):
        text = "Tantalum oxide, tantalum metal, and tantalum nanoparticles."
        hits = hit_excerpts(text, "tantalum")
        self.assertEqual(len(hits), 3)
        self.assertEqual([hit["excerpt_index"] for hit in hits], [0, 0, 0])
        self.assertEqual({hit["snippet"] for hit in hits}, {text})

    def test_overlapping_terms_and_phrases_describe_one_occurrence(self):
        text = "Gold imaging uses gold."
        hits = hit_excerpts(text, 'gold OR "gold imaging" NOT iodine')
        self.assertEqual([hit["text"] for hit in hits], ["Gold imaging", "gold"])
        self.assertEqual(hits[0]["terms"], ["gold", "gold imaging"])
        self.assertEqual(hit_excerpts("iodine gold", "NOT iodine"), [])
        self.assertEqual([hit["text"] for hit in hit_excerpts("iodine gold", "NOT NOT gold")], ["gold"])

    def test_adjacent_occurrences_are_counted_separately(self):
        hits = hit_excerpts("goldgold", "gold")
        self.assertEqual([(hit["start"], hit["end"]) for hit in hits], [(0, 4), (4, 8)])

    def test_unicode_casefold_and_wrapped_phrases_match_query_semantics(self):
        text = "Straße, then Spectral\n  CT, then STRASSE."
        hits = hit_excerpts(text, 'strasse OR "spectral ct"')
        self.assertEqual([hit["text"] for hit in hits], ["Straße", "Spectral\n  CT", "STRASSE"])
        self.assertIn("Spectral CT", hits[1]["snippet"])
        self.assertEqual([hit["text"] for hit in hit_excerpts(text, "Spectral CT", "Exact phrase")],
                         ["Spectral\n  CT"])

    def test_dense_matches_never_make_an_unbounded_excerpt_or_cap_occurrences(self):
        text = "gold ordinary context " * 300
        hits = hit_excerpts(text, "gold", max_length=100)
        self.assertEqual(len(hits), 300)
        self.assertGreater(hits[-1]["excerpt_index"], 0)
        for hit in hits:
            self.assertLessEqual(hit["snippet_end"] - hit["snippet_start"], 100)
            self.assertLessEqual(len(hit["snippet"]), 102)
            self.assertIn("gold", hit["snippet"])

    def test_single_match_longer_than_preview_is_explicit_and_remains_complete(self):
        term = "t" * 300
        hits = hit_excerpts("prefix " + term + " suffix", term, max_length=80)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["text"], term)
        self.assertTrue(hits[0]["snippet_truncated"])
        self.assertLessEqual(len(hits[0]["snippet"]), 82)

    def test_compatible_first_excerpt_uses_unicode_offsets_and_stays_bounded(self):
        text = "before " * 50 + "Straße visible here. " + "after " * 50
        quote = excerpt(text, "strasse", "All words")
        self.assertIn("Straße", quote)
        self.assertLessEqual(len(quote), 262)
        self.assertEqual(hit_excerpts(text, ""), [])


class SearchHitResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = Store(self.folder / "library.sqlite3")
        project = self.store.add_project(self.folder)
        self.path = self.folder / "paper.pdf"
        self.path.write_bytes(b"Disposable source; text extraction is supplied by the test worker.")
        self.store.save_scan(project, self.path, digest_file(self.path), "sig", "settings", {}, [])
        self.text = "Tantalum first. " + "unrelated words " * 30 + "tantalum second and TANTALUM third."
        self.worker = Mock()
        self.worker.text_pages.return_value = [{"page": 1, "pdf_label": "1", "text": self.text}]

    def tearDown(self):
        self.temp.cleanup()

    def test_page_results_include_all_occurrences_and_merged_excerpt_mapping(self):
        results = search_library(self.store, self.worker, "PDFs", query="tantalum")
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["match_count"], 3)
        self.assertEqual(len(result["search_hits"]), 3)
        self.assertEqual(len(result["match_excerpts"]), 2)
        self.assertEqual([group["hit_indices"] for group in result["match_excerpts"]], [[0], [1, 2]])
        self.assertEqual(result["quote"], result["match_excerpts"][0]["text"])
        self.assertEqual(result["context"], self.text)
        for index, hit in enumerate(result["search_hits"]):
            self.assertIn(index, result["match_excerpts"][hit["excerpt_index"]]["hit_indices"])

    def test_not_only_result_has_no_invented_positive_occurrences(self):
        result = search_library(self.store, self.worker, "PDFs", query="NOT iodine")[0]
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["search_hits"], [])
        self.assertEqual(result["match_excerpts"], [])
        self.assertTrue(result["quote"])

    def test_blank_catalog_browsing_does_not_extract_or_index_text(self):
        result = search_library(self.store, self.worker, "PDFs", query="")[0]
        self.assertTrue(result["pdf_document"])
        self.assertEqual(result["context"], "")
        self.assertNotIn("search_hits", result)
        self.assertEqual(self.worker.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
