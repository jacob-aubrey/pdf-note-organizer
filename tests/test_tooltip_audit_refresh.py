"""Current workflow help, checked on disposable Tk controls and libraries."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from note_organizer import archive_ui, maintenance_ui, research_tools, research_ui, storage_ui, support_ui
from note_organizer.support import UpdateResult
from note_organizer.widgets import annotate_buttons, dismiss_tooltips
from tests.test_preferences_ui import descendants
from tests import test_ui_audit


def help_text(widget):
    tooltip = getattr(widget, "tooltip", None)
    if tooltip is None:
        return ""
    return str(tooltip.text() if callable(tooltip.text) else tooltip.text)


class CurrentTooltipAuditTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp

    def tearDown(self):
        test_ui_audit.UIAuditTests.tearDown(self)
        self.assertFalse(self.errors)

    def assert_explained(self, parent):
        annotate_buttons(parent)
        controls = [widget for widget in descendants(parent) if isinstance(widget,
            (ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.Entry, ttk.Combobox, ttk.Spinbox))]
        self.assertTrue(controls)
        for widget in controls:
            with self.subTest(control=str(widget), kind=widget.winfo_class()):
                self.assertTrue(getattr(widget, "tooltip", None))
                self.assertTrue(widget.tooltip.enabled)
                self.assertTrue(help_text(widget).strip())
                self.assertNotEqual(help_text(widget), "Choose this action.")

    def test_every_main_tab_and_disabled_control_has_current_help(self):
        for tab in (self.app.inbox_tab, self.app.library_tab, self.app.notes_tab, self.app.remarkable_tab):
            self.assert_explained(tab)
        self.assertIn("Select an incoming document", help_text(self.app.inbox_view.review_button))
        self.assertIn("Review selected", help_text(self.app.inbox_view.file_button))

    def test_inbox_help_follows_ready_retry_and_busy_states(self):
        view = self.app.inbox_view
        path = str(self.pc / "Incoming.pdf")
        view.tree.insert("", "end", iid=path, values=("Incoming.pdf", "Ready"))
        view.tree.selection_set(path)
        self.assertIn("Identify", help_text(view.review_button))
        self.assertIn("retryable", help_text(view.retry_button))
        view.review_path, view.retry_available = path, True
        self.assertIn("Try identification again", help_text(view.retry_button))
        self.assertIn("Confirm the name", help_text(view.file_button))
        view.busy = True
        for button in (view.review_button, view.skip_button, view.retry_button, view.file_button):
            self.assertIn("Wait", help_text(button))

    def test_search_filters_and_preferences_controls_have_help(self):
        before = set(self.root.winfo_children())
        self.app.search_options()
        window = next(widget for widget in self.root.winfo_children() if widget not in before)
        self.assert_explained(window)
        self.app.search_scope.set("PDFs")
        self.assert_explained(window)
        window.destroy()
        with patch("note_organizer.dialogs.library_diagnostics", return_value={
                "active": {"name": "Synthetic library", "documents": 0, "notes": 0}, "alternatives": []}):
            self.app.global_settings()
        window = self.app.preferences_window
        self.assert_explained(window)
        viewer_help = self.app.preferences_dialog.viewer_help.get()
        self.assertIn("current Windows default PDF application", viewer_help)
        self.assertIn("Windows Settings", viewer_help)
        window.destroy()

    def test_feedback_help_names_actual_recipient_and_does_not_claim_private_form(self):
        for destination in ("test@example.org", "https://example.org/feedback", None):
            dialog = support_ui.FeedbackWindow(self.app, destination)
            self.assert_explained(dialog.window)
            text = help_text(dialog.open_button)
            self.assertNotIn("private", text.lower())
            if destination == "test@example.org":
                self.assertIn(destination, text)
                self.assertIn("send it yourself", text)
            elif destination:
                self.assertIn("submit it yourself", text)
            else:
                self.assertIn("Copy report", text)
            dialog.window.destroy()

    def test_updates_help_follows_pending_and_available_download_states(self):
        with patch.object(support_ui, "background"):
            dialog = support_ui.UpdatesWindow(self.app)
        self.assert_explained(dialog.window)
        self.assertIn("Checking", help_text(dialog.check_button))
        self.assertIn("Wait", help_text(dialog.release_button))
        self.assertIn("Wait", help_text(dialog.download_button))
        dialog.loaded(UpdateResult("available", "2.5.0", "A release is available", latest_version="2.6.0",
            release_url="https://example.org/release", download_url="https://example.org/source.zip", download_label="Download source…"))
        self.assertIn("does not install", help_text(dialog.download_button))
        self.assertIn("GitHub release", help_text(dialog.release_button))
        dialog.window.destroy()

    def test_citation_help_explains_individual_fields_and_saved_state(self):
        with patch.object(research_ui, "background"):
            dialog = research_ui.CitationWindow(self.app, "synthetic")
        self.assert_explained(dialog.window)
        fields = dict(zip(dialog.fields, dialog.inputs))
        self.assertIn("semicolons", help_text(fields["authors"]))
        self.assertIn("does not change PDF navigation", help_text(fields["pages"]))
        self.assertIn("DOI", help_text(fields["doi"]))
        self.assertIn("Wait", help_text(dialog.lookup))
        dialog.loaded({})
        self.assertIn("only this DOI", help_text(dialog.lookup))
        dialog.saving = True
        self.assertIn("Wait", help_text(dialog.cancel))
        dialog.saving = False
        dialog.close()

    def test_citation_conflict_options_and_actions_have_help(self):
        before = set(self.root.winfo_children())
        research_ui.review_citation_conflict(self.app, [{"title": "First"}, {"title": "Second"}], Mock())
        window = next(widget for widget in self.root.winfo_children() if widget not in before)
        self.assert_explained(window)
        self.assertEqual(len([widget for widget in descendants(window) if isinstance(widget, ttk.Radiobutton)]), 2)
        window.destroy()

    def test_supplement_help_distinguishes_candidates_from_attachments(self):
        with patch.object(research_ui, "background"):
            dialog = research_ui.SupplementsWindow(self.app, "synthetic", self.pc / "Paper.pdf")
        self.assert_explained(dialog.window)
        self.assertIn("web candidate", help_text(dialog.open))
        self.assertIn("attached file", help_text(dialog.open_attachment_file))
        dialog.web_links = [{"label": "Supplement", "source": "Publisher", "url": "https://example.org/si.pdf"}]
        dialog.tree.set_status()
        dialog.show_links()
        dialog.tree.selection_set("0")
        dialog.selection_changed()
        self.assertIn("browser", help_text(dialog.open))
        self.assertIn("100 MB", help_text(dialog.download))
        dialog.downloading = True
        self.assertIn("Wait", help_text(dialog.download))
        dialog.window.destroy()

    def test_saved_search_help_identifies_scope_and_pending_operations(self):
        before = set(self.root.winfo_children())
        with patch.object(research_tools, "background") as background:
            research_tools.open_saved_searches(self.app)
        window = next(widget for widget in self.root.winfo_children() if widget not in before)
        self.assert_explained(window)
        buttons = {widget.cget("text"): widget for widget in descendants(window) if isinstance(widget, ttk.Button)}
        self.assertIn("Wait", help_text(buttons["Apply saved search"]))
        background.call_args.args[2]({})
        self.assertIn("Select a saved search", help_text(buttons["Apply saved search"]))
        self.assertIn("Notes/PDFs/All", help_text(buttons["Save current search"]))
        window.destroy()

    def test_labels_help_explains_loading_and_guarded_close(self):
        before = set(self.root.winfo_children())
        with patch.object(self.app, "research_paper", return_value=("synthetic", str(self.pc / "Paper.pdf"))), \
                patch.object(research_tools, "background") as background:
            research_tools.open_labels(self.app)
        window = next(widget for widget in self.root.winfo_children() if widget not in before)
        self.assert_explained(window)
        save = next(widget for widget in descendants(window) if isinstance(widget, ttk.Button) and widget.cget("text") == "Save labels")
        self.assertIn("Wait", help_text(save))
        background.call_args.args[2]({"tag": [], "collection": []})
        self.assertIn("linked copies", help_text(save))
        window.destroy()

    def test_storage_help_explains_disabled_restore_and_cleanup_requirements(self):
        with patch.object(maintenance_ui, "background"):
            maintenance = maintenance_ui.MaintenanceWindow(self.app)
        self.assert_explained(maintenance.window)
        self.assertIn("Restore a verified backup first", help_text(maintenance.open_restored_button))
        maintenance.restored_path = Path("C:/Synthetic restored library")
        self.assertIn(str(maintenance.restored_path), help_text(maintenance.open_restored_button))
        maintenance.set_busy(True)
        self.assertIn("Wait", help_text(maintenance.close_button))
        maintenance.set_busy(False)
        maintenance.close()
        with patch.object(archive_ui, "background"):
            archives = archive_ui.ArchiveReviewWindow(self.app)
        self.assert_explained(archives.window)
        self.assertIn("No verified", help_text(archives.remove))
        archives.rows = [{"ready": True}]
        self.assertIn("acknowledgment", help_text(archives.remove))
        archives.acknowledged.set(True)
        self.assertIn("backup file", help_text(archives.remove))
        archives.close()
        with patch.object(storage_ui, "background"):
            copies = storage_ui.LegacyCleanupDialog(self.app)
        self.assert_explained(copies.window)
        self.assertIn("Wait", help_text(copies.remove_button))
        copies.busy = ""
        self.assertIn("Select only copies", help_text(copies.remove_button))
        copies.close()
        dismiss_tooltips()


if __name__ == "__main__":
    unittest.main()
