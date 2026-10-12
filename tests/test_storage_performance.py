"""Image-heavy note queries should keep full snapshots off the UI path."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from note_organizer.storage import Store, DEFAULT_SETTINGS


class LightweightEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = Store(self.folder / "library.sqlite3")
        self.project_id = self.store.add_project(self.folder)
        entries = [{"key": f"note-{i}", "page": i+1, "label": str(i+1),
                    "kind": "highlight" if i % 2 == 0 else "drawing", "rect": [0, 0, 10, 10],
                    "quote": "Gold imaging" if i % 2 == 0 else "", "comment": "Verify results",
                    "ocr": "Check the signal", "context": "Control experiment", "color": "Yellow",
                    "image": f"large-image-{i}" * 10000}
                   for i in range(4)]
        self.store.save_scan(self.project_id, self.folder / "paper.pdf", "digest", "signature",
                             json.dumps(DEFAULT_SETTINGS), {"title": "A study", "author": "Example"}, entries)
        self.document_id = self.store.documents()[0]["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_lightweight_results_preserve_text_and_lazy_images(self):
        full = self.store.entries()
        light = self.store.entries(include_images=False)
        self.assertEqual([{k: v for k, v in e.items() if k != "image"} for e in full], light)
        self.assertTrue(all("image" not in e for e in light))
        for e in full:
            self.assertEqual(self.store.entry_image(e["document_id"], e["key"]), e["image"])
        self.assertEqual(self.store.entries(), full)

    def test_lightweight_search_and_type_filters_match_full_queries(self):
        for query, note_type in [("gold NOT phantom", "All notes"),
                                 ("signal", "Drawings and handwriting"),
                                 ("", "Highlights and markup")]:
            with self.subTest(query=query, note_type=note_type):
                full = self.store.entries(query=query, note_type=note_type)
                light = self.store.entries(query=query, note_type=note_type, include_images=False)
                self.assertEqual([e["key"] for e in full], [e["key"] for e in light])

    def test_blank_query_skips_parser_and_search_normalization(self):
        with patch("note_organizer.storage.compile_search") as parser, \
             patch("note_organizer.storage.normalize") as normalize:
            self.assertEqual(len(self.store.entries(query="  ", include_images=False)), 4)
        parser.assert_not_called()
        normalize.assert_not_called()

    def test_metadata_is_decoded_once_per_document(self):
        with patch("note_organizer.storage.json.loads", wraps=json.loads) as decode:
            self.assertEqual(len(self.store.entries(include_images=False)), 4)
        self.assertEqual(decode.call_count, 5)

    def test_missing_or_hidden_image_is_unavailable(self):
        self.assertEqual(self.store.entry_image(self.document_id, "missing"), "")
        self.assertEqual(self.store.entry_image("missing", "note-0"), "")
        with self.store.connect() as db:
            db.execute("UPDATE documents SET hidden=1 WHERE id=?", (self.document_id,))
        self.assertEqual(self.store.entry_image(self.document_id, "note-0"), "")
        self.assertFalse(self.store.entries(include_images=False))

    def test_query_can_cancel_before_start_or_between_rows(self):
        with self.assertRaises(InterruptedError):
            self.store.entries(include_images=False, cancelled=lambda: True)
        with self.assertRaises(InterruptedError):
            self.store.entries(include_images=False, cancelled=iter([False, False, True]).__next__)
        self.assertEqual(len(self.store.entries()), 4)

    def test_history_view_omits_images_without_removing_saved_snapshots(self):
        full = self.store.history(self.document_id)
        light = self.store.history(self.document_id, include_images=False)
        self.assertEqual(len(full), len(light))
        self.assertTrue(all("image" not in json.loads(row["payload"]) for row in light))
        self.assertTrue(all(json.loads(row["payload"])["image"] for row in full))
        self.assertEqual(self.store.history(self.document_id), full)


if __name__ == "__main__":
    unittest.main()
