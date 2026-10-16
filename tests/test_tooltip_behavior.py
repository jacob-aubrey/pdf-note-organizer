"""Hover-help regressions use synthetic Tk controls and a mocked pointer."""
from contextlib import contextmanager, ExitStack
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from note_organizer.widgets import Tooltip, EntryPlaceholder, dismiss_tooltips


class TooltipBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.button = ttk.Button(self.root, text="Synthetic help")
        self.button.pack()
        self.root.update_idletasks()

    def tearDown(self):
        dismiss_tooltips()
        self.root.destroy()
        self.assertFalse(self.errors)

    @contextmanager
    def hovering(self, widget, *, target=None, focused=True):
        """Simulate a hover without moving the user's pointer or activating a window."""
        owner = widget.winfo_toplevel()
        with ExitStack() as stack:
            stack.enter_context(patch.object(widget, "winfo_viewable", return_value=True))
            stack.enter_context(patch.object(widget, "winfo_pointerxy", return_value=(10, 10)))
            stack.enter_context(patch.object(widget, "winfo_containing", return_value=target or widget))
            stack.enter_context(patch.object(owner, "focus_displayof", return_value=owner if focused else None))
            yield

    @contextmanager
    def popup(self):
        """Observe a popup's lifecycle without displaying a native test window."""
        window = Mock()
        window.winfo_screenwidth.return_value = 1920
        window.winfo_screenheight.return_value = 1080
        window.winfo_reqwidth.return_value = 200
        window.winfo_reqheight.return_value = 60
        with patch("note_organizer.widgets.tk.Toplevel", return_value=window), \
                patch("note_organizer.widgets.ttk.Label"):
            yield window

    def test_keyboard_focus_never_schedules_help(self):
        tip = Tooltip(self.button, "Explanation")
        self.assertEqual(self.button.bind("<FocusIn>"), "")
        self.button.event_generate("<FocusIn>")
        self.root.update()
        self.assertIsNone(tip.pending)
        self.assertIsNone(tip.window)

    def test_pointer_is_checked_when_delayed_help_would_display(self):
        tip = Tooltip(self.button, "Explanation")
        tip.schedule()
        self.assertIsNotNone(tip.pending)
        with self.hovering(self.button, target=self.root), self.popup() as window:
            tip.show()
        self.assertIsNone(tip.pending)
        self.assertIsNone(tip.window)
        window.deiconify.assert_not_called()

    def test_one_pending_or_visible_tooltip_globally(self):
        first = Tooltip(self.button, "First explanation")
        other = ttk.Button(self.root, text="Other synthetic help")
        second = Tooltip(other, "Second explanation")
        with self.hovering(self.button), self.popup() as first_window:
            first.show()
        self.assertIs(first.window, first_window)
        second.schedule()
        self.assertIsNone(first.window)
        first_window.destroy.assert_called_once()
        self.assertIsNotNone(second.pending)
        with self.hovering(other), self.popup() as second_window:
            second.show()
        self.assertIs(second.window, second_window)
        self.assertIs(Tooltip._active, second)
        self.assertIsNone(first.pending)

    def test_tab_focus_and_unmap_changes_dismiss_visible_and_pending_help(self):
        tip = Tooltip(self.button, "Explanation")
        for event in ("<<NotebookTabChanged>>", "<FocusOut>", "<Unmap>"):
            with self.subTest(event=event):
                with self.hovering(self.button), self.popup():
                    tip.show()
                self.root.event_generate(event)
                self.root.update()
                self.assertIsNone(tip.window)
                tip.schedule()
                self.assertIsNotNone(tip.pending)
                self.root.event_generate(event)
                self.root.update()
                self.assertIsNone(tip.pending)

    def test_disabled_control_still_explains_itself_on_hover(self):
        self.button.configure(state="disabled")
        tip = Tooltip(self.button, "Choose a paper first")
        with self.hovering(self.button), self.popup() as window:
            tip.show()
        self.assertIs(tip.window, window)
        window.deiconify.assert_called_once()

    def test_empty_search_hint_forwards_hover_to_its_entry_help(self):
        value = tk.StringVar(self.root)
        entry = ttk.Entry(self.root, textvariable=value)
        entry.pack()
        hint = EntryPlaceholder(entry, "Search…", value)
        tip = Tooltip(entry, "Search fields and Boolean rules")
        hint.help_enter()
        self.assertIsNotNone(tip.pending)
        with self.hovering(entry, target=hint.label), self.popup() as window:
            tip.show()
        window.deiconify.assert_called_once()
        self.assertEqual(value.get(), "")

    def test_only_known_placeholder_overlay_counts_as_entry_hover(self):
        entry = ttk.Entry(self.root)
        entry.pack()
        other_child = tk.Label(entry, text="Unrelated child")
        tip = Tooltip(entry, "Explanation")
        with self.hovering(entry, target=other_child):
            self.assertFalse(tip.pointer_over())

    def test_native_pdf_focus_allows_hover_only_while_its_app_is_foreground(self):
        tip = Tooltip(self.button, "Compact control explanation")
        native = Mock()
        self.root._native_reader_children = [native]
        with self.hovering(self.button, focused=False):
            native.owner_is_foreground.return_value = True
            self.assertTrue(tip.pointer_over())
            native.owner_is_foreground.return_value = False
            self.assertFalse(tip.pointer_over())

    def test_help_cannot_display_over_an_inactive_owner(self):
        tip = Tooltip(self.button, "Explanation")
        with self.hovering(self.button, focused=False), self.popup() as window:
            tip.show()
        self.assertIsNone(tip.window)
        window.deiconify.assert_not_called()

    def test_dialog_hover_does_not_require_clicking_to_move_keyboard_focus(self):
        dialog = tk.Toplevel(self.root)
        button = ttk.Button(dialog, text="Dialog action")
        tip = Tooltip(button, "Dialog explanation")
        with self.hovering(button), patch.object(dialog, "focus_displayof", return_value=self.button), self.popup() as popup:
            tip.show()
        self.assertIs(tip.window, popup)
        popup.deiconify.assert_called_once()

    def test_dialog_hover_accepts_native_reader_focus_in_same_foreground_app(self):
        dialog = tk.Toplevel(self.root)
        button = ttk.Button(dialog, text="Dialog action")
        tip = Tooltip(button, "Dialog explanation")
        native = Mock()
        self.root._native_reader_children = [native]
        with self.hovering(button, focused=False):
            native.owner_is_foreground.return_value = True
            self.assertTrue(tip.pointer_over())
            native.owner_is_foreground.return_value = False
            self.assertFalse(tip.pointer_over())

    def test_modal_dialog_blocks_hover_help_on_other_app_windows(self):
        dialog = tk.Toplevel(self.root)
        tip = Tooltip(self.button, "Main window explanation")
        with self.hovering(self.button), patch.object(self.button, "grab_current", return_value=dialog):
            self.assertFalse(tip.pointer_over())

    def test_containers_and_whole_static_tables_do_not_show_help(self):
        for widget in (ttk.Frame(self.root), ttk.Notebook(self.root), tk.Canvas(self.root),
                       tk.Text(self.root), ttk.Panedwindow(self.root), ttk.Treeview(self.root)):
            with self.subTest(widget=type(widget).__name__):
                tip = Tooltip(widget, "Broad panel explanation")
                with self.hovering(widget), self.popup() as window:
                    tip.schedule()
                    tip.show()
                self.assertFalse(tip.enabled)
                self.assertIsNone(tip.pending)
                self.assertIsNone(tip.window)
                window.deiconify.assert_not_called()

    def test_dynamic_table_help_is_restricted_to_a_real_cell(self):
        table = ttk.Treeview(self.root)
        tip = Tooltip(table, lambda: "Page details for the hovered row")
        for region, row in (("heading", ""), ("nothing", ""), ("cell", ""), ("cell", "row")):
            with self.subTest(region=region, row=row):
                tip.hide()
                with self.hovering(table), self.popup() as window, \
                        patch.object(table, "identify_region", return_value=region), \
                        patch.object(table, "identify_row", return_value=row):
                    tip.show()
                self.assertEqual(tip.window is window, region == "cell" and bool(row))

    def test_destroy_cancels_pending_help_and_destroys_visible_help(self):
        tip = Tooltip(self.button, "Explanation")
        tip.schedule()
        self.button.destroy()
        self.assertIsNone(tip.pending)
        other = ttk.Button(self.root, text="Other synthetic help")
        tip = Tooltip(other, "Explanation")
        with self.hovering(other), self.popup() as window:
            tip.show()
        other.destroy()
        self.assertIsNone(tip.window)
        window.destroy.assert_called_once()
        # Dismissal remains safe after the widget's Tcl command is gone.
        tip.hide()
        self.assertFalse(tip.pointer_over())


if __name__ == "__main__":
    unittest.main()
