"""Interface regressions use temporary libraries and never start cloud tracking."""
from concurrent.futures import Future
import os
from tkinter import ttk
import unittest
from unittest.mock import patch

from tests import test_ui_audit
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class InterfaceDesignTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = test_ui_audit.UIAuditTests.tearDown

    def pair_without_network(self):
        path = self.app.service.remarkable.vault.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        self.app.refresh()
        settle_library(self.app, self.root)

    def test_pending_routing_survives_refresh_and_acknowledgement_collapses_setup(self):
        app = self.app
        self.pair_without_network()
        app.toggle_cloud_setup()
        alternate = self.folder / "Alternate"
        alternate.mkdir()
        app.cloud_pc_root.set(str(alternate))
        self.assertEqual(app.cloud_apply_status.get(), "Unsaved changes")
        self.assertEqual(app.cloud_sync_button.cget("text"), "Apply & sync PDFs")
        app.save_cloud_routing()
        self.assertEqual(app.cloud_apply_status.get(), "Applying…")
        self.assertTrue(app.cloud_apply_button.instate(["disabled"]))
        app.refresh_cloud()
        self.assertEqual(app.cloud_pc_root.get(), str(alternate.resolve()))
        self.assertEqual(app.cloud_apply_status.get(), "Applying…")
        self.store.set_preference("remarkable", {**self.config, "pc_root": str(alternate.resolve())})
        app.refresh()
        settle_library(app, self.root)
        self.assertEqual(app.cloud_apply_status.get(), "Saved")
        self.assertFalse(app.cloud_setup_expanded)
        self.assertEqual(app.cloud_sync_button.cget("text"), "Sync PDFs")
        self.assertIsNone(app.cloud_routing_pending)

    def test_relative_pc_path_is_normalized_before_worker_acknowledgement(self):
        alternate = self.folder / "Alternate"
        alternate.mkdir()
        self.app.cloud_pc_root.set(os.path.relpath(alternate))
        self.app.save_cloud_routing()
        self.assertEqual(self.app.cloud_pc_root.get(), str(alternate.resolve()))
        self.store.set_preference("remarkable", {**self.config, "pc_root": str(alternate.resolve())})
        self.app.refresh()
        settle_library(self.app, self.root)
        self.assertEqual(self.app.cloud_apply_status.get(), "Saved")
        self.assertTrue(self.app.cloud_apply_button.instate(["disabled"]))

    def test_acknowledging_prior_routing_does_not_hide_newer_edits(self):
        app = self.app
        app.toggle_cloud_setup()
        first, second = self.folder / "First", self.folder / "Second"
        first.mkdir()
        second.mkdir()
        app.cloud_pc_root.set(str(first))
        app.save_cloud_routing()
        app.cloud_pc_root.set(str(second))
        self.store.set_preference("remarkable", {**self.config, "pc_root": str(first.resolve())})
        app.refresh()
        settle_library(app, self.root)
        self.assertEqual(app.cloud_pc_root.get(), str(second.resolve()))
        self.assertEqual(app.cloud_apply_status.get(), "Unsaved changes")
        self.assertTrue(app.cloud_setup_expanded)

    def test_reader_uses_physical_page_for_table_preview_and_source_navigation(self):
        app = self.app
        path = self.pc / "article.pdf"
        path.touch()
        app.query_cancel.set()
        app.query_generation += 1
        future = Future()
        future.set_result([{"document_id": "doc", "key": "mark", "path": str(path),
                            "kind": "highlight", "quote": "A highlighted passage", "page": 1,
                            "page_count": 12, "label": "233", "pdf_label": "233"}])
        app.finish_query(app.query_generation, None, future)
        self.assertTrue(app.notes.heading("page", "text").startswith("Page"))
        self.assertEqual(app.notes.set("0", "page"), "1")
        self.assertNotIn("PDF page 1 of 12", app.preview_text.get("1.0", "end"))
        details = app.reader_document_details()
        try:
            from note_organizer.widgets import ReadOnlyText
            details_text = next(w for w in details.winfo_children()[0].winfo_children() if isinstance(w, ReadOnlyText))
            self.assertIn("PDF page 1 of 12 · PDF label 233", details_text.text.get("1.0", "end"))
        finally:
            details.destroy()
        self.assertFalse(app.show_details.get())
        with patch.object(app, "open_pdf") as open_pdf:
            app.open_source()
        open_pdf.assert_called_once_with(str(path), 1)

    def test_pdf_action_feedback_stays_on_its_tab_and_keeps_background_status(self):
        app = self.app
        app.tabs.select(app.notes_tab)
        self.root.update()
        app.status.set("Checking watched PDFs…")
        with patch("note_organizer.ui.open_pdf_page", return_value=("Opened at PDF page 3", True)):
            app.launch_pdf(self.pc / "article.pdf", 3, "notes")
        self.assertEqual(app.action_feedback["notes"].get(), "Opened at PDF page 3")
        self.assertEqual(app.status.get(), "Checking watched PDFs…")
        self.assertEqual(app.feedback_labels["notes"].winfo_manager(), "pack")
        app.tabs.select(app.remarkable_tab)
        self.root.update()
        self.assertEqual(app.action_feedback["notes"].get(), "")
        self.assertFalse(app.feedback_labels["notes"].winfo_manager())
        self.assertEqual(app.action_feedback["cloud"].get(), "")

    def test_search_uses_available_row_width_in_a_wide_window(self):
        self.app.tabs.select(self.app.notes_tab)
        self.root.geometry("1600x820")
        self.root.deiconify()
        self.root.update()
        self.assertGreater(self.app.search_entry.winfo_width(), self.app.notes_tab.winfo_width() * .65)
        self.assertLessEqual(abs(self.app.reader_folder.winfo_width() - self.app.reader_paper.winfo_width()), 1)
        self.assertLessEqual(abs(self.app.reader_folder.winfo_width() - self.app.label_picker.winfo_width()), 1)
        self.assertEqual(len(self.app.tabs.tabs()), 4)
        self.root.withdraw()

    def test_every_main_button_and_input_has_contextual_help(self):
        controls = [w for w in descendants(self.root)
                    if isinstance(w, (ttk.Button, ttk.Checkbutton, ttk.Combobox, ttk.Entry, ttk.Spinbox))]
        self.assertGreater(len(controls), 25)
        for widget in controls:
            with self.subTest(control=str(widget)):
                self.assertTrue(hasattr(widget, "tooltip"))
                text = widget.tooltip.text
                self.assertTrue(text() if callable(text) else text)
        self.assertIn("Connect", self.app.cloud_auto.tooltip.text())
        self.assertIn("drawing", self.app.enlarge_button.tooltip.text())

    def test_closed_preferences_dialog_ignores_late_diagnostics_result(self):
        app = self.app
        pending = Future()
        with patch.object(app.query_executor, "submit", return_value=pending):
            app.global_settings()
        window = app.preferences_window
        window.destroy()
        pending.set_result({"active": {"name": "Test", "documents": 0, "notes": 0}, "alternatives": []})
        app.poll()
        self.assertFalse(self.errors)
        self.assertTrue(app.dialog_results.empty())


if __name__ == "__main__":
    unittest.main()
