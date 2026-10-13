"""Complete paths stay readable; all files and libraries in these tests are disposable."""
from concurrent.futures import Future
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from note_organizer.dialogs import PreferencesDialog
from note_organizer.widgets import PathField, ReadOnlyText
from note_organizer.workflow_ui import SortingFields
from tests import test_combined_workflow_ui, test_preferences_ui


def long_path(base, ending="paper.pdf"):
    return str(Path(base).joinpath(*[f"Research folder with a long descriptive name {number}" for number in range(22)], ending))


class SettingsPathVisibilityTests(unittest.TestCase):
    setUp = test_preferences_ui.PreferencesUITests.setUp
    tearDown = test_preferences_ui.PreferencesUITests.tearDown

    def library_tab(self):
        self.dialog.window.attributes("-alpha", 0)
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        tabs = next(widget for widget in test_preferences_ui.descendants(self.dialog.window)
                    if isinstance(widget, ttk.Notebook))
        tabs.select(1)
        self.dialog.window.deiconify()
        self.root.update()

    def test_active_library_is_compact_with_live_full_path_help_and_copy_without_saving(self):
        self.dialog.cancel()
        self.app.data_dir = Path(long_path(self.data, "app library"))
        self.dialog = PreferencesDialog(self.app)
        self.library_tab()
        display = self.dialog.library_path_entry
        expected = str(self.app.data_dir.resolve())
        self.assertEqual(display.get(), expected)
        self.assertEqual(str(display.cget("state")), "readonly")
        self.assertIn(expected, display.tooltip.text())
        self.assertIn("preserves its separate notes and settings", display.tooltip.text())
        self.assertFalse(hasattr(display.path_access, "menu"))
        with patch.object(self.service, "save_preferences") as saved, patch.object(self.store, "set_preference") as written:
            with patch.object(self.dialog.window, "clipboard_clear") as clear, patch.object(self.dialog.window, "clipboard_append") as copied:
                self.dialog.copy_path()
            clear.assert_called_once()
            copied.assert_called_once_with(expected)
            with patch.object(display, "clipboard_clear"), patch.object(display, "clipboard_append") as copied:
                self.dialog.library_path_copy.invoke()
            copied.assert_called_once_with(expected)
            saved.assert_not_called()
            written.assert_not_called()
        self.assertFalse(self.errors)

    def test_many_library_diagnostics_scroll_and_copy_while_save_stays_visible(self):
        result = {"active": {"name": "Current", "documents": 4, "notes": 8},
                  "alternatives": [{"name": f"Library {number}", "path": long_path(self.folder, f"Library {number}"),
                                    "documents": number, "notes": number * 2} for number in range(35)]}
        completed = Future()
        completed.set_result(result)
        with patch.object(self.store, "set_preference") as written, patch.object(self.service, "save_preferences") as saved:
            self.dialog.show_diagnostics(completed)
            self.library_tab()
            display = self.dialog.diagnostics_display
            text = display.text.get("1.0", "end-1c")
            for alternate in result["alternatives"]:
                self.assertIn(alternate["path"], text)
            self.assertLess(display.text.yview()[1], 1)
            display.text.yview_moveto(1)
            self.root.update()
            self.assertGreater(display.text.yview()[0], 0)
            with patch.object(display, "clipboard_clear"), patch.object(display, "clipboard_append") as copied:
                display.copy_button.invoke()
            copied.assert_called_once_with(text)
            saved.assert_not_called()
            written.assert_not_called()
        button, window = self.dialog.save_button, self.dialog.window
        self.assertGreater(button.winfo_width(), 1)
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), window.winfo_rooty() + window.winfo_height() + 2)
        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), window.winfo_rootx() + window.winfo_width() + 2)
        self.assertFalse(self.errors)

    def test_sorting_path_help_and_copy_follow_draft_edits_without_exposing_gemini_key(self):
        from types import SimpleNamespace
        self.app.inbox = SimpleNamespace(config=lambda: {"watch_folder": long_path(self.folder, "Inbox"),
                                                         "library_root": long_path(self.folder, "Literature")})
        parent = ttk.Frame(self.root)
        fields = SortingFields(self.app, parent)
        fields.api_key.set("synthetic-secret-key-for-visibility-test")
        with patch.object(self.store, "set_preference") as written, patch.object(self.service, "save_preferences") as saved:
            for name, entry in fields.folder_entries.items():
                self.assertIn(entry.get(), entry.tooltip.text())
                changed = long_path(self.folder, "Changed " + name)
                variable = fields.watch if name == "Incoming documents" else fields.library
                variable.set(changed)
                self.assertIn(changed, entry.tooltip.text())
                self.assertNotIn(fields.api_key.get(), entry.tooltip.text())
                with patch.object(entry, "clipboard_clear"), patch.object(entry, "clipboard_append") as copied:
                    fields.folder_copy_buttons[name].invoke()
                copied.assert_called_once_with(changed)
            self.assertFalse(hasattr(fields.key_entry, "path_access"))
            self.assertEqual(fields.key_entry.cget("show"), "•")
            saved.assert_not_called()
            written.assert_not_called()
        parent.destroy()
        self.assertFalse(self.errors)

    def test_path_field_entry_and_readonly_combo_copy_live_value_and_select_all_with_keyboard(self):
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        entry = ttk.Entry(self.root)
        entry.pack()
        combo = ttk.Combobox(self.root, state="readonly")
        combo.pack()
        for widget in (entry, combo):
            helper = PathField(widget, "Choose a folder.")
            copy_button = helper.add_copy_button(self.root)
            original, changed = long_path(self.folder), long_path(self.folder, "edited path.pdf")
            if widget is entry:
                widget.insert(0, original)
                widget.delete(0, "end")
                widget.insert(0, changed)
            else:
                widget.set(original)
                widget.set(changed)
            helper.refresh()
            self.assertIn(changed, widget.tooltip.text())
            with patch.object(widget, "clipboard_clear"), patch.object(widget, "clipboard_append") as copied:
                copy_button.invoke()
            copied.assert_called_once_with(changed)
            widget.focus_force()
            self.root.update()
            widget.event_generate("<Control-a>")
            self.root.update()
            self.assertEqual(widget.index("sel.first"), 0)
            self.assertEqual(widget.index("sel.last"), len(changed))
        self.assertFalse(self.errors)

    def test_path_help_combines_current_location_and_explanation_without_context_menu(self):
        entry = ttk.Entry(self.root)
        path = long_path(self.folder)
        entry.insert(0, path)
        helper = PathField(entry, "Choose a file.")
        text = entry.tooltip.text()
        self.assertIn(path, text)
        self.assertIn("Choose a file.", text)
        self.assertNotIn("Right-click", text)
        self.assertFalse(hasattr(helper, "menu"))
        self.assertEqual(entry.bind("<Button-3>"), "")

    def test_capped_settings_keep_save_visible_and_library_paths_scrollable(self):
        self.library_tab()
        self.dialog.diagnostics.set("Saved library locations:\n" + "\n".join(long_path(self.folder, f"Library {number}") for number in range(20)))
        with patch("note_organizer.widgets.work_area", return_value=(0, 0, 700, 500)):
            from note_organizer.widgets import fit_dialog
            fit_dialog(self.dialog.window, self.root)
        self.root.update()
        window, button = self.dialog.window, self.dialog.save_button
        self.assertLessEqual(window.winfo_height(), 484)
        self.assertTrue(button.winfo_ismapped())
        self.assertGreater(button.winfo_width(), 1)
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), window.winfo_rooty() + window.winfo_height() + 2)
        display = self.dialog.diagnostics_display
        self.assertTrue(display.text.winfo_ismapped())
        self.assertGreater(display.text.winfo_height(), 20)
        self.assertLess(display.text.yview()[1], 1)
        self.assertFalse(self.errors)

    def test_readonly_text_tracks_value_changes_and_detaches_when_destroyed(self):
        value = tk.StringVar(self.root, value=long_path(self.folder))
        display = ReadOnlyText(self.root, textvariable=value)
        changed = long_path(self.folder, "Changed library")
        value.set(changed)
        self.assertEqual(display.text.get("1.0", "end-1c"), changed)
        with patch.object(display, "clipboard_clear"), patch.object(display, "clipboard_append") as copied:
            display.copy()
        copied.assert_called_once_with(changed)
        display.destroy()
        value.set("Changed after the display was closed")
        self.root.update()
        self.assertFalse(self.errors)


