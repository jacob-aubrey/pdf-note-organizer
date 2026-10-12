"""Path controls share live hover help and a visible copy action, using disposable data."""
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from note_organizer.dialogs import PreferencesDialog
from note_organizer.workflow_ui import SortingFields
from tests import test_combined_workflow_ui, test_preferences_ui
from tests.test_path_visibility import long_path


class SettingsPathConsistencyTests(unittest.TestCase):
    setUp = test_preferences_ui.PreferencesUITests.setUp
    tearDown = test_preferences_ui.PreferencesUITests.tearDown

    def test_active_library_and_viewer_share_compact_path_controls(self):
        self.dialog.cancel()
        self.app.data_dir = Path(long_path(self.folder, "Active library"))
        self.dialog = PreferencesDialog(self.app)
        viewer = long_path(self.folder, "PDF viewer.exe")
        self.dialog.viewer_path.set(viewer)
        self.root.update()
        for entry, button, value, explanation in (
                (self.dialog.library_path_entry, self.dialog.library_path_copy,
                 str(self.app.data_dir.resolve()), "reads and writes this library"),
                (self.dialog.path_entry, self.dialog.viewer_path_copy, viewer, "Other application")):
            self.assertIsInstance(entry, ttk.Entry)
            self.assertIn(value, entry.tooltip.text())
            self.assertIn(explanation, entry.tooltip.text())
            self.assertFalse(hasattr(entry.path_access, "menu"))
            self.assertEqual(entry.bind("<Button-3>"), "")
            self.assertEqual(str(button.cget("compound")), "image")
            self.assertEqual(button.icon_name, "copy")
            self.assertIn("Copy full path", button.tooltip.text())
            self.assertIn("complete file or folder", button.tooltip.text())
            self.assertIn(value, button.tooltip.text())
            with patch.object(entry, "clipboard_clear"), patch.object(entry, "clipboard_append") as copied:
                button.invoke()
            copied.assert_called_once_with(value)
        self.assertFalse(self.errors)

    def test_sorting_folder_copy_actions_follow_current_unsaved_values(self):
        self.app.inbox = SimpleNamespace(config=lambda: {})
        parent = ttk.Frame(self.root)
        fields = SortingFields(self.app, parent)
        with patch.object(self.store, "set_preference") as saved:
            for name, variable in (("Incoming documents", fields.watch), ("Library root", fields.library)):
                entry, copy = fields.folder_entries[name], fields.folder_copy_buttons[name]
                variable.set(long_path(self.folder, "First " + name))
                latest = long_path(self.folder, "Latest " + name)
                variable.set(latest)
                self.root.update()
                self.assertIn(latest, entry.tooltip.text())
                self.assertIn(latest, copy.tooltip.text())
                with patch.object(entry, "clipboard_clear"), patch.object(entry, "clipboard_append") as copied:
                    copy.invoke()
                copied.assert_called_once_with(latest)
                self.assertFalse(hasattr(entry.path_access, "menu"))
            saved.assert_not_called()
        parent.destroy()
        self.assertFalse(self.errors)

    def test_saved_library_paths_have_an_unambiguous_selector_and_full_path_copy(self):
        result = {"active": {"name": "Current", "documents": 0, "notes": 0},
                  "alternatives": [{"name": "Saved library", "path": long_path(self.folder, f"Library {number}")}
                                   for number in range(2)]}
        done = Future()
        done.set_result(result)
        self.dialog.show_diagnostics(done)
        display = self.dialog.diagnostics_display
        self.assertEqual(len(display.paths), 2)
        for name, value in display.paths.items():
            display.path_selector.set(name)
            display.path_selector.event_generate("<<ComboboxSelected>>")
            self.root.update()
            path = value[0] if isinstance(value, tuple) else value
            self.assertIn(path, display.path_selector.tooltip.text())
            with patch.object(display.path_selector, "clipboard_clear"), patch.object(display.path_selector, "clipboard_append") as copied:
                display.path_selector.path_access.copy_button.invoke()
            copied.assert_called_once_with(path)
        self.assertFalse(self.errors)

    def test_escape_cancels_settings_drafts_without_saving(self):
        self.dialog.processing.group.set("Whole page")
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.dialog.window.attributes("-alpha", 0)
        self.dialog.window.deiconify()
        self.root.update()
        self.dialog.window.focus_force()
        self.root.update()
        with patch.object(self.store, "set_preference") as saved:
            self.dialog.window.event_generate("<Escape>")
            self.root.update()
            self.assertFalse(self.dialog.window.winfo_exists())
            saved.assert_not_called()
        self.assertFalse(self.errors)


