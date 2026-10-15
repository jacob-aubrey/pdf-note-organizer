"""Inline reading and resize behavior, using disposable Tk applications."""
from concurrent.futures import Future
from PIL import Image
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from note_organizer.widgets import WrapToolbar
from tests import test_ui_audit


class ResponsivePreviewTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = test_ui_audit.UIAuditTests.tearDown

    def test_hidden_toolbar_actions_reflow_and_cancel_cleanly_at_shutdown(self):
        window = tk.Toplevel(self.root)
        toolbar = WrapToolbar(window)
        toolbar.pack(fill="x")
        first = toolbar.add(ttk.Button(toolbar, text="First action"))
        second = toolbar.add(ttk.Button(toolbar, text="Second action"), visible=False)
        self.root.update()
        self.assertTrue(first.winfo_manager())
        self.assertFalse(second.winfo_manager())
        toolbar.set_visible(second, True)
        self.root.update()
        self.assertTrue(second.winfo_manager())
        toolbar.set_visible(first, False)
        self.root.update()
        self.assertFalse(first.winfo_manager())
        self.assertEqual(second.winfo_x(), 0)
        toolbar.schedule()
        self.root.after_cancel(toolbar.pending)
        window.destroy()
        self.assertFalse(self.errors)

    def test_image_follows_complete_text_and_shares_its_scrollbar(self):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        result = Future()
        result.set_result([{"document_id": "example", "key": "ink", "path": "paper.pdf", "page": 1,
                            "kind": "drawing", "comment": "Last paragraph of the note."}])
        image = Image.new("RGB", (600, 2400), "white")
        with patch.object(app, "load_preview_image", return_value=image):
            app.finish_query(app.query_generation, None, result)
            app.preview_future.result(timeout=2)
        app.poll()
        app.tabs.select(app.notes_tab)
        app.reader_views.select(app.note_details)
        self.root.geometry("1100x700")
        self.root.deiconify()
        self.root.update()
        app.draw_image()
        text = app.preview_text
        self.assertEqual(len(text.image_names()), 1)
        image_index = text.index(app.preview_image_name)
        self.assertTrue(text.compare(image_index, ">", text.search("Last paragraph", "1.0")))
        self.assertGreater(app.tk_image.height(), text.winfo_height())
        self.assertLessEqual(app.tk_image.width(), text.winfo_width()-28)
        text.yview_moveto(1)
        self.assertGreater(text.yview()[0], 0)
        before = text.get("1.0", "end")
        self.root.geometry("940x620")
        self.root.update()
        app.draw_image()
        self.assertEqual(text.get("1.0", "end"), before)
        self.assertEqual(len(text.image_names()), 1)
        self.assertEqual(str(text.cget("state")), "disabled")

    def test_wrapping_actions_expand_and_contract_without_clipping(self):
        window = tk.Toplevel(self.root)
        toolbar = WrapToolbar(window)
        toolbar.pack(fill="x")
        controls = [toolbar.add(ttk.Button(toolbar, text=label)) for label in
                    ("Open PDF", "Full page context", "Enlarge image", "Copy image")]
        self.root.update()
        widths = [control.winfo_reqwidth() for control in controls]
        wide = sum(widths) + 3*toolbar.gap + 4
        narrow = max(sum(widths[:2]), sum(widths[2:])) + toolbar.gap + 4
        for width, rows in ((wide, 1), (narrow, 2), (wide, 1)):
            window.geometry(f"{width}x200")
            self.root.update()
            self.assertEqual(len({control.winfo_y() for control in controls}), rows)
            for control in controls:
                self.assertLessEqual(control.winfo_x()+control.winfo_width(), toolbar.winfo_width())
                self.assertLessEqual(control.winfo_y()+control.winfo_height(), toolbar.winfo_height())
        window.destroy()
        self.assertFalse(self.errors)

    def test_switching_to_text_note_removes_previous_inline_image(self):
        app = self.app
        app.preview_text.configure(state="normal")
        app.preview_text.insert("1.0", "A drawing")
        app.preview_text.mark_set("preview_image", "end-1c")
        app.preview_text.configure(state="disabled")
        app.image = Image.new("RGB", (40, 40), "white")
        app.draw_image()
        self.assertEqual(len(app.preview_text.image_names()), 1)
        with patch.object(app, "selected_entry", return_value=None):
            app.preview()
        self.assertFalse(app.preview_text.image_names())
        self.assertIsNone(app.image)


if __name__ == "__main__":
    unittest.main()
