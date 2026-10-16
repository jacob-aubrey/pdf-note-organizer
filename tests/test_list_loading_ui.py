"""List placeholders distinguish pending work, no results, and failures."""
import unittest
from unittest.mock import patch

from note_organizer.research_ui import SupplementsWindow
from note_organizer.storage_ui import LegacyCleanupDialog
from note_organizer.widgets import DataTable
from tests import test_ui_audit
from tests.test_preferences_ui import descendants


class ListLoadingUITests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp

    def tearDown(self):
        test_ui_audit.UIAuditTests.tearDown(self)
        self.assertFalse(self.errors)

    def test_extra_pdf_review_explains_pending_check_and_failure_inside_the_list(self):
        with patch("note_organizer.storage_ui.background"):
            dialog = LegacyCleanupDialog(self.app)
        self.assertEqual(dialog.tree.status_message, "Checking extra PDF copies…")
        dialog.loaded([])
        self.assertIsNone(dialog.tree.status_message)
        with patch("note_organizer.storage_ui.background"):
            dialog.refresh()
        self.assertEqual(dialog.tree.status_message, "Checking extra PDF copies…")
        dialog.failed(OSError("Synthetic unavailable original"))
        self.assertIn("failed", dialog.tree.status_message)
        self.assertFalse(dialog.busy)

    def test_supplement_lists_clear_placeholders_and_ignore_superseded_loading_results(self):
        with patch("note_organizer.research_ui.background") as background:
            dialog = SupplementsWindow(self.app, "synthetic", self.pc / "paper.pdf")
            initial = list(background.call_args_list)
            self.assertEqual(dialog.tree.status_message, "Checking existing library files…")
            self.assertEqual(dialog.attached.status_message, "Loading attached files…")
            dialog.discover()
            latest = background.call_args
            initial[1].args[2]([])
            self.assertEqual(dialog.tree.status_message, "Finding supplementary files…")
            latest.args[2](([], ([], [], "")))
            initial[0].args[2]([])
            self.assertIsNone(dialog.tree.status_message)
            self.assertIsNone(dialog.attached.status_message)
            dialog.discover()
            background.call_args.args[3](OSError("Synthetic request failure"))
            self.assertIn("failed", dialog.tree.status_message)
            self.assertFalse(dialog.find.instate(["disabled"]))

    def test_filing_recovery_has_a_loading_placeholder_and_a_distinct_error_state(self):
        with patch("note_organizer.ui.background") as background:
            window = self.app.filing_recovery()
        table = next(widget for widget in descendants(window) if isinstance(widget, DataTable))
        self.assertEqual(table.status_message, "Checking interrupted filings…")
        background.call_args.args[2]([])
        self.assertIsNone(table.status_message)
        background.call_args.args[3](OSError("Synthetic unavailable recovery database"))
        self.assertIn("Could not load", table.status_message)


if __name__ == "__main__":
    unittest.main()
