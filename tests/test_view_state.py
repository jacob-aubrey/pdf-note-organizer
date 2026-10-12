"""Read-only UI snapshots stay small and invalidate only changed note content."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from note_organizer.remarkable_sync import default_config
from note_organizer.storage import Store
from note_organizer.view_state import cloud_destinations, read_view


class ViewStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "Library with spaces"
        self.store = Store(self.data / "notes.sqlite3")
        self.pc = self.root / "Sorted"
        self.pc.mkdir()
        self.pid = self.store.add_project(self.pc)
        self.pdf = self.pc / "article.pdf"
        self.pdf.write_bytes(b"Synthetic article source")
        self.image_marker = "large synthetic crop payload:"
        self.entries = [
            {"key": "drawing-1", "kind": "drawing", "page": 1, "rect": [1, 2, 3, 4],
             "comment": "Initial handwriting transcription", "image": self.image_marker * 10000},
            {"key": "highlight-1", "kind": "highlight", "page": 1, "rect": [2, 3, 4, 5],
             "quote": "A selected result", "image": ""},
        ]
        self.save_notes(self.entries)

    def tearDown(self):
        self.temp.cleanup()

    def save_notes(self, entries):
        self.store.save_scan(self.pid, self.pdf, "same-pdf-digest", "same-file-signature", "same-extraction-settings",
                             {"title": "Synthetic article"}, entries)

    def test_snapshot_is_read_only_and_retains_database_bytes(self):
        before = self.store.path.read_bytes()
        view = read_view(self.store.path)
        self.assertEqual(view.project(self.pid)["id"], self.pid)
        self.assertEqual(len(view.documents(self.pid)), 1)
        self.assertEqual(self.store.path.read_bytes(), before)
        # Read-only mode also refuses to silently create a missing library.
        missing = self.data / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            read_view(missing)
        self.assertFalse(missing.exists())

    def test_snapshot_omits_large_note_images_but_keeps_document_counts(self):
        view = read_view(self.store.path)
        self.assertEqual(view.documents()[0]["count"], 2)
        self.assertNotIn(self.image_marker, repr(vars(view)))
        self.assertNotIn("image", view.documents()[0])
        self.assertNotIn("payload", view.documents()[0])
        self.assertLess(len(repr(vars(view))), len(self.entries[0]["image"]) // 10)

    def test_hidden_documents_are_absent_without_changing_visible_counts(self):
        hidden_pdf = self.pc / "hidden.pdf"
        hidden_pdf.write_bytes(b"Separate synthetic article")
        self.store.save_scan(self.pid, hidden_pdf, "hidden-digest", "hidden-signature", "same-extraction-settings",
                             {"title": "Hidden article"}, [{**self.entries[1], "key": "hidden-highlight"}])
        self.store.relocate_source(hidden_pdf, self.root / "Elsewhere" / "hidden.pdf")
        self.store.scan_result(self.pid, self.pdf, "Synthetic read issue")
        view = read_view(self.store.path)
        self.assertEqual(len(view.documents(self.pid)), 1)
        self.assertEqual(view.documents(self.pid)[0]["count"], 2)
        self.assertEqual(view.errors(self.pid)[0]["error"], "Synthetic read issue")
        self.assertFalse(view.documents(self.pid + 100))

    def test_note_token_stays_stable_for_export_and_cloud_only_changes(self):
        initial = read_view(self.store.path)
        self.store.export_result(self.pid, "new-notebook-hash")
        self.store.set_preference("remarkable", {**default_config(self.data), "source_folder_id": "literature-id", "enabled": True})
        self.store.set_preference("remarkable_last_check", {"at": "synthetic-check", "source_pdf_count": 4})
        self.store.save_remarkable_item("cloud-only", {"state": "review", "name": "Another cloud article"})
        refreshed = read_view(self.store.path)
        self.assertNotEqual(initial.project(self.pid)["dirty"], refreshed.project(self.pid)["dirty"])
        self.assertEqual(initial.note_token(), refreshed.note_token())
        document_id = refreshed.documents()[0]["id"]
        self.assertEqual(refreshed.note_token(self.pid, document_id), refreshed.note_token())
        self.assertEqual(refreshed.note_token(self.pid + 100), ())

    def test_note_token_changes_when_note_text_changes_at_the_same_count(self):
        before = read_view(self.store.path)
        revised = deepcopy(self.entries)
        revised[0]["comment"] = "Corrected handwriting transcription"
        self.save_notes(revised)
        after = read_view(self.store.path)
        self.assertEqual(before.documents()[0]["count"], after.documents()[0]["count"])
        self.assertEqual(before.documents()[0]["digest"], after.documents()[0]["digest"])
        self.assertNotEqual(before.note_token(), after.note_token())
        self.save_notes(revised)
        self.assertEqual(after.note_token(), read_view(self.store.path).note_token())

    def test_filesystem_cache_is_frozen_until_the_next_snapshot(self):
        token = self.data / "remarkable" / "device-token.dpapi"
        token.parent.mkdir(parents=True)
        token.write_bytes(b"Synthetic protected-token placeholder")
        review = self.data / "reMarkable Review" / "review.pdf"
        review.parent.mkdir()
        review.write_bytes(b"Synthetic retained copy")
        missing = review.parent / "missing.pdf"
        self.store.save_remarkable_item("review", {"state": "review", "review_pdf": str(review)})
        self.store.save_remarkable_item("missing-review", {"state": "review", "review_pdf": str(missing)})
        configured = self.root / "Configured destination"
        configured.mkdir()
        mapped = self.root / "Mapped destination"
        mapped.mkdir()
        self.store.set_preference("remarkable", {**default_config(self.data), "pc_root": str(configured),
                                                "mappings": {"mapped": str(mapped), "missing": str(self.root / "Unavailable")}})
        before = read_view(self.store.path)
        project_root = before.project(self.pid)["root"]
        self.assertTrue({project_root, str(configured), str(mapped)}.issubset(before.directories))
        self.assertTrue({str(token), str(review)}.issubset(before.files))
        self.assertNotIn(str(missing), before.files)
        token.unlink()
        review.unlink()
        configured.rmdir()
        self.assertIn(str(token), before.files)
        self.assertIn(str(configured), before.directories)
        after = read_view(self.store.path)
        self.assertNotIn(str(token), after.files)
        self.assertNotIn(str(review), after.files)
        self.assertNotIn(str(configured), after.directories)

    def test_cloud_destinations_follow_scoped_ids_and_exact_folder_matches(self):
        research = self.pc / "Research"
        research.mkdir()
        mapped = self.pc / "Specific counterpart"
        mapped.mkdir()
        catalog = [
            {"id": "lit", "name": "Literature", "ancestor_ids": [], "path": "/Literature"},
            {"id": "research", "name": "Research", "ancestor_ids": ["lit"], "path": "/Literature/Research"},
            {"id": "nested", "name": "Nested", "ancestor_ids": ["lit", "research"], "path": "/Literature/Research/Nested"},
            {"id": "outside", "name": "Research", "ancestor_ids": [], "path": "/Research"},
        ]
        config = {**default_config(self.data), "source_folder_id": "lit", "pc_root": str(self.pc)}
        unchanged = deepcopy(config)
        targets, ready = cloud_destinations(catalog, config, self.data)
        self.assertTrue(ready)
        self.assertEqual(targets, {"lit": str(self.pc.resolve()), "research": str(research.resolve()), "nested": "Needs mapping"})
        self.assertEqual(config, unchanged)
        config["mappings"] = {"nested": str(mapped), "outside": str(mapped)}
        targets, _ = cloud_destinations(catalog, config, self.data)
        self.assertEqual(targets["nested"], str(mapped.resolve()))
        self.assertNotIn("outside", targets)
        external = self.root / "Outside linked root"
        external.mkdir()
        config["mappings"]["nested"] = str(external)
        targets, _ = cloud_destinations(catalog, config, self.data)
        self.assertEqual(targets["nested"], "Needs mapping")

    def test_cloud_destinations_exclude_review_and_private_cache_routes(self):
        catalog = [{"id": "lit", "name": "Literature", "ancestor_ids": [], "path": "/Literature"}]
        config = {**default_config(self.data), "source_folder_id": "lit", "pc_root": str(self.pc)}
        for excluded in (Path(config["review_dir"]), self.data / "remarkable" / "Nested"):
            with self.subTest(destination=excluded):
                excluded.mkdir(parents=True, exist_ok=True)
                config["mappings"] = {"lit": str(excluded)}
                targets, ready = cloud_destinations(catalog, config, self.data)
                self.assertEqual(targets, {"lit": "Needs mapping"})
                self.assertTrue(ready)


if __name__ == "__main__":
    unittest.main()
