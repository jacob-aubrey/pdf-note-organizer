"""Path controls share full-value hover and copy, using disposable libraries."""
import tkinter as tk
import unittest
from unittest.mock import patch

from tests import test_ui_audit
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class PathUIConsistencyTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp

    def tearDown(self):
        self.app.preview_cancel.set()
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        test_ui_audit.UIAuditTests.tearDown(self)

    def library_paper(self):
        path = self.pc / ("Research papers and annotated notes " * 4) / "A very long paper title.pdf"
        project = self.store.add_project(self.pc)
        self.store.save_scan(project, path, "synthetic-digest", "synthetic-signature", "{}", {},
                             [{"key": "note", "kind": "highlight", "page": 2, "quote": "Synthetic passage"}])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.root.update()
        return self.app.view.documents()[0]["path"], str(project)

    def assert_copy(self, access, button, path):
        self.assertEqual(access.value(), path)
        self.assertIn(path, access.widget.tooltip.text())
        self.assertIn(path, button.tooltip.text())
        with patch.object(access.widget, "clipboard_clear") as cleared, patch.object(access.widget, "clipboard_append") as copied:
            button.invoke()
        cleared.assert_called_once()
        copied.assert_called_once_with(path)

    def test_cloud_controls_copy_paths_without_display_ids_or_placeholders(self):
        app = self.app
        self.assert_copy(app.cloud_scope_path_access, app.cloud_scope_copy, "/Literature")
        self.assert_copy(app.cloud_pc_path_access, app.cloud_pc_copy, str(self.pc))
        app.cloud_scope.current(0)
        app.cloud_scope_path_access.refresh()
        self.assertTrue(app.cloud_scope_copy.instate(["disabled"]))
        self.assertNotIn("Find Literature automatically", app.cloud_scope.tooltip.text())
        app.cloud_pc_root.set(str(self.pc / "Different root"))
        self.assertIn("Different root", app.cloud_pc_copy.tooltip.text())

    def test_notes_selectors_use_complete_pc_paths_instead_of_short_labels(self):
        path, project = self.library_paper()
        app = self.app
        app.projects.selection_set(project)
        app.project_selected()
        document = app.papers.get_children()[0]
        app.papers.selection_set(document)
        app.paper_selected()
        folder_path = app.view.project(int(project))["root"]
        self.assertEqual(app.reader_folder.get(), self.pc.name.lower())
        self.assert_copy(app.reader_folder_path_access, app.reader_folder_copy, folder_path)
        self.assert_copy(app.reader_paper_path_access, app.reader_paper_copy, path)
        self.assertNotEqual(app.reader_paper.get(), path)
        app.reader_folder.current(0)
        app.reader_folder_selected()
        self.assertTrue(app.reader_folder_copy.instate(["disabled"]))

    def test_all_papers_copies_selected_note_source_and_explains_that_choice(self):
        app = self.app
        path = str(self.pc / "Some long folder" / "Selected note paper.pdf")
        app.entries = [{"document_id": "doc", "key": "note", "path": path,
                        "kind": "highlight", "page": 2, "quote": "Passage"}]
        app.notes.insert("", "end", iid="0", values=(2, "highlight", "Passage"))
        app.notes.selection_set("0")
        app.reader_paper.current(0)
        app.preview()
        self.assert_copy(app.reader_paper_path_access, app.reader_paper_copy, path)
        self.assertIn("selected note's source PDF", app.reader_paper.tooltip.text())
        self.assertIn(path, app.source_button.tooltip.text())

    def test_table_hover_and_details_contain_actual_paths_and_explanations(self):
        path, project = self.library_paper()
        app = self.app
        app.projects.selection_set(project)
        app.project_selected()
        document = app.papers.get_children()[0]
        app.papers.selection_set(document)
        app.paper_selected()
        folder_path = app.view.project(int(project))["root"]
        self.assertEqual(app.projects.tooltip.value(project, "name"), folder_path)
        self.assertEqual(app.papers.tooltip.value(document, "name"), path)
        self.assertIn("copy", app.projects.tooltip.extra(project, "name"))
        self.assertEqual(app.folder_details.selected_path(), folder_path)
        self.assertEqual(app.paper_details.selected_path(), path)
        self.assert_copy(app.paper_details.path_access, app.paper_details.path_copy_button, path)

    def test_mapping_and_review_details_copy_only_real_available_locations(self):
        app = self.app
        app.cloud_folders.selection_set("missing")
        app.cloud_selection_changed()
        self.assertEqual(app.mapping_details.paths, {"Tablet folder": ("/Literature/Missing", "Tablet folder")})
        retained = str(self.pc / "Review" / "retained.pdf")
        destination = str(self.pc / "Missing" / "paper.pdf")
        app.view.cloud_items = {"pdf": {"name": "paper", "cloud_path": "/Literature/Missing/paper",
            "target": destination, "review_pdf": retained, "reason": "Needs mapping", "state": "review"}}
        app.cloud_review.insert("", "end", iid="pdf", values=("paper", "/Literature/Missing/paper", "Needs mapping"))
        app.cloud_review.selection_set("pdf")
        app.cloud_review_selected()
        app.review_details.path_selector.set("Retained PDF")
        app.review_details.path_access.refresh()
        self.assert_copy(app.review_details.path_access, app.review_details.path_copy_button, retained)
        self.assertEqual(app.review_details.paths["PC destination"][0], destination)

    def test_activity_locations_keep_concrete_paths_copyable(self):
        app = self.app
        recovery = str(self.pc / "New paper.pdf.preserved")
        failed = str(self.pc / "Could not read.pdf")
        app.view.preferences["sync_summary"] = {"details": [{"path": failed, "message": "Could not read"}]}
        app.view.cloud_items = {"saved": {"recovery_paths": [recovery]}}
        app.refresh_activity_paths()
        app.activity_locations.set("Retained recovery copy · 2")
        app.activity_path_access.refresh()
        self.assert_copy(app.activity_path_access, app.activity_path_copy, recovery)
        self.assertEqual(set(app.activity_location_paths.values()), {failed, recovery})

    def test_path_buttons_fit_main_panels_at_normal_and_larger_scale(self):
        original_scale = self.root.tk.call("tk", "scaling")
        try:
            for scale in (1.333333333, 2.0):
                self.root.tk.call("tk", "scaling", scale)
                self.root.geometry("1000x700")
                self.root.attributes("-alpha", 0)
                self.root.deiconify()
                for tab in (self.app.notes_tab, self.app.remarkable_tab):
                    self.app.tabs.select(tab)
                    if tab is self.app.remarkable_tab and not self.app.cloud_setup_expanded:
                        self.app.toggle_cloud_setup()
                    self.root.update()
                    pairs = ((self.app.reader_folder, self.app.reader_folder_copy), (self.app.reader_paper, self.app.reader_paper_copy)) if tab is self.app.notes_tab else ((self.app.cloud_scope, self.app.cloud_scope_copy), (self.app.cloud_pc_entry, self.app.cloud_pc_copy))
                    for field, button in pairs:
                        self.assertGreater(field.winfo_width(), 15)
                        self.assertGreater(button.winfo_width(), 15)
                        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), self.root.winfo_rootx() + self.root.winfo_width())
                self.assertFalse(self.errors)
        finally:
            self.root.tk.call("tk", "scaling", original_scale)

    def test_help_is_scrollable_copyable_and_escape_closes_it(self):
        app = self.app
        window = app.help()
        window.attributes("-alpha", 0)
        window.deiconify()
        self.root.update()
        self.assertGreater(len(window.help_text.value), 2500)
        self.assertTrue(window.help_text.text.cget("yscrollcommand"))
        field = next(widget for widget in descendants(window) if hasattr(widget, "path_access"))
        self.assert_copy(field.path_access, field.path_access.copy_button, str(app.data_dir.resolve()))
        window.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(window.winfo_exists())
        self.assertFalse(self.errors)

    def test_history_scrolls_and_escape_closes_without_waiting_for_loading(self):
        path = str(self.pc / "history source.pdf")
        app = self.app
        with patch.object(app, "selected_entry", return_value={"document_id": "synthetic", "path": path}):
            window = app.history()
        window.attributes("-alpha", 0)
        window.deiconify()
        self.root.update()
        self.assertTrue(window.history_text.text.cget("yscrollcommand"))
        field = next(widget for widget in descendants(window) if hasattr(widget, "path_access"))
        self.assert_copy(field.path_access, field.path_access.copy_button, path)
        window.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(window.winfo_exists())
        self.assertFalse(self.errors)

    def test_escape_discards_search_pairing_and_folder_settings_without_commands(self):
        self.library_paper()
        app = self.app
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.root.update()
        with patch.object(app.service, "command") as command:
            for open_dialog in (app.search_options, app.pair_remarkable, app.settings):
                before = set(self.root.winfo_children())
                open_dialog()
                window = next(widget for widget in self.root.winfo_children()
                              if isinstance(widget, tk.Toplevel) and widget not in before)
                window.attributes("-alpha", 0)
                window.deiconify()
                self.root.update()
                window.event_generate("<Escape>")
                self.root.update()
                self.assertFalse(window.winfo_exists())
            command.assert_not_called()
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