class WorkflowPathVisibilityTests(unittest.TestCase):
    setUp = test_combined_workflow_ui.CombinedWorkflowUITests.setUp
    tearDown = test_combined_workflow_ui.CombinedWorkflowUITests.tearDown

    def test_review_paths_and_copy_all_details_follow_current_selection(self):
        with patch("note_organizer.workflow_ui.background"):
            review = self.app.review_library()
        review.window.attributes("-alpha", 0)
        review.window.withdraw()
        paths = [long_path(self.folder, "First copy.pdf"), long_path(self.folder, "Second copy.pdf")]
        review.rows = {str(number): {"id": str(number), "kind": "local_duplicate", "title": f"Paper {number}",
                                    "reason": f"Explanation {number}", "local_paths": [path],
                                    "sources": [], "actions": []} for number, path in enumerate(paths)}
        review.render()
        with patch.object(self.app, "open_path") as opened, patch.object(self.app.service, "command") as command:
            for number, path in enumerate(paths):
                review.tree.selection_set(str(number))
                review.selected()
                self.assertEqual(review.paths.get(), path)
                self.assertIn(path, review.paths.tooltip.text())
                with patch.object(review.paths, "clipboard_clear"), patch.object(review.paths, "clipboard_append") as copied:
                    review.local_path_copy.invoke()
                copied.assert_called_once_with(path)
                expected = review.details.get("1.0", "end-1c")
                self.assertIn(path, expected)
                self.assertIn(f"Explanation {number}", expected)
                with patch.object(review.details_display, "clipboard_clear"), patch.object(review.details_display, "clipboard_append") as copied:
                    review.details_display.copy()
                copied.assert_called_once_with(expected)
            opened.assert_not_called()
            command.assert_not_called()
        review.close()
        self.assertFalse(self.errors)

    def test_narrowed_inbox_source_stays_compact_with_full_path_help_and_copy(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("1100x740")
        self.root.deiconify()
        self.app.tabs.select(self.app.inbox_tab)
        source = self.app.inbox_view.original_label
        path = str(self.folder / "Research" / "A longer research paper filename with extra details.pdf")
        self.app.inbox_view.original.set(path)
        self.root.update()
        pane = source.master
        while pane is not None and not isinstance(pane, ttk.Panedwindow):
            pane = pane.master
        self.assertIsInstance(pane, ttk.Panedwindow)
        pane.sashpos(0, pane.winfo_width() - 280)
        self.root.update()
        self.assertIn(str(source.cget("wraplength")), ("", "0"))
        self.assertLess(source.winfo_width(), 440)
        self.assertLess(source.winfo_height(), 50)
        self.assertIn(path, source.tooltip.text())
        with patch.object(source, "clipboard_clear"), patch.object(source, "clipboard_append") as copied:
            self.app.inbox_view.original_path_copy.invoke()
        copied.assert_called_once_with(path)
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
