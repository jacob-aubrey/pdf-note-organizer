"""Real Tk sizing for labels that collapse before actions lose usable space."""
import tkinter as tk
from tkinter import ttk
import unittest

from note_organizer.icons import Button
from note_organizer.theme import apply_theme
from note_organizer.widgets import ResponsiveButtons, WrapToolbar
from tests import test_ui_audit


class ResponsiveButtonTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def resize(self, width):
        self.root.geometry(f"{width}x240+0+0")
        self.root.deiconify()
        self.root.update()
        self.assertFalse(self.errors)

    def test_toolbar_collapses_before_wrapping_and_restores_labels(self):
        toolbar = WrapToolbar(self.root)
        toolbar.pack(fill="x")
        labels = ("Open externally", "Reading mode", "Full page context", "Copy image")
        buttons = [toolbar.add(Button(toolbar, text=label)) for label in labels]
        self.resize(800)
        full = sum(button.measured_width() for button in buttons) + toolbar.gap * 3
        compact = sum(button.measured_width(True) for button in buttons) + toolbar.gap * 3
        self.resize((full + compact) // 2)
        self.assertTrue(all(button.compact for button in buttons))
        self.assertEqual(len({button.winfo_y() for button in buttons}), 1)
        self.assertEqual(tuple(button.cget("text") for button in buttons), labels)
        self.assertEqual(tuple(button.action_label for button in buttons), labels)
        self.resize(90)
        self.assertGreater(len({button.winfo_y() for button in buttons}), 1)
        for button in buttons:
            self.assertLessEqual(button.winfo_x() + button.winfo_width(), toolbar.winfo_width())
        self.resize(full + 10)
        self.assertTrue(all(not button.compact for button in buttons))
        self.assertEqual(len({button.winfo_y() for button in buttons}), 1)

    def test_critical_actions_keep_labels_until_other_actions_are_compact(self):
        toolbar = WrapToolbar(self.root)
        toolbar.pack(fill="x")
        ordinary = toolbar.add(Button(toolbar, text="Open externally"))
        critical = toolbar.add(Button(toolbar, text="File document"))
        width = ordinary.measured_width(True) + critical.measured_width(False) + toolbar.gap + 4
        self.resize(width)
        self.assertTrue(ordinary.compact)
        self.assertFalse(critical.compact)
        self.resize(ordinary.measured_width(True) + critical.measured_width(True) + toolbar.gap + 4)
        self.assertTrue(critical.compact)
        self.assertEqual(critical.action_label, "File document")

    def test_packed_form_keeps_field_usable_and_button_command_state(self):
        row = ttk.Frame(self.root)
        row.pack(fill="x")
        field = ttk.Entry(row, width=1)
        field.pack(side="left", fill="x", expand=True)
        calls = []
        button = Button(row, text="Browse…", command=lambda: calls.append(True))
        button.pack(side="right", padx=(6, 0))
        self.resize(180)
        self.assertIsInstance(row._responsive_buttons, ResponsiveButtons)
        self.assertTrue(button.compact)
        self.assertGreaterEqual(field.winfo_width(), 96)
        button.invoke()
        self.assertEqual(calls, [True])
        button.configure(state="disabled")
        self.resize(170)
        self.assertTrue(button.instate(["disabled"]))
        self.resize(500)
        self.assertFalse(button.compact)
        self.assertTrue(button.instate(["disabled"]))

    def test_grid_rows_measure_independently_and_restore_after_resize(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        entry = ttk.Entry(frame, width=16)
        entry.grid(row=0, column=0, sticky="ew")
        browse = Button(frame, text="Browse…")
        browse.grid(row=0, column=1, padx=(8, 0))
        close = Button(frame, text="Close")
        close.grid(row=1, column=1, sticky="e")
        self.resize(entry.winfo_reqwidth() + browse.measured_width(True) + 12)
        self.assertTrue(browse.compact)
        self.assertFalse(close.compact)
        self.resize(600)
        self.assertFalse(browse.compact)

    def test_dynamic_icons_and_compact_labels_preserve_action_identity(self):
        row = ttk.Frame(self.root)
        row.pack(fill="x")
        button = Button(row, text="Reading mode", underline=0)
        button.pack(side="left")
        self.resize(100)
        self.assertEqual(button.icon_name, "maximize")
        self.assertTrue(button.compact)
        button.configure(text="Exit reading mode")
        self.root.update()
        self.assertEqual(button.icon_name, "minimize")
        self.assertEqual(button.action_label, "Exit reading mode")
        self.assertEqual(button.cget("text"), "Exit reading mode")
        self.assertEqual(button.cget("underline"), 0)
        self.assertTrue(button.compact)
        self.resize(500)
        self.assertEqual(str(button.cget("compound")), "left")

    def test_icon_only_actions_and_width_stability_across_repeated_layouts(self):
        row = ttk.Frame(self.root)
        row.pack(fill="x")
        first = Button(row, text="Open externally")
        first.pack(side="left")
        copy = Button(row, text="Copy full path")
        copy.pack(side="left", padx=(6, 0))
        self.resize(160)
        signature = (first.winfo_reqwidth(), copy.winfo_reqwidth(), first.compact)
        for _ in range(12):
            row._responsive_buttons.schedule()
            self.root.update()
            self.assertEqual((first.winfo_reqwidth(), copy.winfo_reqwidth(), first.compact), signature)
        self.assertEqual(str(copy.cget("compound")), "image")
        self.resize(600)
        self.assertEqual(str(copy.cget("compound")), "image")
        self.assertFalse(first.compact)

    def test_hidden_actions_are_excluded_and_destroy_cancels_pending_layout(self):
        toolbar = WrapToolbar(self.root)
        toolbar.pack(fill="x")
        first = toolbar.add(Button(toolbar, text="Open externally"))
        second = toolbar.add(Button(toolbar, text="Full page context"))
        self.resize(first.measured_width(False) + 4)
        self.assertTrue(first.compact)
        toolbar.set_visible(second, False)
        self.root.update()
        self.assertFalse(first.compact)
        self.assertFalse(second.winfo_manager())
        toolbar.schedule()
        toolbar.destroy()
        self.root.update()
        self.assertFalse(self.errors)

    def test_sibling_counter_changes_reflow_a_fixed_width_header(self):
        row = ttk.Frame(self.root)
        row.pack(fill="x")
        button = Button(row, text="Reading mode")
        button.pack(side="left")
        counter = ttk.Label(row, text="1 / 2")
        counter.pack(side="right")
        self.resize(300)
        self.assertFalse(button.compact)
        counter.configure(text="Main search · Match 1000 of 2000")
        self.root.update()
        self.assertTrue(button.compact)
        counter.configure(text="1 / 2")
        self.root.update()
        self.assertFalse(button.compact)

    def test_high_dpi_icons_fit_and_destroy_before_registration_is_safe(self):
        self.root.tk.call("tk", "scaling", 2)
        row = ttk.Frame(self.root)
        row.pack(fill="x")
        buttons = [Button(row, text=label) for label in ("Open externally", "Reading mode")]
        for button in buttons:
            button.pack(side="left", padx=(0, 6))
        width = sum(button.measured_width(True) for button in buttons) + 16
        self.resize(width)
        self.assertTrue(all(button.compact for button in buttons))
        for button in buttons:
            self.assertLessEqual(button.winfo_x() + button.winfo_width(), row.winfo_width())
        doomed = Button(row, text="Close")
        doomed.destroy()
        self.root.update()
        self.assertFalse(self.errors)


class ResponsiveAppHeaderTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = test_ui_audit.UIAuditTests.tearDown

    def test_reader_header_controls_fit_without_overlap_at_minimum_window(self):
        app = self.app
        app.tabs.select(app.notes_tab)
        app.match_display.set("Main search · 629/629")
        self.root.deiconify()
        for size in ("940x620", "1250x820", "1600x900", "940x620"):
            self.root.geometry(size)
            self.root.update()
            header = app.reader_header
            children = sorted((child for child in header.pack_slaves() if child.winfo_viewable()),
                              key=lambda child: child.winfo_x())
            for index, child in enumerate(children):
                self.assertGreaterEqual(child.winfo_x(), 0, (size, child))
                self.assertLessEqual(child.winfo_x() + child.winfo_width(), header.winfo_width(),
                                     (size, child, child.winfo_width(), header.winfo_width()))
                if index:
                    before = children[index - 1]
                    self.assertLessEqual(before.winfo_x() + before.winfo_width(), child.winfo_x(),
                                         (size, before, child))
            if size == "940x620":
                self.assertTrue(app.source_button.compact)
                self.assertTrue(app.reader_expand_button.compact)
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
