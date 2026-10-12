"""Synthetic regressions for issue feedback, preferences, and cloud checks."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from note_organizer.remarkable_cloud import CloudError
from note_organizer.remarkable_sync import RemarkableSync
from note_organizer.service import Service
from note_organizer.storage import DEFAULT_SETTINGS, Store
from tests.test_remarkable import fixture, folder


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.store.set_preference("remarkable", {"integration_enabled": True})
        self.service = Service(self.store)

    def tearDown(self):
        self.service.stop()
        self.temp.cleanup()

    def clean_project(self):
        watched = self.root / "Research"
        watched.mkdir()
        pid = self.store.add_project(watched)
        Path(self.store.project(pid)["output"]).write_bytes(b"Existing notebook")
        self.store.export_result(pid, "existing-notebook-version")
        return watched, pid

    def run_preference_commands(self):
        self.service.remarkable.sync = Mock(side_effect=lambda **kwargs: self.service.stop() or False)
        self.service.run()

    def test_missing_watched_folder_is_reported_apart_from_pdf_read_errors(self):
        self.store.add_project(self.root / "Offline drive")
        self.service.sync()
        summary = self.store.preference("sync_summary")
        self.assertEqual(summary["unavailable_folders"], 1)
        self.assertEqual(summary["pdf_errors"], 0)
        self.assertEqual(summary["unreadable_folders"], 0)
        self.assertEqual(summary["export_waiting"], 1)
        self.assertEqual({d["kind"] for d in summary["details"]}, {"unavailable_folder", "export_waiting"})
        final_text = list(self.service.messages.queue)[-1][0]
        self.assertIn("unavailable folders: 1", final_text)
        self.assertNotIn("PDF read errors", final_text)

    def test_unreadable_directory_is_reported_apart_from_pdf_read_errors(self):
        watched, _ = self.clean_project()
        denied = watched / "Restricted"

        def walk(path, onerror):
            onerror(PermissionError(13, "Permission denied", str(denied)))
            yield str(watched), [], []

        with patch("note_organizer.service.os.walk", side_effect=walk):
            self.service.sync()
        summary = self.store.preference("sync_summary")
        self.assertEqual(summary["unavailable_folders"], 0)
        self.assertEqual(summary["unreadable_folders"], 1)
        self.assertEqual(summary["pdf_errors"], 0)
        self.assertEqual(summary["export_waiting"], 0)
        self.assertEqual(summary["details"][0]["path"], str(denied))

    def test_corrupt_pdf_is_reported_with_its_path_and_retry_details(self):
        watched, _ = self.clean_project()
        pdf = watched / "corrupt.pdf"
        pdf.write_bytes(b"Unreadable PDF")
        with self.assertLogs(level="ERROR"):
            self.service.sync()
        summary = self.store.preference("sync_summary")
        self.assertEqual(summary["pdf_errors"], 1)
        self.assertEqual(summary["unavailable_folders"], 0)
        self.assertEqual(summary["unreadable_folders"], 0)
        self.assertEqual(summary["details"][0]["kind"], "pdf_error")
        self.assertTrue(summary["details"][0]["message"])
        self.assertEqual(Path(summary["details"][0]["path"]), pdf)
        self.assertTrue(self.service.pending)

    def test_locked_notebook_is_counted_as_export_waiting(self):
        _, pid = self.clean_project()
        self.store.mark_dirty(pid)
        with self.assertLogs(level="ERROR"):
            with patch("note_organizer.service.export_notebook", side_effect=PermissionError("Word lock")):
                self.service.sync()
        summary = self.store.preference("sync_summary")
        self.assertEqual(summary["export_waiting"], 1)
        self.assertEqual(summary["pdf_errors"], 0)
        self.assertEqual(summary["details"][0]["kind"], "export_waiting")
        self.assertIn("Word lock", summary["details"][0]["message"])

    def test_intentional_close_during_manual_cloud_sync_preserves_previous_error(self):
        self.store.set_preference("remarkable_error", "Earlier connection error")

        def cancel(**kwargs):
            self.service.stop()
            raise InterruptedError("reMarkable sync stopped")

        self.service.remarkable.sync = Mock(side_effect=cancel)
        self.service.command("remarkable_sync")
        self.service.run()
        self.assertEqual(self.store.preference("remarkable_error"), "Earlier connection error")
        self.assertFalse(self.service.cloud_busy)
        self.assertFalse(any("Background operation failed" in text for text, _ in self.service.messages.queue))

    def test_intentional_close_during_pairing_does_not_save_a_cloud_error(self):
        def cancel(code):
            self.service.stop()
            raise InterruptedError("reMarkable sync stopped")

        self.service.remarkable.connect = Mock(side_effect=cancel)
        self.service.command("remarkable_connect", "abcdefgh")
        self.service.run()
        self.assertIsNone(self.store.preference("remarkable_error"))

    def test_processing_defaults_apply_only_to_new_projects(self):
        existing = self.store.add_project(self.root / "Existing")
        original = json.loads(self.store.project(existing)["settings"])
        self.service.command("defaults", {"gap": 48, "notebook_style": "Detailed", "ocr": True})
        self.service.command("defaults", {"context_padding": 64})
        self.run_preference_commands()
        saved = self.store.default_settings()
        self.assertEqual(saved, {**DEFAULT_SETTINGS, "gap": 48, "notebook_style": "Detailed", "ocr": True, "context_padding": 64})
        self.assertEqual(json.loads(self.store.project(existing)["settings"]), original)
        added = self.store.add_project(self.root / "New")
        self.assertEqual(json.loads(self.store.project(added)["settings"]), saved)
        self.assertEqual(self.store.add_project(self.root / "Existing"), existing)
        self.assertEqual(json.loads(self.store.project(existing)["settings"]), original)

    def test_viewer_preference_is_saved_by_the_worker(self):
        preference = {"viewer": "custom", "path": str(self.root / "Viewer.exe")}
        self.service.command("viewer", preference)
        self.run_preference_commands()
        self.assertEqual(self.store.preference("pdf_viewer"), preference)
        self.assertIn(("PDF viewer preference saved.", True), self.service.messages.queue)

    def test_verified_metadata_check_counts_only_pdfs_in_selected_source(self):
        source = folder("Literature")
        child = folder("Research", source.id)
        other = folder("Personal")
        root_pdf, _ = fixture(source.id)
        nested_pdf, _ = fixture(child.id)
        outside_pdf, _ = fixture(other.id)
        notebook = replace(root_pdf, id="notebook", files=[])
        trashed_pdf = replace(nested_pdf, id="deleted-pdf", deleted=True)
        engine = RemarkableSync(self.store, threading.Event(), Mock())
        engine.client = Mock()
        engine.client.library.return_value = [source, child, other, root_pdf, nested_pdf, outside_pdf, notebook, trashed_pdf]
        engine.sync(force=True, listing_only=True)
        check = self.store.preference("remarkable_last_check")
        self.assertEqual(check["source_folder_id"], source.id)
        self.assertEqual(check["source_pdf_count"], 2)
        self.assertTrue(check["at"])
        engine.client.pdf_bundle.assert_not_called()

    def test_pairing_records_verified_cloud_check_without_downloading_pdfs(self):
        source = folder("Literature")
        client = Mock()
        client.pair.return_value = "synthetic-token"
        client.library.return_value = [source]
        engine = RemarkableSync(self.store, threading.Event(), Mock(), client_factory=Mock(return_value=client))
        engine.vault = Mock()
        engine.connect("abcdefgh")
        engine.vault.save.assert_called_once_with("synthetic-token")
        self.assertEqual(self.store.preference("remarkable_last_check")["source_pdf_count"], 0)
        client.pdf_bundle.assert_not_called()

    def test_failed_metadata_check_does_not_overwrite_last_verified_check(self):
        old = {"at": "previous-success", "source_folder_id": "literature-id", "source_pdf_count": 3}
        self.store.set_preference("remarkable_last_check", old)
        engine = RemarkableSync(self.store, threading.Event(), Mock())
        engine.client = Mock()
        engine.client.library.side_effect = CloudError("Network unavailable")
        with self.assertRaises(CloudError):
            engine.sync(force=True, listing_only=True)
        self.assertEqual(self.store.preference("remarkable_last_check"), old)


if __name__ == "__main__":
    unittest.main()
