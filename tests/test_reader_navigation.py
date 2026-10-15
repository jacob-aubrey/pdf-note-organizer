"""Shared main-search occurrences follow visible results and enabled fields."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from note_organizer.reader_navigation import current_target, match_locations, navigation_target
from note_organizer.reader_results import result_excerpt, result_tooltip
from note_organizer.research_search import enrich_note_matches, search_library
from note_organizer.research_tools import saved_search_options
from note_organizer.storage import DEFAULT_SEARCH_FIELDS, SEARCH_FIELDS, Store, digest_file, matches_search, search_values


def note(**changes):
    return {"path": "paper.pdf", "document_id": "one", "key": "note", "kind": "highlight",
            "page": 1, "rect": [0, 0, 10, 10], "quote": "", "comment": "", "context": "", **changes}


class NoteOccurrenceTests(unittest.TestCase):
    def test_all_positive_occurrences_across_enabled_fields_keep_field_offsets(self):
        entry = note(quote="Tantalum and TANTALUM", comment="A tantalum note",
                     ocr="tantalum handwriting", context="Tantalum outside the note")
        enrich_note_matches(entry, "tantalum", ["quote", "comment", "ocr", "context"])
        self.assertEqual(entry["match_count"], 5)
        self.assertEqual([hit["field"] for hit in entry["search_hits"]],
                         ["quote", "quote", "comment", "ocr", "context"])
        values = search_values(entry)
        for index, hit in enumerate(entry["search_hits"]):
            self.assertEqual(values[hit["field"]][hit["start"]:hit["end"]], hit["text"])
            excerpt = entry["match_excerpts"][hit["excerpt_index"]]
            self.assertEqual(excerpt["field"], hit["field"])
            self.assertIn(index, excerpt["hit_indices"])

    def test_surrounding_text_is_off_by_default_and_explicitly_identified_when_enabled(self):
        entry = note(context="Tantalum appears beside this unrelated highlight", quote="Other words")
        enrich_note_matches(entry, "tantalum")
        self.assertEqual(entry["search_hits"], [])
        enrich_note_matches(entry, "tantalum", ["context"])
        self.assertEqual(entry["match_count"], 1)
        self.assertEqual(entry["search_hits"][0]["source_label"], "Match in surrounding text")
        self.assertIn("Tantalum", entry["match_excerpts"][0]["text"])

    def test_excluded_fields_never_leak_into_occurrences(self):
        entry = note(quote="gold", comment="gold", context="gold", ocr="gold",
                     metadata={"title": "Gold title"})
        enrich_note_matches(entry, "gold", ["comment"])
        self.assertEqual([hit["field"] for hit in entry["search_hits"]], ["comment"])
        enrich_note_matches(entry, "gold", [])
        self.assertEqual(entry["search_hits"], [])

    def test_identical_note_passages_share_navigation_and_retain_all_enabled_sources(self):
        passage = "Gold and more gold."
        entry = note(quote=passage, comment=passage, ocr=passage)
        enrich_note_matches(entry, "gold", ["quote", "comment", "ocr"])
        self.assertEqual(entry["match_count"], 2)
        self.assertEqual(len(entry["match_excerpts"]), 1)
        for item in [*entry["search_hits"], *entry["match_excerpts"]]:
            self.assertEqual(item["field"], "quote")
            self.assertEqual(item["fields"], ["quote", "comment", "ocr"])
            self.assertEqual(item["source_labels"], ["Match in highlighted text", "Match in typed note",
                                                     "Match in handwriting transcription"])
        self.assertEqual([entry[field] for field in ("quote", "comment", "ocr")], [passage] * 3)
        locations = match_locations([entry], ["0"])
        self.assertEqual([target.hit_index for target in locations], [0, 1])
        self.assertEqual(navigation_target([entry], ["0"], "0", 1).hit_index, 0)

    def test_shared_passages_keep_only_enabled_sources_and_rebuild_after_filter_changes(self):
        entry = note(quote="gold gold", comment="gold gold", ocr="gold gold")
        enrich_note_matches(entry, "gold", ["comment", "ocr"])
        self.assertEqual(entry["match_count"], 2)
        self.assertTrue(all(hit["field"] == "comment" and hit["fields"] == ["comment", "ocr"]
                            for hit in entry["search_hits"]))
        enrich_note_matches(entry, "gold", ["ocr"])
        self.assertTrue(all(hit["field"] == "ocr" and hit["fields"] == ["ocr"]
                            for hit in entry["search_hits"]))

    def test_case_whitespace_context_and_metadata_remain_distinct_passages(self):
        entry = note(quote="Gold", comment="gold", ocr="Gold ", context="Gold",
                     metadata={"title": "Gold"})
        enrich_note_matches(entry, "gold", ["quote", "comment", "ocr", "context", "title"])
        self.assertEqual(entry["match_count"], 5)
        self.assertEqual([hit["fields"] for hit in entry["search_hits"]],
                         [["quote"], ["comment"], ["ocr"], ["context"], ["title"]])

    def test_boolean_and_phrase_offsets_casefold_and_excluded_terms(self):
        entry = note(quote="Straße and Spectral\n  CT and STRASSE; iodine")
        enrich_note_matches(entry, 'strasse OR "spectral ct" NOT iodine', ["quote"])
        self.assertEqual([hit["text"] for hit in entry["search_hits"]],
                         ["Straße", "Spectral\n  CT", "STRASSE"])
        self.assertEqual(entry["match_count"], 3)
        enrich_note_matches(entry, "NOT iodine", ["quote"])
        self.assertFalse(entry["search_hits"])
        enrich_note_matches(entry, "NOT NOT strasse", ["quote"])
        self.assertEqual(entry["match_count"], 2)

    def test_metadata_only_hits_show_actual_source_without_fabricating_note_text(self):
        entry = note(quote="Unrelated text", metadata={"title": "Gold imaging", "author": "Gold, Jane"})
        enrich_note_matches(entry, "gold", ["title", "author"])
        self.assertEqual(entry["quote"], "Unrelated text")
        self.assertEqual([hit["source_label"] for hit in entry["search_hits"]],
                         ["Match in paper title", "Match in author"])
        self.assertEqual([group["text"] for group in entry["match_excerpts"]],
                         ["Gold imaging", "Gold, Jane"])

    def test_enrichment_does_not_change_boolean_match_acceptance(self):
        entry = note(quote="gold", comment="iodine")
        for query, expected in (("gold AND iodine", True), ("gold NOT iodine", False),
                                ("NOT cobalt", True), ("cobalt OR NOT silver", True)):
            with self.subTest(query=query):
                before = matches_search(entry, query, ["quote", "comment"], "All words", "All notes")
                enrich_note_matches(entry, query, ["quote", "comment"])
                self.assertEqual(before, expected)
                self.assertEqual(matches_search(entry, query, ["quote", "comment"], "All words", "All notes"), before)

    def test_blank_query_clears_cached_occurrence_metadata(self):
        entry = enrich_note_matches(note(quote="gold gold"), "gold", ["quote"])
        self.assertEqual(entry["match_count"], 2)
        enrich_note_matches(entry, "   ", ["quote"])
        self.assertEqual((entry["search_hits"], entry["match_excerpts"], entry["match_count"]), ([], [], 0))

    def test_exact_phrase_treats_boolean_operators_as_text(self):
        entry = note(quote="gold AND iodine, then gold.")
        enrich_note_matches(entry, "gold AND iodine", ["quote"], "Exact phrase")
        self.assertEqual([hit["text"] for hit in entry["search_hits"]], ["gold AND iodine"])

    def test_overlapping_phrases_count_one_occurrence_and_retain_both_terms(self):
        entry = enrich_note_matches(note(quote="Gold imaging and gold"), 'gold OR "gold imaging"', ["quote"])
        self.assertEqual(entry["match_count"], 2)
        self.assertEqual(entry["search_hits"][0]["terms"], ["gold", "gold imaging"])

    def test_result_excerpt_explains_context_only_matches_and_tooltip_counts_the_note(self):
        entry = enrich_note_matches(note(quote="Unrelated highlight", context="Gold outside the highlight"),
                                    "gold", ["context"])
        self.assertEqual(result_excerpt(entry), "Match in surrounding text: Gold outside the highlight")
        self.assertIn("1 search occurrence in this result", result_tooltip(entry))
        self.assertNotIn("1 search occurrence on this page", result_tooltip(entry))

    def test_result_excerpt_prefers_actual_matching_note_field_over_unrelated_comment(self):
        entry = enrich_note_matches(note(quote="Gold highlighted", comment="Unrelated note"), "gold", ["quote"])
        self.assertEqual(result_excerpt(entry), "Gold highlighted")


class MatchNavigationTests(unittest.TestCase):
    def setUp(self):
        self.entries = [enrich_note_matches(note(quote="gold gold"), "gold", ["quote"]),
                        note(kind="drawing"),
                        {"kind": "pdf", "search_hits": [{"field": "pdf", "text": "gold"}]}]

    def test_visible_row_order_controls_navigation_and_count(self):
        locations = match_locations(self.entries, ["2", "0", "1"])
        self.assertEqual([(target.row, target.hit_index) for target in locations],
                         [("2", 0), ("0", 0), ("0", 1), ("1", None)])
        self.assertEqual([target.ordinal for target in locations], [1, 2, 3, 4])
        self.assertTrue(all(target.total == 4 for target in locations))

    def test_next_moves_within_note_then_to_next_result_and_wraps(self):
        target = navigation_target(self.entries, ["0", "1", "2"], "0", 0)
        self.assertEqual((target.row, target.hit_index, target.ordinal), ("0", 1, 2))
        target = navigation_target(self.entries, ["0", "1", "2"], target.row, target.hit_index)
        self.assertEqual((target.row, target.hit_index), ("1", None))
        target = navigation_target(self.entries, ["0", "1", "2"], "2", 0)
        self.assertEqual((target.row, target.hit_index, target.ordinal), ("0", 0, 1))

    def test_previous_moves_across_results_and_wraps(self):
        target = navigation_target(self.entries, ["0", "1", "2"], "0", 0, -1)
        self.assertEqual((target.row, target.hit_index, target.ordinal), ("2", 0, 4))
        target = navigation_target(self.entries, ["0", "1", "2"], "1", None, -1)
        self.assertEqual((target.row, target.hit_index), ("0", 1))

    def test_no_selection_chooses_first_or_last_and_empty_list_disables_navigation(self):
        self.assertEqual(navigation_target(self.entries, ["0", "1"]).row, "0")
        self.assertEqual(navigation_target(self.entries, ["0", "1"], step=-1).row, "1")
        self.assertIsNone(navigation_target(self.entries, []))
        self.assertIsNone(current_target(self.entries, ["0", "1"]))

    def test_current_counter_does_not_navigate_and_recovers_stale_hit(self):
        target = current_target(self.entries, ["2", "0", "1"], "0", 1)
        self.assertEqual((target.row, target.hit_index, target.ordinal), ("0", 1, 3))
        target = current_target(self.entries, ["2", "0", "1"], "0", 99)
        self.assertEqual((target.row, target.hit_index, target.ordinal), ("0", 0, 2))

    def test_stale_invalid_duplicate_and_negative_rows_are_skipped(self):
        locations = match_locations(self.entries, ["2", "bad", "-1", "999", "2", "0"])
        self.assertEqual([(target.row, target.hit_index) for target in locations], [("2", 0), ("0", 0), ("0", 1)])

    def test_browse_and_not_only_results_still_have_one_stop_each(self):
        entries = [note(kind="drawing"), {"kind": "pdf", "pdf_document": True},
                   enrich_note_matches(note(quote="gold"), "NOT iodine", ["quote"])]
        self.assertEqual([(target.row, target.hit_index) for target in match_locations(entries, ["0", "1", "2"])],
                         [("0", None), ("1", None), ("2", None)])


class SearchDefaultTests(unittest.TestCase):
    def test_default_fields_omit_only_surrounding_text(self):
        self.assertEqual(set(DEFAULT_SEARCH_FIELDS), set(SEARCH_FIELDS) - {"context"})

    def test_saved_search_missing_fields_gets_default_but_explicit_context_is_preserved(self):
        self.assertEqual(saved_search_options({})["fields"], list(DEFAULT_SEARCH_FIELDS))
        self.assertEqual(saved_search_options({"fields": None})["fields"], list(DEFAULT_SEARCH_FIELDS))
        saved = {"fields": ["context"], "scope": "All", "query": "gold"}
        loaded = saved_search_options(saved)
        self.assertEqual(loaded["fields"], ["context"])
        self.assertEqual(loaded["scope"], "All")
        loaded["fields"].append("quote")
        self.assertEqual(saved["fields"], ["context"])

    def test_library_defaults_exclude_surrounding_text_without_changing_explicit_search(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            store = Store(folder / "library.sqlite3")
            project = store.add_project(folder)
            source = folder / "paper.pdf"
            source.write_bytes(b"Source fixture; no PDF extraction is requested.")
            store.save_scan(project, source, digest_file(source), "sig", "settings", {},
                            [note(context="tantalum context", quote="Unrelated highlight")])
            worker = Mock()
            self.assertEqual(search_library(store, worker, "Notes", query="tantalum"), [])
            entry = search_library(store, worker, "Notes", query="tantalum", fields=["context"])[0]
            self.assertEqual(entry["match_count"], 1)
            self.assertEqual(entry["search_hits"][0]["field"], "context")
            self.assertEqual(worker.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
