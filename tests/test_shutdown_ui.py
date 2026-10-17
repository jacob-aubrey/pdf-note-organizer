"""Safe close blocks app input while keeping progress and cleanup responsive."""
import threading
import time
import tkinter as tk
from unittest.mock import patch
import unittest

from note_organizer.shutdown import ShutdownTasks
from tests import test_ui_audit


class ShutdownUITests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def tearDown(self):
        for release in getattr(self, "releases", []):
            release.set()
        if hasattr(self.app, "shutdown_tasks"):
            self.app.shutdown_tasks.thread.join(5)
            self.root.update()
        if getattr(self.app, "shutdown_dialog", None) and self.app.shutdown_dialog.window.winfo_exists():
            self.app.shutdown_dialog.destroy()
        if hasattr(self, "destroy_patch"):
            self.destroy_patch.stop()
        test_ui_audit.UIAuditTests.tearDown(self)

    def show(self):
        native = getattr(self, "enable_pdf_reader", False)
        if native:
            from tests.reader_app_regression import require_private_desktop
            require_private_desktop()
        self.root.attributes("-alpha", 1 if native else 0)
        width = min(1100, self.root.winfo_screenwidth() - 32) if native else 1100
        height = min(760, self.root.winfo_screenheight() - 80) if native else 760
        self.root.geometry(f"{width}x{height}+0+0")
        self.root.deiconify()
        self.root.update()
        self.releases = []
        self.destroy_patch = patch.object(self.root, "destroy")
        self.destroy = self.destroy_patch.start()

    def held_task(self, executor):
        entered, release = threading.Event(), threading.Event()
        self.releases.append(release)
        def run():
            entered.set()
            release.wait(10)
        future = executor.submit(run)
        self.assertTrue(entered.wait(1))
        return future, release

    def test_modal_blocks_all_windows_and_tracks_actual_shutdown_stages(self):
        self.show()
        extra = tk.Toplevel(self.root)
        extra.geometry("300x200+0+0")
        self.root.update()
        future, release_workflow = self.held_task(self.app.workflow_executor)
        future.shutdown_label = "Saving annotated PDF: Paper.pdf"
        self.app.workflow_futures.add(future)
        release_service, release_reader = threading.Event(), threading.Event()
        self.releases.extend([release_service, release_reader])
        self.app.service.thread = threading.Thread(target=release_service.wait, daemon=True)
        self.app.service.thread.start()
        self.app.service.activity_state = {"phase": "Saving notebook", "detail": "Paper notes.docx", "current": 1, "total": 2}
        with patch.object(self.app.pdf_reader, "wait_closed", side_effect=lambda: release_reader.wait(10)):
            started = time.monotonic()
            self.app.close()
            self.assertLess(time.monotonic() - started, .5)
            dialog = self.app.shutdown_dialog
            self.root.update()
            self.assertEqual(self.root.grab_current(), dialog.window)
            if self.root.tk.call("tk", "windowingsystem") == "win32":
                self.assertTrue(self.root.attributes("-disabled"))
                self.assertTrue(extra.attributes("-disabled"))
            self.pump_until(lambda: "Paper notes.docx" in dialog.detail.get())
            self.assertIn("1/2", dialog.detail.get())
            from pathlib import Path
            from tests.reader_app_regression import capture_test_window
            capture_test_window(dialog.window, Path(__file__).resolve().parents[1] / ".test-tmp/shutdown-dialog.png")
            x = dialog.window.winfo_rootx() + dialog.window.winfo_width() / 2
            y = dialog.window.winfo_rooty() + dialog.window.winfo_height() / 2
            self.assertLess(abs(x - (self.root.winfo_rootx() + self.root.winfo_width() / 2)), 3)
            self.assertLess(abs(y - (self.root.winfo_rooty() + self.root.winfo_height() / 2)), 3)
            heartbeat = []
            self.root.after(0, lambda: heartbeat.append(True))
            self.root.update()
            self.assertTrue(heartbeat)
            before = float(dialog.progress["value"])
            self.pump_until(lambda: float(dialog.progress["value"]) != before)
            self.app.close()
            self.assertIs(self.app.shutdown_dialog, dialog)
            self.root.tk.call(dialog.window.protocol("WM_DELETE_WINDOW"))
            dialog.window.event_generate("<Escape>")
            self.root.update()
            self.assertTrue(dialog.window.winfo_exists())
            self.destroy.assert_not_called()
            self.app.service.activity_state = {"phase": "Stopping folder watching", "detail": ""}
            self.pump_until(lambda: "Stopping folder watching" in dialog.detail.get())
            release_service.set()
            self.pump_until(lambda: "Saving annotated PDF: Paper.pdf" in dialog.detail.get())
            release_workflow.set()
            self.pump_until(lambda: "embedded PDF reader" in dialog.detail.get())
            self.destroy.assert_not_called()
            release_reader.set()
            self.pump_until(lambda: self.destroy.called)
            self.destroy.assert_called_once()
            self.assertFalse(dialog.window.winfo_exists())
            self.assertIsNone(self.root.grab_current())

    def test_slow_search_keeps_dialog_open_until_its_worker_exits(self):
        self.show()
        future, release = self.held_task(self.app.query_executor)
        self.app.query_future = future
        self.app.close()
        self.pump_until(lambda: "current note/PDF search" in self.app.shutdown_dialog.detail.get())
        self.destroy.assert_not_called()
        release.set()
        self.pump_until(lambda: self.destroy.called)
        self.assertTrue(future.done())

    def test_queued_search_is_cancelled_before_executors_stop(self):
        self.show()
        future, release = self.held_task(self.app.workflow_executor)
        self.app.workflow_futures.add(future)
        with patch.object(self.app, "refresh_notes") as search:
            self.app.search_after = self.root.after(0, self.app.refresh_notes)
            self.app.close()
            self.root.update()
            search.assert_not_called()
        self.assertIsNone(self.app.search_after)
        release.set()
        self.pump_until(lambda: self.destroy.called)


