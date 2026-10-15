"""Search acceptance, occurrence counts and source order share one text model."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import pymupdf as fitz

from note_organizer.pdf_worker import _text_pages
from note_organizer.extraction import extract
from note_organizer.reader_navigation import match_locations
from note_organizer.research_search import enrich_note_matches, file_version, hit_excerpts, search_library
from note_organizer.search import compile_search, match_spans, normalize
from note_organizer.storage import DEFAULT_SETTINGS, Store, digest_file, matches_search


class WrappedWordTests(unittest.TestCase):
    def test_only_discretionary_hyphen_breaks_are_removed(self):
        for raw in ("tanta-\nlum", "tanta-\r\n  lum", "tanta- lum", "tanta\u2010\nlum",
                    "tanta\u00adlum", "tanta\u00ad\nlum", "TANTA-\nLUM"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize(raw), "tantalum")
                self.assertEqual(match_spans(raw, ["tantalum"]), [(0, len(raw))])
                self.assertTrue(compile_search("tantalum")([normalize(raw)]))
        for raw in ("tantalum-based", "tantalum - based", "5-\n3", "A non\u2011breaking compound"):
            with self.subTest(literal=raw):
                self.assertEqual(normalize(raw), " ".join(raw.casefold().split()))

    def test_wrapped_and_plain_occurrences_keep_exact_original_offsets(self):
        text = "Tantalum first. tanta-\nlum second. tan\u00adtalum third."
        hits = hit_excerpts(text, "tantalum")
        self.assertEqual([hit["text"] for hit in hits], ["Tantalum", "tanta-\nlum", "tan\u00adtalum"])
        self.assertEqual([hit["term"] for hit in hits], ["tantalum"] * 3)
        for hit in hits:
            self.assertEqual(text[hit["start"]:hit["end"]], hit["text"])
            self.assertEqual(hit["normalized_text"], "tantalum")
            self.assertEqual(hit["terms"], ["tantalum"])
            self.assertEqual(hit["before"], text[max(0, hit["start"] - 100):hit["start"]])
            self.assertEqual(hit["after"], text[hit["end"]:hit["end"] + 100])

    def test_phrase_and_boolean_matching_share_wrapped_word_semantics(self):
        text = "Tanta-\nlum oxide has spec-\ntral\n  CT uses, without iodine."
        hits = hit_excerpts(text, '"tantalum oxide" OR "spectral ct"')
        self.assertEqual([hit["text"] for hit in hits], ["Tanta-\nlum oxide", "spec-\ntral\n  CT"])
        self.assertTrue(compile_search('"tantalum oxide" AND "spectral ct"')([normalize(text)]))
        self.assertFalse(compile_search("tantalum NOT iodine")([normalize(text)]))
        self.assertEqual(hit_excerpts(text, "NOT iodine"), [])

    def test_inline_compound_remains_searchable_as_a_literal_compound(self):
        text = "Tantalum-based and tanta-\nlum particles."
        hits = hit_excerpts(text, "tantalum-based")
        self.assertEqual([hit["text"] for hit in hits], ["Tantalum-based"])
        self.assertEqual(len(hit_excerpts(text, "tantalum")), 2)

    def test_adjacent_wrapped_and_casefolded_occurrences_remain_distinct(self):
        for text, query, expected in (
                ("tanta-\nlumtanta-\nlum", "tantalum OR tantalum", ["tanta-\nlum", "tanta-\nlum"]),
                ("tan\u00adtalumtantalum", "tantalum", ["tan\u00adtalum", "tantalum"]),
                ("StraßeSTRASSE", "strasse", ["Straße", "STRASSE"]),
                ("goldgold", 'gold OR "gold"', ["gold", "gold"])):
            with self.subTest(text=text):
                hits = hit_excerpts(text, query)
                self.assertEqual([hit["text"] for hit in hits], expected)
                self.assertEqual(hits[0]["end"], hits[1]["start"])
                entry = {"search_hits": hits}
                self.assertEqual([target.hit_index for target in match_locations([entry], ["0"])], [0, 1])

    def test_overlapping_nonprefix_terms_retain_the_complete_hit_for_pdf_mapping(self):
        text = "Gold imaging, then gold."
        hits = hit_excerpts(text, 'gold OR "old imaging"')
        self.assertEqual([hit["text"] for hit in hits], ["Gold imaging", "gold"])
        self.assertEqual(hits[0]["normalized_text"], "gold imaging")
        self.assertEqual(hits[0]["terms"], ["gold", "old imaging"])

    def test_note_filter_count_and_navigation_include_wrapped_extracted_words(self):
        # Stored highlight quotations join selected PDF words with spaces, while
        # comments/OCR may retain their actual line breaks. Both forms occur in
        # existing libraries; no rescan or mutation of their source is needed.
        entry = {"path": "paper.pdf", "kind": "highlight", "key": "one", "page": 1,
                 "quote": "tanta- lum sample and tantalum", "comment": "tanta-\nlum note",
                 "metadata": {"title": "Tantalum title"}}
        self.assertTrue(matches_search(entry, "tantalum", ["quote", "comment"], "All words", "All notes"))
        enrich_note_matches(entry, "tantalum", ["quote", "comment"])
        self.assertEqual(entry["match_count"], 3)
        self.assertEqual([hit["field"] for hit in entry["search_hits"]], ["quote", "quote", "comment"])
        self.assertEqual([target.hit_index for target in match_locations([entry], ["0"])], [0, 1, 2])
        self.assertEqual(entry["quote"], "tanta- lum sample and tantalum")


class PDFSearchReadingOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.path = self.folder / "columns.pdf"
        with fitz.open() as document:
            page = document.new_page(width=600, height=800)
            # A scientific PDF's text stream reads down the left column, then
            # down the right. Their aligned baselines expose the old sort=True
            # row-interleaving bug without imposing our own column heuristic.
            page.insert_text((40, 80), "Left first tantalum observation.")
            page.insert_text((40, 110), "Left second tantalum observation.")
            page.insert_text((330, 80), "Right first tantalum observation.")
            page.insert_text((330, 110), "Right second tantalum observation.")
            page.insert_text((40, 160), "Wrapped tanta-")
            page.insert_text((40, 175), "lum observation.")
            document.save(self.path)
        self.store = Store(self.folder / "library.sqlite3")
        self.project = self.store.add_project(self.folder)
        self.store.save_scan(self.project, self.path, digest_file(self.path), "sig", "settings", {}, [])
        self.document = self.store.documents()[0]["id"]
        self.worker = Mock()
        self.worker.text_pages.side_effect = _text_pages

    def tearDown(self):
        self.temp.cleanup()

    def test_page_hits_follow_pdf_source_flow_and_preserve_wrapped_hit(self):
        original = self.path.read_bytes()
        with fitz.open(self.path) as document:
            flow = document[0].get_text(sort=False)
            row_order = document[0].get_text(sort=True)
        self.assertNotEqual(flow, row_order)
        self.assertLess(row_order.index("Right first"), row_order.index("Left second"))
        self.assertLess(flow.index("Left second"), flow.index("Right first"))
        result = search_library(self.store, self.worker, "PDFs", query="tantalum")[0]
        self.assertEqual(result["context"], flow)
        self.assertEqual(result["match_count"], 5)
        self.assertEqual([hit["before"].splitlines()[-1].strip() for hit in result["search_hits"]],
                         ["Left first", "Left second", "Right first", "Right second", "Wrapped"])
        self.assertEqual(result["search_hits"][-1]["text"], "tanta-\nlum")
        self.assertEqual(self.path.read_bytes(), original)

    def test_surrounding_note_text_keeps_the_same_column_flow(self):
        with fitz.open(self.path) as document:
            document[0].add_text_annot((270, 120), "A margin comment")
            data = document.tobytes()
        self.path.write_bytes(data)
        _, _, _, entries = extract(self.path, {**DEFAULT_SETTINGS, "context_padding": 1000})
        entry = entries[0]
        entry["path"] = str(self.path)
        enrich_note_matches(entry, "tantalum", ["context"])
        self.assertEqual(entry["match_count"], 5)
        self.assertEqual([hit["before"].splitlines()[-1].strip() for hit in entry["search_hits"]],
                         ["Left first", "Left second", "Right first", "Right second", "Wrapped"])

    def test_wrapped_word_index_candidates_and_cached_counts_match_full_text(self):
        for query in ("tantalum", '"tantalum observation"', '"tantalum observation" NOT iodine'):
            with self.subTest(query=query):
                result = search_library(self.store, self.worker, "PDFs", query=query)[0]
                expected = hit_excerpts(result["context"], query)
                self.assertEqual(result["search_hits"], [dict(hit, field="pdf", source_label="Match in PDF text")
                                                        for hit in expected])
                self.assertTrue(any("tanta-\nlum" in hit["text"] for hit in result["search_hits"]))
        self.store = Store(self.store.path)
        self.assertEqual(search_library(self.store, self.worker, "PDFs", query="tantalum")[0]["match_count"], 5)
        self.worker.text_pages.assert_called_once()

    def test_prior_sorting_and_normalization_cache_is_rebuilt_once(self):
        old_version = json.dumps(json.loads(file_version(self.path))[:-1])
        self.store.cache_pdf_pages(self.document, digest_file(self.path), old_version,
                                   [{"page": 1, "pdf_label": "", "text": "Old cache misses the wrapped word."}])
        result = search_library(self.store, self.worker, "PDFs", query="tantalum")[0]
        self.assertEqual(result["match_count"], 5)
        self.assertEqual(search_library(self.store, self.worker, "PDFs", query="tantalum")[0]["match_count"], 5)
        self.worker.text_pages.assert_called_once()


if __name__ == "__main__":
    unittest.main()
