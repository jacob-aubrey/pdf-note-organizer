"""Cleanup needs two deliberate review steps and never works on real libraries."""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from note_organizer.storage_ui import open_cleanup
from note_organizer.theme import apply_theme
from note_organizer.ui import App
from note_organizer.widgets import dismiss_tooltips


class StorageCleanupUITests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        apply_theme(self.root)
        self.errors = []
        self.root.report_callback_exception = lambda *values: self.errors.append(values)
        long_path = "C:\\Synthetic research library\\" + "Long folder name\\" * 10
        self.plans = [{"cloud_id": "ready", "name": "Ready paper", "path": long_path + "Paper [reMarkable 12345678].pdf",
                       "main_path": long_path + "Paper.pdf", "status": "ready", "bytes": 2048, "reasons": [], "proof": "reviewed-proof"},
                      {"cloud_id": "blocked", "name": "Edited paper", "path": long_path + "Other [reMarkable 87654321].pdf",
                       "main_path": long_path + "Other.pdf", "status": "blocked", "bytes": 3072,
                       "reasons": ["The reading copy was changed outside Notable."]}]
        self.planner = patch("note_organizer.storage_ui.plan_legacy_cleanup", return_value=self.plans)
        self.mock_plan = self.planner.start()
        self.app = SimpleNamespace(root=self.root, store=Mock(), workflow_executor=ThreadPoolExecutor(max_workers=1),
            workflow_futures=set(), workflow_results=Queue(), service=Mock(), refresh=Mock())
        self.app.tree = lambda *args, **kwargs: App.tree(self.app, *args, **kwargs)
        self.app.service.storage_action.return_value = [{"cloud_id": "ready", "path": self.plans[0]["path"], "status": "removed", "bytes": 2048}]
        self.window = open_cleanup(self.app)
        self.dialog = self.window.cleanup_dialog
        self.settle()

    def tearDown(self):
        self.app.workflow_executor.shutdown(wait=True, cancel_futures=True)
        dismiss_tooltips()
        self.root.destroy()
        self.planner.stop()
        self.assertFalse(self.errors)

    def settle(self):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            self.root.update()
            while not self.app.workflow_results.empty():
                success, error, future = self.app.workflow_results.get_nowait()
                try:
                    result = future.result()
                except Exception as exc:
                    if error:
                        error(exc)
                    else:
                        raise
                else:
                    success(result)
                self.app.workflow_futures.discard(future)
            if not self.app.workflow_futures:
                self.root.update()
                return
            time.sleep(.005)
        self.fail("Synthetic cleanup action did not finish")

    def select(self, *rows):
        self.dialog.tree.selection_set(rows)
        self.dialog.selected()
        self.root.update_idletasks()

    def test_opening_only_reviews_and_keeps_removal_disabled_by_default(self):
        self.mock_plan.assert_called_once_with(self.app.store)
        self.app.service.storage_action.assert_not_called()
        self.assertFalse(self.dialog.acknowledged.get())
        self.assertTrue(self.dialog.remove_button.instate(["disabled"]))
        self.assertEqual(len(self.dialog.tree.get_children()), 2)
        self.assertIn("2.0 KB", self.dialog.summary.get())

    def test_blocked_rows_can_be_inspected_but_cannot_be_removed(self):
        self.select("1")
        self.dialog.acknowledged.set(True)
        self.dialog.update_controls()
        self.assertTrue(self.dialog.remove_button.instate(["disabled"]))
        self.assertIn(self.plans[1]["path"], self.dialog.details.value)
        self.assertIn("changed outside Notable", self.dialog.details.value)
        self.dialog.review_removal()
        self.assertIsNone(self.dialog.confirmation)
        self.app.service.storage_action.assert_not_called()

    def test_ready_selection_needs_acknowledgment_then_exact_path_confirmation(self):
        self.select("0")
        self.dialog.review_removal()
        self.assertIsNone(self.dialog.confirmation)
        self.dialog.acknowledged.set(True)
        self.dialog.update_controls()
        self.dialog.remove_button.invoke()
        confirmation = self.dialog.confirmation
        self.assertIsNotNone(confirmation)
        self.assertIn(self.plans[0]["path"], confirmation.details.value)
        self.assertIn("2.0 KB", confirmation.details.value)
        self.app.service.storage_action.assert_not_called()
        confirmation.confirm_button.invoke()
        self.settle()
        self.app.service.storage_action.assert_called_once_with("cleanup", [self.plans[0]])
        self.app.refresh.assert_called_once()
        self.assertIn("Removed 1 extra copy", self.dialog.report.value)
        self.assertIn("2.0 KB reclaimed", self.dialog.report.value)
        self.assertFalse(self.dialog.acknowledged.get())

    def test_select_all_skips_blocked_copies_and_mixed_manual_selection_is_disabled(self):
        self.dialog.select_ready.set(True)
        self.dialog.select_all_ready()
        self.assertEqual(self.dialog.tree.selection(), ("0",))
        self.select("0", "1")
        self.dialog.acknowledged.set(True)
        self.dialog.update_controls()
        self.assertEqual(self.dialog.ready_selection(), [])
        self.assertTrue(self.dialog.remove_button.instate(["disabled"]))

    def test_long_paths_have_dynamic_hover_copy_and_wrapped_selectable_details(self):
        self.select("0")
        self.assertEqual(self.dialog.details.selected_path(), self.plans[0]["path"])
        self.assertIn(self.plans[0]["path"], self.dialog.details.path_access.help())
        self.assertEqual(str(self.dialog.details.text.cget("wrap")), "word")
        self.assertEqual(self.dialog.details.path_copy_button.cget("text"), "Copy full path")
        with patch.object(self.dialog.details.path_selector, "clipboard_clear") as cleared, \
                patch.object(self.dialog.details.path_selector, "clipboard_append") as copied:
            self.dialog.details.path_copy_button.invoke()
        cleared.assert_called_once()
        copied.assert_called_once_with(self.plans[0]["path"])

    def test_worker_error_preserves_dialog_and_explains_that_copies_are_retained(self):
        self.mock_plan.side_effect = OSError("Source temporarily unavailable")
        self.dialog.refresh()
        self.settle()
        self.assertIn("remain in place", self.dialog.summary.get())
        self.assertIn("Source temporarily unavailable", self.dialog.report.value)
        self.assertFalse(self.dialog.busy)
        self.app.service.storage_action.assert_not_called()

    def test_resized_dialog_keeps_confirmation_actions_and_full_paths_accessible(self):
        self.root.deiconify()
        self.root.geometry("900x700+10+10")
        self.window.deiconify()
        self.window.geometry("780x600+20+20")
        self.root.update()
        self.select("0")
        self.assertGreaterEqual(self.window.winfo_width(), 740)
        self.assertLessEqual(self.dialog.close_button.winfo_rooty() + self.dialog.close_button.winfo_height(),
                             self.window.winfo_rooty() + self.window.winfo_height())
        self.assertLessEqual(self.dialog.acknowledgment.winfo_rooty() + self.dialog.acknowledgment.winfo_height(),
                             self.window.winfo_rooty() + self.window.winfo_height())
        self.assertEqual(self.dialog.details.selected_path(), self.plans[0]["path"])

    def test_closing_during_read_only_check_is_safe_for_late_callback(self):
        self.dialog.busy = "checking"
        self.dialog.close()
        self.dialog.loaded(self.plans)
        self.assertFalse(self.dialog.alive())
        self.app.service.storage_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
