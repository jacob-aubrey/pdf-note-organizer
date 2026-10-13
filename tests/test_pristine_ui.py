"""Whole-interface layout contracts, using isolated offline libraries."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import font, ttk
import unittest
from unittest.mock import patch

from PIL import Image
from note_organizer.branding import apply_app_icon
from note_organizer.dialogs import PreferencesDialog
from note_organizer.icons import Button
from note_organizer.research_ui import SupplementsWindow
from note_organizer.service import Service
from note_organizer.storage import Store
from note_organizer.theme import apply_theme, PANEL, SURFACE, TEXT, MUTED, FOCUS
from note_organizer.ui import App
from note_organizer.widgets import DataTable, ScrollFrame
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class PristineInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.attributes("-alpha", 0)
        self.original_scaling = self.root.tk.call("tk", "scaling")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.store = Store(Path(self.temp.name) / "data/library.sqlite3")
        self.store.set_preference("remarkable", {"integration_enabled": True})
        with patch.object(Service, "start"):
            self.app = App(self.root, self.store, self.store.path.parent)
            settle_library(self.app, self.root)

    def tearDown(self):
        self.app.closing = True
        self.app.inbox.stop()
        self.app.service.stop()
        self.app.query_cancel.set()
        self.app.preview_cancel.set()
        self.app.workflow_executor.shutdown(wait=True, cancel_futures=True)
        self.app.query_executor.shutdown(wait=True, cancel_futures=True)
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        self.app.pdf_worker.shutdown(wait=True)
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.tk.call("tk", "scaling", self.original_scaling)
        self.root.destroy()
        self.temp.cleanup()
        self.assertFalse(self.errors)

    def assert_inside(self, widget, parent):
        x = widget.winfo_rootx() - parent.winfo_rootx()
        y = widget.winfo_rooty() - parent.winfo_rooty()
        label = str(widget.cget("text")) if "text" in widget.keys() else str(widget)
        self.assertGreaterEqual(x, -2, label)
        self.assertGreaterEqual(y, -2, label)
        self.assertLessEqual(x + widget.winfo_width(), parent.winfo_width() + 2, label)
        self.assertLessEqual(y + widget.winfo_height(), parent.winfo_height() + 2, label)

    def test_main_controls_fit_each_workspace_at_minimum_and_desktop_sizes(self):
        self.root.deiconify()
        for size in ("940x620", "1250x820", "1600x900"):
            self.root.geometry(size)
            for tab in (self.app.inbox_tab, self.app.library_tab, self.app.notes_tab, self.app.remarkable_tab):
                self.app.tabs.select(tab)
                self.root.update()
                for control in descendants(tab):
                    if isinstance(control, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton)) and control.winfo_ismapped():
                        with self.subTest(size=size, tab=str(tab), control=str(control)):
                            self.assert_inside(control, control.master)
                            ancestor = control.master
                            while ancestor is not tab and not isinstance(ancestor, ScrollFrame):
                                ancestor = ancestor.master
                            if ancestor is tab:
                                self.assert_inside(control, tab)
                            if isinstance(control, ttk.Button):
                                self.assertGreaterEqual(control.winfo_width(), control.winfo_reqwidth() - 2)
                            self.assertGreaterEqual(control.winfo_height(), control.winfo_reqheight() - 2)

    def test_settings_forms_scroll_at_short_height_and_keep_actions_visible(self):
        dialog = PreferencesDialog(self.app)
        dialog.window.attributes("-alpha", 0)
        dialog.window.geometry("700x430")
        self.root.deiconify()
        self.root.update()
        for form in dialog.form_pages:
            dialog.tabs.select(form)
            self.root.update()
            form.canvas.yview_moveto(1)
            self.root.update()
            self.assert_inside(dialog.save_button, dialog.window)
            if form.content.winfo_height() > form.canvas.winfo_height():
                self.assertGreater(form.canvas.yview()[0], 0)
                self.assertAlmostEqual(form.canvas.yview()[1], 1, places=2)
        cancel = next(w for w in descendants(dialog.window) if isinstance(w, Button) and w.cget("text") == "Cancel")
        self.assertLess(cancel.winfo_rootx(), dialog.save_button.winfo_rootx())
        dialog.cancel()

    def test_tab_focus_reveals_controls_below_the_settings_viewport(self):
        dialog = PreferencesDialog(self.app)
        dialog.window.attributes("-alpha", 0)
        dialog.window.geometry("700x430")
        dialog.tabs.select(dialog.sorting_tab)
        self.root.deiconify()
        self.root.update()
        field = dialog.sorting.slides_ai_check
        field.event_generate("<FocusIn>")
        self.root.update()
        self.assert_inside(field, dialog.sorting_canvas)
        dialog.cancel()

    def test_folder_processing_example_explanation_and_actions_do_not_overlap(self):
        folder = Path(self.temp.name) / "Papers"
        folder.mkdir()
        self.store.add_project(folder)
        self.app.refresh()
        settle_library(self.app, self.root)
        self.app.projects.selection_set(self.app.projects.get_children()[0])
        self.app.settings()
        self.root.deiconify()
        window = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        window.attributes("-alpha", 0)
        self.root.update()
        canvas = next(w for w in descendants(window) if isinstance(w, tk.Canvas))
        apply = next(w for w in descendants(window) if isinstance(w, Button) and w.cget("text") == "Apply changes")
        self.assertLess(canvas.winfo_rooty() + canvas.winfo_height(), apply.winfo_rooty())
        gridded = [w for w in canvas.master.winfo_children() if w.winfo_manager() == "grid"]
        for first in gridded:
            for second in gridded:
                if first is second:
                    continue
                a, b = first.grid_info(), second.grid_info()
                if a["row"] == b["row"]:
                    self.assertNotEqual(a["column"], b["column"], (str(first), str(second)))
        window.destroy()

    def test_empty_tables_have_real_empty_states_and_no_selectable_placeholder(self):
        self.app.tabs.select(self.app.library_tab)
        self.root.deiconify()
        self.root.update()
        table = self.app.projects
        self.assertIsInstance(table, DataTable)
        self.assertFalse(table.get_children())
        self.assertTrue(table.empty_label.winfo_ismapped())
        table.insert("", "end", iid="example", values=("Example", "Available"))
        self.root.update()
        self.assertFalse(table.empty_label.winfo_ismapped())
        table.delete("example")
        self.root.update()
        self.assertTrue(table.empty_label.winfo_ismapped())

    def test_supplement_review_reserves_actions_when_height_is_limited(self):
        folder = Path(self.temp.name) / "Papers"
        folder.mkdir()
        project = self.store.add_project(folder)
        from tests.test_notebook import sample_pdf
        path = folder / "Paper.pdf"
        sample_pdf(path)
        self.store.save_scan(project, path, "audit", "signature", "settings", {"title": "Paper"}, [])
        document_id = self.store.documents()[0]["id"]
        dialog = SupplementsWindow(self.app, document_id, path)
        dialog.window.attributes("-alpha", 0)
        dialog.window.geometry("760x550")
        self.root.deiconify()
        self.root.update()
        buttons = [w for w in descendants(dialog.window) if isinstance(w, Button)]
        self.assertGreater(len(buttons), 8)
        for button in buttons:
            self.assertTrue(button.winfo_ismapped(), button.cget("text"))
            self.assert_inside(button, dialog.window)
            self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth() - 2)
        self.assertGreater(dialog.tree.winfo_height(), 40)
        self.assertGreater(dialog.attached.winfo_height(), 40)
        dialog.window.destroy()

    def test_context_menus_and_saved_search_list_share_the_theme(self):
        self.app.saved_searches()
        self.root.update()
        listing = next(w for w in descendants(self.root) if isinstance(w, tk.Listbox))
        self.assertEqual(listing.cget("background"), PANEL)
        self.assertEqual(listing.cget("foreground"), TEXT)
        self.assertTrue(listing.cget("yscrollcommand"))
        for widget in descendants(self.root):
            if isinstance(widget, tk.Menu):
                self.assertEqual(str(widget.cget("background")), SURFACE)
                self.assertEqual(str(widget.cget("foreground")), TEXT)


class ThemeAndBrandingTests(unittest.TestCase):
    def test_table_rows_and_control_states_follow_font_scaling(self):
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale):
                root = tk.Tk()
                root.withdraw()
                original = root.tk.call("tk", "scaling")
                try:
                    root.tk.call("tk", "scaling", (96 / 72) * scale)
                    style = apply_theme(root)
                    lines = font.Font(root=root, font=style.lookup("Treeview", "font")).metrics("linespace")
                    self.assertGreaterEqual(int(style.lookup("Treeview", "rowheight")), lines + 8)
                    self.assertEqual(style.lookup("TRadiobutton", "foreground", ("disabled",)), MUTED)
                    self.assertEqual(style.lookup("TEntry", "bordercolor", ("focus",)), FOCUS)
                    self.assertEqual(style.lookup("TCombobox", "foreground", ("disabled", "readonly")), MUTED)
                finally:
                    root.tk.call("tk", "scaling", original)
                    root.destroy()

    def test_app_icon_contains_small_taskbar_and_high_dpi_variants(self):
        base = Path(__file__).resolve().parents[1]
        with Image.open(base / "Note icon.ico") as source:
            self.assertEqual(source.ico.sizes(), {(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)})
            for size in source.ico.sizes():
                frame = source.ico.getimage(size)
                self.assertTrue(frame.getchannel("A").getbbox())
                self.assertGreater(len(set(frame.get_flattened_data())), 10)
        root = tk.Tk()
        root.withdraw()
        try:
            apply_app_icon(root)
            self.assertEqual(len(root._app_icons), 6)
            child = tk.Toplevel(root)
            child.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
