"""Consistent path controls use disposable Tk widgets and a mocked clipboard."""
from contextlib import contextmanager, ExitStack
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from note_organizer.widgets import (
    CellTooltip, PathField, PathTextTooltip, ReadOnlyText, SelectionDetails,
    Tooltip, dismiss_tooltips,
)


class ConsistentPathHelperTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.path = r"C:\Synthetic research library\Long folder name\paper.pdf"

    def tearDown(self):
        dismiss_tooltips()
        self.root.destroy()
        self.assertFalse(self.errors)

    @contextmanager
    def hovering(self, widget):
        owner = widget.winfo_toplevel()
        with ExitStack() as stack:
            stack.enter_context(patch.object(widget, "winfo_viewable", return_value=True))
            stack.enter_context(patch.object(widget, "winfo_pointerxy", return_value=(10, 10)))
            stack.enter_context(patch.object(widget, "winfo_rootx", return_value=0))
            stack.enter_context(patch.object(widget, "winfo_rooty", return_value=0))
            stack.enter_context(patch.object(widget, "winfo_containing", return_value=widget))
            stack.enter_context(patch.object(owner, "focus_displayof", return_value=owner))
            yield

    @contextmanager
    def popup(self):
        window = Mock()
        window.winfo_reqwidth.return_value = 200
        window.winfo_reqheight.return_value = 60
        with patch("note_organizer.widgets.tk.Toplevel", return_value=window), \
                patch("note_organizer.widgets.ttk.Label"):
            yield window

    def test_table_path_and_explanation_are_identical_in_wide_and_narrow_cells(self):
        tree = ttk.Treeview(self.root, columns=("name",), show="headings")
        tree.insert("", "end", iid="paper", values=("paper.pdf",))
        tip = CellTooltip(tree, value=lambda row, column: self.path,
                          extra=lambda row, column: "The original PDF on this PC.")
        tip.cell = ("paper", "name", "#1")
        for width in (45, 1200):
            with self.subTest(width=width), self.hovering(tree), \
                    patch.object(tip, "identify", return_value=tip.cell), \
                    patch.object(tree, "bbox", return_value=(0, 0, width, 30)), \
                    patch.object(tree, "winfo_width", return_value=width):
                self.assertEqual(tip.cell_text(), self.path + "\n\nThe original PDF on this PC.")

    def test_table_explicit_full_path_help_remains_visible_when_path_fits(self):
        tree = ttk.Treeview(self.root, columns=("path",), show="headings")
        tree.insert("", "end", iid="paper", values=(self.path,))
        tip = CellTooltip(tree, extra=lambda row, column: "Linked PC destination.")
        tip.full_with_help = True
        tip.cell = ("paper", "path", "#1")
        with self.hovering(tree), patch.object(tip, "identify", return_value=tip.cell), \
                patch.object(tree, "bbox", return_value=(0, 0, 1800, 30)), \
                patch.object(tree, "winfo_width", return_value=1800):
            self.assertEqual(tip.cell_text(), self.path + "\n\nLinked PC destination.")

    def test_path_getter_and_explanation_are_dynamic_and_copy_uses_current_value(self):
        label = ttk.Label(self.root, text="Short display")
        location = {"path": self.path, "help": "Original source."}
        access = PathField(label, lambda: location["help"], value=lambda: location["path"])
        button = access.add_copy_button(self.root)
        self.assertEqual(label.tooltip.text(), self.path + "\n\nOriginal source.")
        location.update(path=self.path + ".changed", help="Changed source.")
        access.refresh()
        self.assertEqual(label.tooltip.text(), location["path"] + "\n\nChanged source.")
        self.assertIn(location["path"], button.tooltip.text())
        with patch.object(label, "clipboard_clear") as cleared, \
                patch.object(label, "clipboard_append") as copied:
            button.invoke()
        cleared.assert_called_once()
        copied.assert_called_once_with(location["path"])

    def test_copy_is_a_compact_icon_control_without_path_context_menu(self):
        entry = ttk.Entry(self.root)
        entry.insert(0, self.path)
        access = PathField(entry, "Choose a folder.")
        button = access.add_copy_button(self.root)
        self.assertEqual(button.cget("text"), "Copy full path")
        self.assertEqual(str(button.cget("compound")), "image")
        self.assertEqual(button.icon_name, "copy")
        self.assertEqual(button.cget("style"), "Compact.TButton")
        self.assertFalse(hasattr(access, "menu"))
        self.assertFalse(hasattr(access, "popup"))
        for event in ("<Button-3>", "<Shift-F10>", "<Menu>"):
            self.assertEqual(entry.bind(event), "")
        self.assertIn(self.path, button.tooltip.text())
        self.assertIn("complete", button.tooltip.text())

    def test_textvariable_writes_update_copy_state_and_destroy_keeps_the_variable(self):
        value = tk.StringVar(self.root, value="")
        entry = ttk.Entry(self.root, textvariable=value)
        original_traces = value.trace_info()
        access = PathField(entry, "Choose a folder.")
        button = access.add_copy_button(self.root)
        self.assertTrue(button.instate(["disabled"]))
        value.set(self.path)
        self.root.update_idletasks()
        self.assertFalse(button.instate(["disabled"]))
        self.assertIn(self.path, entry.tooltip.text())
        value.set("")
        self.root.update_idletasks()
        self.assertTrue(button.instate(["disabled"]))
        with patch.object(entry, "clipboard_clear") as clear, \
                patch.object(entry, "clipboard_append") as copied:
            access.copy()
        clear.assert_not_called()
        copied.assert_not_called()
        value.set(self.path)
        self.assertIsNotNone(access.pending_refresh)
        entry.destroy()
        self.assertIsNone(access.pending_refresh)
        self.assertEqual(value.trace_info(), original_traces)
        value.set("The retained variable is still usable")
        self.root.update()
        self.assertEqual(value.get(), "The retained variable is still usable")

    def test_unknown_paths_and_surrounding_prose_do_not_get_path_hover_help(self):
        text = tk.Text(self.root)
        other = r"C:\Not registered\another.pdf"
        text.insert("1.0", "Explanation\n" + self.path + "\nMore text\n" + other)
        tip = PathTextTooltip(text)
        tip.set_paths({"Original": (self.path, "Original document.")})
        self.assertEqual(len(tip.spans), 1)
        for index, expected in (("1.3", ""), ("2.4", self.path + "\n\nOriginal document."),
                                ("3.2", ""), ("4.5", "")):
            with self.subTest(index=index), self.hovering(text), \
                    patch.object(text, "index", return_value=index), \
                    patch.object(text, "bbox", return_value=(0, 0, 30, 25)):
                self.assertEqual(tip.path_text(), expected)
                self.assertEqual(tip.pointer_over(), bool(expected))

    def test_path_hover_popup_rechecks_pointer_and_is_dismissed_after_leaving_path(self):
        text = tk.Text(self.root)
        text.insert("1.0", self.path + "\nExplanation")
        tip = PathTextTooltip(text)
        tip.set_paths({"Original": (self.path, "Original source.")})
        with self.hovering(text), patch.object(text, "index", return_value="1.5"), \
                patch.object(text, "bbox", return_value=(0, 0, 30, 25)), \
                self.popup() as popup, patch.object(tip, "popup_position", return_value=(20, 30)):
            tip.show()
            popup.deiconify.assert_called_once()
            self.assertIs(tip.window, popup)
            tip.current = tip.spans[0]
            with patch.object(text, "index", return_value="2.3"):
                tip.motion()
            self.assertIsNone(tip.window)
            popup.destroy.assert_called_once()
        with self.hovering(text), patch.object(text, "index", return_value="2.3"), \
                patch.object(text, "bbox", return_value=(0, 0, 30, 25)), \
                self.popup() as popup:
            tip.show()
            popup.deiconify.assert_not_called()

    def test_generic_text_hover_stays_disabled_and_explicit_path_hover_works(self):
        text = tk.Text(self.root)
        text.insert("1.0", self.path)
        generic = Tooltip(text, "Broad panel explanation")
        self.assertFalse(generic.enabled)
        explicit = PathTextTooltip(text)
        explicit.set_paths({"Original": (self.path, "Original document.")})
        self.assertTrue(explicit.enabled)
        with self.hovering(text), patch.object(text, "index", return_value="1.4"), \
                patch.object(text, "bbox", return_value=(0, 0, 30, 25)):
            self.assertFalse(generic.pointer_over())
            self.assertTrue(explicit.pointer_over())

    def test_multiline_named_path_copy_copies_only_the_chosen_location(self):
        details = SelectionDetails(self.root)
        second = r"C:\Synthetic destination\copy.pdf"
        content = f"Needs review\nOriginal: {self.path}\nDestination: {second}"
        paths = {"Original file": (self.path, "Original download."),
                 "Destination file": (second, "Retained filed copy.")}
        details.set(content, paths=paths)
        self.assertEqual(details.path_selector.cget("values"), tuple(paths))
        for label, (path, help_text) in paths.items():
            details.path_selector.set(label)
            details.path_access.refresh()
            self.assertEqual(details.path_selector.tooltip.text(), path + "\n\n" + help_text)
            with patch.object(details.path_selector, "clipboard_clear"), \
                    patch.object(details.path_selector, "clipboard_append") as copied:
                details.path_copy_button.invoke()
            copied.assert_called_once_with(path)
        with patch.object(details, "clipboard_clear"), patch.object(details, "clipboard_append") as copied:
            details.copy_button.invoke()
        copied.assert_called_once_with(content)
        details.set("Choose a document.", selected=False, paths=paths)
        self.assertTrue(details.copy_button.instate(["disabled"]))
        self.assertTrue(details.path_copy_button.instate(["disabled"]))
        self.assertEqual(details.paths, {})

    def test_unchanged_details_keep_selection_and_selected_path(self):
        details = SelectionDetails(self.root)
        content = "Explanation\n" + self.path
        paths = {"PDF": (self.path, "Local source.")}
        details.set(content, paths=paths)
        details.text.tag_add("sel", "1.0", "1.5")
        selected = tuple(str(index) for index in details.text.tag_ranges("sel"))
        details.set(content, paths=paths)
        self.assertEqual(tuple(str(index) for index in details.text.tag_ranges("sel")), selected)
        self.assertEqual(details.path_selector.get(), "PDF")
        self.assertEqual(len(details.path_tooltip.spans), 1)

    def test_readonly_text_paths_are_explicit_and_replaced_with_the_contents(self):
        display = ReadOnlyText(self.root)
        display.set(self.path, paths={"Original": (self.path, "Original source.")})
        self.assertEqual(len(display.path_tooltip.spans), 1)
        display.set("A different message without a known path.")
        self.assertEqual(display.path_tooltip.spans, [])
        self.assertIsNone(display.path_tooltip.current)

    def test_wrapped_path_hover_rejects_blank_margin_beside_a_display_line(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("260x220")
        text = tk.Text(self.root, width=1, height=6, wrap="word", padx=6)
        text.pack(fill="both", expand=True)
        path = r"C:\Research library\Folder with some spaces\One more long folder\paper.pdf"
        text.insert("1.0", path + "\nExplanation")
        tip = PathTextTooltip(text)
        tip.set_paths({"PDF": (path, "Original PDF.")})
        self.root.deiconify()
        self.root.update()
        x, y, width, height, _ = text.dlineinfo("1.0")
        ink_point = (text.winfo_rootx() + x + 1, text.winfo_rooty() + y + height // 2)
        blank_point = (text.winfo_rootx() + text.winfo_width() - 4,
                       text.winfo_rooty() + y + height // 2)
        self.assertLess(x + width, text.winfo_width() - 4)
        with patch.object(text, "winfo_pointerxy", return_value=ink_point):
            self.assertEqual(tip.identify()[2], path)
        with patch.object(text, "winfo_pointerxy", return_value=blank_point):
            self.assertIsNone(tip.identify())

    def test_long_path_tooltip_widens_to_fit_the_owning_monitor_without_shortening_value(self):
        value = "C:\\" + "\\".join(f"Long research folder name number {number}" for number in range(26)) + "\\paper.pdf"
        entry = ttk.Entry(self.root)
        entry.insert(0, value)
        access = PathField(entry, "Original PDF in the selected research folder.")
        native_toplevel = tk.Toplevel
        def invisible_toplevel(*args, **kwargs):
            window = native_toplevel(*args, **kwargs)
            window.attributes("-alpha", 0)
            return window
        with self.hovering(entry), patch("note_organizer.widgets.work_area", return_value=(0, 0, 900, 220)), \
                patch("note_organizer.widgets.tk.Toplevel", side_effect=invisible_toplevel):
            entry.tooltip.show()
            self.root.update_idletasks()
        window = entry.tooltip.window
        self.assertIsNotNone(window)
        label = window.winfo_children()[0]
        self.assertEqual(label.cget("text"), access.help())
        self.assertGreater(int(label.cget("wraplength")), 340)
        self.assertLessEqual(window.winfo_reqwidth(), 884)
        self.assertLessEqual(window.winfo_reqheight(), 204)


if __name__ == "__main__":
    unittest.main()
