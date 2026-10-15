"""Search hints are presentation, never searchable or copyable query text."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from note_organizer.theme import BACKGROUND, FIELD, MUTED, apply_theme
from note_organizer.widgets import EntryPlaceholder


class SearchPlaceholderTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root)
        self.query = tk.StringVar(self.root)
        self.changes = []
        self.query.trace_add("write", lambda *_: self.changes.append(self.query.get()))
        self.entry = ttk.Entry(self.root, textvariable=self.query)
        self.entry.pack(fill="x", padx=12, pady=12)
        self.other = ttk.Entry(self.root)
        self.other.pack()
        # Keep the test window withdrawn. Simulate keyboard focus instead of
        # taking desktop focus away from the person running the application.
        self.focused = self.other
        self.entry.focus_get = lambda: self.focused
        self.entry.focus_set = lambda: self.focus(self.entry)
        self.hint = EntryPlaceholder(self.entry, "Search notes and PDF text…", self.query)
        self.root.update()

    def focus(self, widget):
        self.focused = widget
        self.hint.refresh()

    def shown(self):
        return self.hint.label.winfo_manager() == "place"

    def tearDown(self):
        self.root.destroy()

    def test_empty_hint_never_enters_query_or_fires_search(self):
        self.assertTrue(self.shown())
        self.assertEqual(self.hint.label.cget("foreground"), MUTED)
        self.assertEqual(self.hint.label.cget("background"), FIELD)
        self.assertEqual(self.query.get(), "")
        self.assertEqual(self.entry.get(), "")
        self.assertEqual(self.changes, [])
        self.focus(self.entry)
        self.root.update()
        self.assertFalse(self.shown())
        self.assertEqual(self.changes, [])
        self.focus(self.other)
        self.root.update()
        self.assertTrue(self.shown())
        self.assertEqual(self.changes, [])

    def test_typing_clearing_and_programmatic_changes_keep_real_values(self):
        self.focus(self.entry)
        self.root.update()
        self.entry.insert(0, "tantalum AND CT")
        self.root.update()
        self.assertEqual(self.query.get(), "tantalum AND CT")
        self.assertFalse(self.shown())
        self.focus(self.other)
        self.root.update()
        self.assertFalse(self.shown())
        self.query.set("")
        self.root.update()
        self.assertTrue(self.shown())
        self.assertEqual(self.changes, ["tantalum AND CT", ""])

    def test_hint_click_focuses_entry_and_selection_copy_contains_query_only(self):
        self.assertTrue(self.hint.label.bind("<Button-1>"))
        self.hint.focus()
        self.root.update()
        self.assertEqual(self.focused, self.entry)
        self.assertFalse(self.shown())
        self.assertEqual(self.changes, [])
        self.query.set("real search")
        self.entry.event_generate("<Control-a>")
        self.entry.selection_range(0, "end")
        self.entry.event_generate("<<Copy>>")
        self.assertEqual(self.root.clipboard_get(), "real search")
        self.query.set("")
        self.entry.selection_range(0, "end")
        self.assertFalse(self.entry.selection_present())
        self.assertEqual(self.entry.get(), "")

    def test_disabled_and_readonly_entries_stay_uneditable(self):
        self.entry.state(["disabled"])
        self.hint.refresh()
        self.assertEqual(self.hint.label.cget("background"), BACKGROUND)
        self.hint.focus()
        self.root.update()
        self.assertEqual(self.focused, self.other)
        self.entry.insert(0, "ignored")
        self.assertEqual(self.query.get(), "")
        self.entry.state(["!disabled", "readonly"])
        self.hint.refresh()
        self.hint.focus()
        self.root.update()
        self.assertEqual(self.focused, self.entry)
        self.entry.insert(0, "ignored")
        self.assertEqual(self.query.get(), "")
        self.assertEqual(self.changes, [])

    def test_dynamic_hint_and_long_text_do_not_resize_entry(self):
        before = self.entry.winfo_reqwidth()
        self.hint.text = lambda: "Search PDFs…"
        self.hint.refresh()
        self.assertEqual(self.hint.label.cget("text"), "Search PDFs…")
        self.hint.text = "An intentionally very long search hint " * 20
        self.hint.refresh()
        self.root.update()
        self.assertEqual(self.entry.winfo_reqwidth(), before)
        self.assertEqual(self.hint.label.place_info()["width"], "-14")

    def test_destroy_removes_own_trace_and_preserves_other_variable_observers(self):
        trace_id = self.hint.trace
        self.entry.destroy()
        self.root.update()
        self.assertTrue(self.hint.closed)
        self.assertFalse(any(trace_id == callback for _, callback in self.query.trace_info()))
        self.query.set("still usable")
        self.root.update()
        self.assertEqual(self.changes, ["still usable"])
        self.hint.destroy()  # Safe when destruction is repeated.

    def test_tcl_owned_combobox_popdown_does_not_break_hint_refresh(self):
        combo = ttk.Combobox(self.root, values=("Notes", "PDFs", "All"), state="readonly")
        combo.pack()
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.root.update()
        popdown = str(self.root.tk.call("ttk::combobox::PopdownWindow", str(combo)))
        try:
            self.root.tk.call("ttk::combobox::Post", str(combo))
            self.root.tk.call("focus", "-force", popdown + ".f.l")
            self.root.update()
            with patch.object(self.entry, "focus_get", side_effect=KeyError("popdown")):
                self.hint.refresh()
            self.assertEqual(self.query.get(), "")
            self.assertTrue(self.shown())
        finally:
            self.root.tk.call("ttk::combobox::Unpost", str(combo))
            combo.destroy()


if __name__ == "__main__":
    unittest.main()
