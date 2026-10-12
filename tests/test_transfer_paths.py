"""Transfer locations remain readable using disposable libraries and Tk windows."""
from tkinter import ttk
import unittest
from unittest.mock import patch

from note_organizer.widgets import SelectionDetails
from tests import test_ui_audit
from tests.test_preferences_ui import descendants


class TransferPathTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp

    def tearDown(self):
        self.app.preview_cancel.set()
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        test_ui_audit.UIAuditTests.tearDown(self)

    def jobs(self):
        return [{"id": state, "path": str(self.pc / ("Long research folder " * 12) / f"{state} paper.pdf"),
                 "state": state, "reason": "Explanation line\n" * 35,
                 "pc_root": str(self.pc), "folder_id": "matched", "source_folder_id": "literature"}
                for state in ("sent", "cancelled")]

    def queue(self, jobs):
        self.app.view.preferences["remarkable_outbox"] = jobs
        callbacks = []
        original_after = self.root.after
        def after(delay, callback=None, *args):
            if delay == 1500:
                callbacks.append(callback)
            return original_after(delay, callback, *args)
        with patch.object(self.root, "after", side_effect=after):
            window = self.app.transfers()
        window.attributes("-alpha", 0)
        window.withdraw()
        widgets = list(descendants(window))
        table = next(widget for widget in widgets if isinstance(widget, ttk.Treeview))
        details = next(widget for widget in widgets if isinstance(widget, SelectionDetails))
        return window, table, details, callbacks[0]

    def select(self, table, item):
        table.selection_set(item)
        table.event_generate("<<TreeviewSelect>>")
        self.root.update()
        self.assertFalse(self.errors)

    def test_completed_and_cancelled_transfers_expose_and_copy_complete_paths(self):
        jobs = self.jobs()
        with patch.object(self.app, "open_path") as opened, patch.object(self.app.service, "command") as command:
            window, table, details, _ = self.queue(jobs)
            for job in jobs:
                self.select(table, job["id"])
                text = details.text.get("1.0", "end-1c")
                self.assertIn(job["path"], text)
                self.assertIn(f"Status: {job['state']}", text)
                self.assertIn("Tablet destination when queued: /Literature/Matched", text)
                self.assertIn("Tablet library when queued: /Literature", text)
                self.assertIn(f"PC library when queued: {self.pc}", text)
                with patch.object(details, "clipboard_clear") as clear, patch.object(details, "clipboard_append") as copied:
                    details.copy_button.invoke()
                clear.assert_called_once()
                copied.assert_called_once_with(text)
            opened.assert_not_called()
            command.assert_not_called()
            window.destroy()

    def test_periodic_refresh_preserves_reading_position_and_updates_selected_path(self):
        jobs = self.jobs()
        window, table, details, refresh = self.queue(jobs)
        window.deiconify()
        self.root.update()
        self.select(table, "sent")
        details.text.yview_moveto(.5)
        self.root.update_idletasks()
        position = details.text.yview()[0]
        bookmark = details.text.index("@0,0")
        self.assertGreater(position, 0)
        with patch.object(details, "set", wraps=details.set) as changed:
            refresh()
            self.root.update()
            changed.assert_not_called()
        self.assertAlmostEqual(details.text.yview()[0], position, places=2)
        jobs[0]["path"] = str(self.pc / ("Renamed research folder " * 12) / "new complete path.pdf")
        refresh()
        self.root.update()
        self.assertIn(jobs[0]["path"], details.text.get("1.0", "end-1c"))
        self.assertEqual(table.selection(), ("sent",))
        self.assertEqual(details.text.index("@0,0"), bookmark)
        self.select(table, "cancelled")
        self.assertIn(jobs[1]["path"], details.value)
        self.app.view.preferences["remarkable_outbox"] = []
        refresh()
        self.root.update()
        self.assertEqual(details.value, "")
        self.assertTrue(details.copy_button.instate(["disabled"]))
        window.destroy()

    def test_details_and_actions_fit_smaller_window_at_larger_display_scale(self):
        scale = self.root.tk.call("tk", "scaling")
        self.root.tk.call("tk", "scaling", 2.0)
        try:
            window, table, details, _ = self.queue(self.jobs())
            window.geometry("850x550")
            window.deiconify()
            self.root.update()
            self.select(table, "sent")
            self.assertGreater(table.winfo_height(), 60)
            for button in (widget for widget in descendants(window) if isinstance(widget, ttk.Button)):
                self.assertGreater(button.winfo_width(), 1)
                self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                     window.winfo_rootx() + window.winfo_width() + 2)
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                     window.winfo_rooty() + window.winfo_height() + 2)
            self.assertGreater(details.text.winfo_height(), 20)
            window.destroy()
        finally:
            self.root.tk.call("tk", "scaling", scale)


if __name__ == "__main__":
    unittest.main()
