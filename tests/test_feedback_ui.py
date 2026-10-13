"""Isolated Tk checks for setup guidance, saved issue details, and small windows."""
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from note_organizer.remarkable_sync import default_config
from note_organizer.service import Service
from note_organizer.storage import Store
from note_organizer.ui import App
from tests.ui_helpers import settle_library


class FeedbackUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.data = self.folder / "Synthetic library"
        self.store = Store(self.data / "library.sqlite3")
        self.config = {**default_config(self.data), "integration_enabled": True, "source_folder_id": "literature-id"}
        self.store.set_preference("remarkable", self.config)
        self.store.set_preference("remarkable_folders", [
            {"id": "literature-id", "name": "Literature", "parent": "", "ancestor_ids": [], "path": "/Literature"}])
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes("-alpha", 0.0)
        self.callback_errors = []
        self.root.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.app = None

    def tearDown(self):
        if self.app:
            self.app.closing = True
            self.app.inbox.stop()
            self.app.workflow_executor.shutdown(wait=True, cancel_futures=True)
            self.app.service.stop()
            self.app.pdf_worker.shutdown(wait=True)
            self.app.query_cancel.set()
            self.app.preview_cancel.set()
            self.app.query_executor.shutdown(wait=True, cancel_futures=True)
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.temp.cleanup()

    def build_app(self, paired=False):
        if paired:
            token_path = self.data / "remarkable" / "device-token.dpapi"
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_bytes(b"Synthetic pairing placeholder")
        with patch.object(Service, "start"):
            self.app = App(self.root, self.store, self.data)
            settle_library(self.app, self.root)
        self.app.tabs.select(self.app.remarkable_tab)
        self.root.update()
        return self.app

    def assert_within_window(self, widget):
        self.assertTrue(widget.winfo_ismapped())
        self.assertGreater(widget.winfo_width(), 1)
        self.assertGreater(widget.winfo_height(), 1)
        left = widget.winfo_rootx() - self.root.winfo_rootx()
        top = widget.winfo_rooty() - self.root.winfo_rooty()
        self.assertGreaterEqual(left, 0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(left + widget.winfo_width(), self.root.winfo_width())
        self.assertLessEqual(top + widget.winfo_height(), self.root.winfo_height())

    def test_unpaired_blank_destination_guides_to_primary_connect(self):
        app = self.build_app()
        self.assertIn("Not paired", app.cloud_status.get())
        self.assertEqual(app.cloud_connect_button.winfo_manager(), "place")
        self.assertEqual(app.cloud_connect_button.cget("style"), "Primary.TButton")
        self.assertFalse(app.cloud_connect_button.instate(["disabled"]))
        self.assertFalse(app.cloud_sync_button.winfo_manager())
        self.assertTrue(app.cloud_setup_expanded)

    def test_paired_blank_destination_reports_setup_incomplete(self):
        app = self.build_app(paired=True)
        self.assertIn("Setup incomplete", app.cloud_status.get())
        self.assertIn("choose your PC destination", app.cloud_status.get())
        self.assertTrue(app.cloud_sync_button.instate(["disabled"]))
        self.assertTrue(app.cloud_setup_expanded)
        self.assertIn("destination", app.cloud_sync_button.tooltip.text())

    def test_paired_valid_destination_exposes_primary_sync(self):
        destination = self.folder / "Sorted"
        destination.mkdir()
        self.config["pc_root"] = str(destination)
        self.store.set_preference("remarkable", self.config)
        app = self.build_app(paired=True)
        self.assertEqual(app.cloud_sync_button.winfo_manager(), "place")
        self.assertEqual(app.cloud_sync_button.cget("style"), "Primary.TButton")
        self.assertFalse(app.cloud_sync_button.instate(["disabled"]))
        self.assertFalse(app.cloud_connect_button.winfo_manager())
        self.assertFalse(app.cloud_setup_expanded)

    def test_show_details_includes_saved_cloud_error_without_a_new_log(self):
        error = "Authorization expired for the synthetic account."
        self.store.set_preference("remarkable_error", error)
        app = self.build_app(paired=True)
        self.assertEqual(app.details_button.winfo_manager(), "pack")
        app.show_sync_details()
        self.assertEqual(app.tabs.select(), str(app.library_tab))
        self.assertTrue(app.activity_frame.winfo_manager())
        self.assertIn(error, app.activity.get("1.0", "end"))
        app.show_sync_details()
        self.assertEqual(app.activity.get("1.0", "end").count(error), 1)

    def test_missing_review_download_disables_open_with_explanatory_tooltip(self):
        self.store.save_remarkable_item("review-id", {
            "state": "review", "name": "Retained article", "cloud_path": "/Literature/Retained article",
            "parent": "literature-id", "review_pdf": str(self.folder / "missing-review.pdf"),
            "reason": "This cloud copy needs a matching PC folder."})
        app = self.build_app(paired=True)
        app.cloud_review.selection_set("review-id")
        app.cloud_review_selected()
        self.assertTrue(app.cloud_open_button.instate(["disabled"]))
        self.assertIn("available download", app.cloud_open_button.tooltip.text())

    def test_narrow_expanded_setup_keeps_edit_and_connect_controls_visible(self):
        app = self.build_app()
        self.root.geometry("940x620+0+0")
        self.root.deiconify()
        self.root.update()
        self.assertTrue(app.cloud_setup_expanded)
        for widget in (app.cloud_connect_button, app.cloud_scope, app.cloud_pc_entry, app.cloud_apply_button):
            with self.subTest(widget=str(widget)):
                self.assert_within_window(widget)
        self.assertGreater(app.cloud_folders.winfo_height(), 40)
        self.assertGreater(app.cloud_review.winfo_height(), 40)
        self.assertFalse(self.callback_errors)

    def test_narrow_ready_view_keeps_mapping_and_review_tables_readable(self):
        destination = self.folder / "Sorted"
        destination.mkdir()
        self.config["pc_root"] = str(destination)
        self.store.set_preference("remarkable", self.config)
        app = self.build_app(paired=True)
        self.root.geometry("940x620+0+0")
        self.root.deiconify()
        self.root.update()
        self.assertFalse(app.cloud_setup_expanded)
        for widget in (app.cloud_sync_button, app.cloud_folders, app.cloud_review):
            with self.subTest(widget=str(widget)):
                self.assert_within_window(widget)
        self.assertGreaterEqual(app.cloud_folders.winfo_height(), 80)
        self.assertGreaterEqual(app.cloud_review.winfo_height(), 80)
        self.assertFalse(self.callback_errors)


if __name__ == "__main__":
    unittest.main()
