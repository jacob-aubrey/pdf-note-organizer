"""Workflow hover-help coverage uses synthetic controls and no library/account."""
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from note_organizer.remarkable_sync import default_config
from note_organizer.widgets import BUTTON_HELP, CellTooltip, annotate_buttons, dismiss_tooltips
from note_organizer.workflow_ui import IntegrationFields, ReconciliationWindow, SortingFields


def descendants(parent):
    for widget in parent.winfo_children():
        yield widget
        yield from descendants(widget)


class WorkflowTooltipTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.app = SimpleNamespace(root=self.root,
            inbox=SimpleNamespace(config=lambda: {"watch_folder": "", "library_root": "", "enabled": False,
                "naming_mode": "Basic", "filename_format": "smart", "online_metadata_lookup_enabled": False,
                "allow_cloud_ai_for_word_documents": False, "allow_cloud_ai_for_presentation_documents": False}),
            cloud_config=lambda: default_config("Synthetic data"),
            refresh=Mock(), service=Mock(), store=None)

    def tearDown(self):
        dismiss_tooltips()
        self.root.destroy()
        self.assertFalse(self.errors)

    def assert_controls_explained(self, parent):
        annotate_buttons(parent)
        missing = []
        for widget in descendants(parent):
            if not isinstance(widget, (ttk.Button, ttk.Checkbutton, ttk.Entry, ttk.Combobox, ttk.Spinbox)):
                continue
            tooltip = getattr(widget, "tooltip", None)
            text = tooltip.text() if tooltip and callable(tooltip.text) else tooltip.text if tooltip else ""
            if not tooltip or not tooltip.enabled or not str(text).strip():
                label = widget.cget("text") if isinstance(widget, (ttk.Button, ttk.Checkbutton)) else widget.winfo_class()
                missing.append(label)
        self.assertFalse(missing, "Missing hover help: " + ", ".join(missing))

    def test_sorting_controls_explain_folder_naming_and_optional_service_choices(self):
        frame = ttk.Frame(self.root)
        SortingFields(self.app, frame)
        self.assert_controls_explained(frame)

    def test_connection_options_are_explained_even_when_master_is_off(self):
        frame = ttk.Frame(self.root)
        fields = IntegrationFields(self.app, frame)
        self.assert_controls_explained(frame)
        self.assertFalse(fields.master.get())
        self.assertTrue(all(control.instate(["disabled"]) for control in fields.checks))
        fields.master.set(True)
        self.assert_controls_explained(frame)
        self.assertTrue(all(not control.instate(["disabled"]) for control in fields.checks))

    def test_reconciliation_controls_explain_scan_scope_and_review_actions(self):
        def tree(parent, columns, **_):
            listing = ttk.Treeview(parent, columns=[column[0] for column in columns], show="headings")
            listing.pack()
            CellTooltip(listing)
            return listing
        self.app.tree = tree
        # This fixture checks static hover help, without a library or workers.
        with patch("note_organizer.workflow_ui.background"):
            window = ReconciliationWindow(self.app)
        window.window.withdraw()
        self.assert_controls_explained(window.window)
        self.assertTrue(window.link_button.instate(["disabled"]))
        self.assertTrue(window.map_button.instate(["disabled"]))
        self.assertTrue(window.send_button.instate(["disabled"]))
        window.close()
        self.assertTrue(window.cancelled.is_set())

    def test_auto_help_follows_button_labels_when_panels_expand_and_collapse(self):
        frame = ttk.Frame(self.root)
        for initial, changed in (("Show sync details", "Hide sync details"), ("Edit setup", "Hide setup")):
            with self.subTest(initial=initial):
                button = ttk.Button(frame, text=initial)
                annotate_buttons(frame)
                tooltip = button.tooltip
                text = tooltip.text() if callable(tooltip.text) else tooltip.text
                self.assertEqual(text, BUTTON_HELP[initial])
                button.configure(text=changed)
                text = tooltip.text() if callable(tooltip.text) else tooltip.text
                self.assertEqual(text, BUTTON_HELP[changed])


if __name__ == "__main__":
    unittest.main()