class WorkflowPathConsistencyTests(unittest.TestCase):
    setUp = test_combined_workflow_ui.CombinedWorkflowUITests.setUp
    tearDown = test_combined_workflow_ui.CombinedWorkflowUITests.tearDown

    def test_inbox_original_and_destination_have_live_explained_copy_actions(self):
        view = self.app.inbox_view
        original, destination = long_path(self.folder), long_path(self.folder, "Literature")
        view.original.set(original)
        view.destination.set(destination)
        self.root.update()
        for widget, button, value, explanation in (
                (view.original_label, view.original_path_copy, original, "original document"),
                (view.destination_entry, view.destination_path_copy, destination, "destination inside your library root")):
            self.assertIn(value, widget.tooltip.text())
            self.assertIn(explanation, widget.tooltip.text())
            self.assertFalse(hasattr(widget.path_access, "menu"))
            with patch.object(widget, "clipboard_clear"), patch.object(widget, "clipboard_append") as copied:
                button.invoke()
            copied.assert_called_once_with(value)
        view.original.set("Select a document in the inbox.")
        self.root.update()
        with patch.object(view.original_label, "clipboard_append") as copied:
            view.original_path_copy.invoke()
        copied.assert_not_called()
        self.assertFalse(self.errors)

    def test_review_scope_and_copy_selector_follow_selection_without_opening_or_saving(self):
        with patch("note_organizer.workflow_ui.background"):
            review = self.app.review_library()
        scope = long_path(self.folder, "Scope")
        local_paths = [long_path(self.folder, "Copy 1.pdf"), long_path(self.folder, "Copy 2.pdf")]
        review.scope.set(scope)
        review.rows = {"finding": {"id": "finding", "kind": "local_duplicate", "title": "Paper", "reason": "Identical files",
                                    "local_paths": local_paths, "sources": [], "actions": []}}
        review.render()
        review.tree.selection_set("finding")
        review.selected()
        self.root.update()
        with patch.object(self.app, "open_path") as opened, patch.object(self.app.store, "set_preference") as saved:
            with patch.object(review.scope_entry, "clipboard_clear"), patch.object(review.scope_entry, "clipboard_append") as copied:
                review.scope_path_copy.invoke()
            copied.assert_called_once_with(scope)
            for path in local_paths:
                review.paths.set(path)
                self.root.update()
                self.assertIn(path, review.paths.tooltip.text())
                with patch.object(review.paths, "clipboard_clear"), patch.object(review.paths, "clipboard_append") as copied:
                    review.local_path_copy.invoke()
                copied.assert_called_once_with(path)
            opened.assert_not_called()
            saved.assert_not_called()
        review.close()
        self.assertFalse(self.errors)

    def test_inbox_metadata_remains_selectable_readonly_and_scrollable_when_narrowed(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("1000x650")
        self.root.deiconify()
        self.app.tabs.select(self.app.inbox_tab)
        view = self.app.inbox_view
        content = "\n".join(f"Line {number}: Research title and citation metadata with descriptive text" for number in range(100))
        view.set_details(content)
        self.root.update()
        self.assertEqual(view.details.get("1.0", "end-1c"), content)
        self.assertEqual(view.details.cget("state"), "disabled")
        self.assertTrue(view.details_display.scroll.winfo_ismapped())
        view.details.yview_moveto(1)
        self.root.update()
        self.assertGreater(view.details.yview()[0], 0)
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