class ShutdownTasksTests(unittest.TestCase):
    def test_waits_happen_off_calling_thread_and_finish_in_order(self):
        release, entered = threading.Event(), threading.Event()
        calls = []
        caller = threading.get_ident()
        def hold():
            calls.append(("first", threading.get_ident()))
            entered.set()
            release.wait(3)
        tasks = ShutdownTasks([("first", "Saving preferences", hold),
                               ("second", "Closing reader", lambda: calls.append(("second", threading.get_ident())))])
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(tasks.finished.is_set())
            self.assertEqual(tasks.stage, ("first", "Saving preferences"))
        finally:
            release.set()
            tasks.thread.join(3)
        self.assertTrue(tasks.finished.is_set())
        self.assertEqual([call[0] for call in calls], ["first", "second"])
        self.assertTrue(all(call[1] != caller for call in calls))


class NativeShutdownUITests(unittest.TestCase):
    enable_pdf_reader = True
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = ShutdownUITests.tearDown
    show = ShutdownUITests.show
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def test_actual_embedded_reader_exits_before_dialog_closes(self):
        import pymupdf
        source = self.folder / "shutdown-reader.pdf"
        with pymupdf.open() as document:
            document.new_page().insert_text((50, 80), "Native reader shutdown test")
            document.save(source)
        self.show()
        self.app.tabs.select(self.app.notes_tab)
        self.app.reader_views.select(self.app.pdf_reader)
        self.root.update()
        self.app.pdf_reader.set_entry({"document_id": "shutdown-test", "key": "pdf:1", "kind": "pdf",
                                       "path": str(source), "page": 1, "metadata": {"title": "Shutdown test"}})
        self.pump_until(lambda: self.app.pdf_reader.loaded, timeout=25)
        self.assertIsNotNone(self.app.pdf_reader.native)
        self.app.close()
        self.pump_until(lambda: self.destroy.called, timeout=20)
        self.assertEqual(self.app.pdf_reader.last_exitcode, 0)
        self.assertTrue(all(not reaper.is_alive() for reaper in self.app.pdf_reader.reapers))
        self.assertTrue(self.app.shutdown_tasks.finished.is_set())


if __name__ == "__main__":
    unittest.main()
