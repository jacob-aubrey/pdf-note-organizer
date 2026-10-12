"""Sorter hover-help and draft-state checks without accounts or real documents."""
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest

from note_organizer.inbox import DEFAULT_CONFIG
from note_organizer.sorting.core_logic import FILENAME_TEMPLATE_TOKENS
from note_organizer.widgets import CellTooltip, dismiss_tooltips
from note_organizer.workflow_ui import InboxView, SortingFields


class SortingTooltipTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.parent = ttk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)
        self.app = SimpleNamespace(root=self.root, inbox=SimpleNamespace(config=lambda: dict(DEFAULT_CONFIG)))

    def tearDown(self):
        dismiss_tooltips()
        self.root.destroy()
        self.assertFalse(self.errors)

    def controls(self, parent):
        for child in parent.winfo_children():
            if isinstance(child, (ttk.Entry, ttk.Combobox, ttk.Button, ttk.Checkbutton)):
                yield child
            yield from self.controls(child)

    def test_every_sorting_setting_control_has_meaningful_hover_help(self):
        fields = SortingFields(self.app, self.parent)
        for control in self.controls(self.parent):
            with self.subTest(control=control.winfo_class(), text=control.cget("text") if "text" in control.keys() else "entry"):
                self.assertTrue(hasattr(control, "tooltip"))
                text = control.tooltip.text
                text = text() if callable(text) else text
                self.assertGreater(len(text), 30)
        self.assertIn("does not require a Gemini key", fields.online_check.tooltip.text)
        self.assertIn("not the document text or file", fields.online_check.tooltip.text)
        self.assertIn(".docx", fields.word_ai_check.tooltip.text)
        self.assertIn(".pptx", fields.slides_ai_check.tooltip.text)
        self.assertIn("Legacy .ppt", fields.slides_ai_check.tooltip.text)

    def test_custom_template_help_lists_real_tokens_and_preserves_extension(self):
        fields = SortingFields(self.app, self.parent)
        text = fields.template_entry.tooltip.text()
        for token in FILENAME_TEMPLATE_TOKENS:
            self.assertIn("{" + token + "}", text)
        self.assertIn("{author_last_et_al}_{year}_{title}", text)
        self.assertIn("added automatically", text)
        self.assertTrue(fields.template_entry.instate(["disabled"]))
        fields.format.set(fields.labels["custom"])
        self.assertFalse(fields.template_entry.instate(["disabled"]))
        fields.format.set(fields.labels["smart"])
        self.assertTrue(fields.template_entry.instate(["disabled"]))

    def test_local_and_gemini_settings_disable_irrelevant_controls_without_losing_consent(self):
        fields = SortingFields(self.app, self.parent)
        fields.word_ai.set(True)
        self.assertFalse(fields.online_check.instate(["disabled"]))
        self.assertTrue(fields.word_ai_check.instate(["disabled"]))
        fields.gemini_enabled.set(True)
        self.assertFalse(fields.word_ai_check.instate(["disabled"]))
        fields.mode.set("Local only")
        for control in (fields.online_check, fields.word_ai_check, fields.slides_ai_check):
            self.assertTrue(control.instate(["disabled"]))
        self.assertTrue(fields.word_ai.get())
        fields.mode.set("Smart metadata lookup")
        self.assertFalse(fields.word_ai_check.instate(["disabled"]))
        fields.gemini_enabled.set(False)
        self.assertTrue(fields.word_ai_check.instate(["disabled"]))
        self.assertFalse(fields.online_check.instate(["disabled"]))

    def test_inbox_controls_and_real_status_cells_explain_review_flow(self):
        def tree(parent, columns, **kwargs):
            result = ttk.Treeview(parent, columns=[column[0] for column in columns], show="headings")
            result.pack(fill="both", expand=True)
            CellTooltip(result)
            return result
        self.app.tree = tree
        self.app.initial_split = lambda *args: None
        self.app.review_library = lambda: None
        self.app.filing_recovery = lambda: None
        view = InboxView(self.app, self.parent)
        for control in self.controls(self.parent):
            with self.subTest(control=control.winfo_class()):
                self.assertTrue(hasattr(control, "tooltip"))
        self.assertIn(".pptx", view.name_entry.tooltip.text())
        self.assertIn("new subfolder", view.destination_entry.tooltip.text())
        self.assertIn("Only PDFs", view.file_button.tooltip.text)
        view.rows["synthetic.pdf"] = {"status": "waiting"}
        self.assertIn("Refresh inbox", view.item_help("synthetic.pdf", "state"))
        view.rows["synthetic.pdf"] = {"status": "skipped"}
        self.assertIn("any time", view.item_help("synthetic.pdf", "state"))
        view.rows["synthetic.pdf"] = {"status": "error", "error": "Synthetic problem"}
        self.assertEqual(view.item_help("synthetic.pdf", "state"), "Synthetic problem")
        self.assertEqual(view.item_help("synthetic.pdf", "name"), "")


if __name__ == "__main__":
    unittest.main()
