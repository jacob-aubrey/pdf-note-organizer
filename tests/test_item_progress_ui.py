"""Measured item progress with real searches on disposable PDFs."""
import threading
import unittest
from unittest.mock import patch

import pymupdf

from note_organizer.pdf_worker import _text_pages
from note_organizer.storage import digest_file
from tests import test_ui_audit


class ItemProgressUITests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def tearDown(self):
        test_ui_audit.UIAuditTests.tearDown(self)
        self.assertFalse(self.errors)

    def show_reader(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("940x700+0+0")
        self.app.tabs.select(self.app.notes_tab)
        self.root.deiconify()
        self.root.update()

    def test_actual_pdf_search_advances_once_per_finished_file_and_keeps_layout_compact(self):
        app = self.app
        project = self.store.add_project(self.pc)
        for index in range(3):
            path = self.pc / f"Paper {index}.pdf"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((50, 70), "Gold imaging")
                pdf.save(path)
            self.store.save_scan(project, path, digest_file(path), "sig", "settings", {}, [])
        entered = [threading.Event() for _ in range(3)]
        release = [threading.Event() for _ in range(3)]
        calls = []
        def read(path, digest, cancelled):
            index = len(calls)
            calls.append(path)
            entered[index].set()
            if not release[index].wait(5):
                raise TimeoutError("Test extraction was not released")
            return _text_pages(path, digest)
        self.show_reader()
        with patch.object(app.pdf_worker, "text_pages_cancellable", side_effect=read):
            try:
                app.all_projects.set(True)
                app.search_scope.set("PDFs")
                app.search.set("gold")
                app.refresh_notes()
                for index in range(3):
                    self.pump_until(lambda: entered[index].is_set() and app.note_count.get() == f"{index} / 3 PDFs")
                    self.assertEqual(str(app.search_progress["mode"]), "determinate")
                    self.assertEqual(float(app.search_progress["maximum"]), 3)
                    self.assertEqual(float(app.search_progress["value"]), index)
                    self.assertIn("paper", app.search_progress_help().lower())
                    self.assertNotIn("remaining", app.note_count.get())
                    self.assertLessEqual(app.search_progress.winfo_width(), 80)
                    self.assertGreater(app.search_entry.winfo_width(), 100)
                    before = float(app.search_progress["value"])
                    app.animate_reader_search()
                    self.assertEqual(float(app.search_progress["value"]), before)
                    release[index].set()
                self.pump_until(lambda: not app.reader_search_busy)
                self.assertEqual(app.note_count.get(), "3 results")
                self.assertFalse(app.search_progress.winfo_ismapped())
            finally:
                for event in release:
                    event.set()
                app.query_future.result(timeout=5)

    def test_superseded_query_cannot_replace_current_item_progress(self):
        from concurrent.futures import Future
        app = self.app
        callbacks, futures = [], []
        def submit(*args, **kwargs):
            callbacks.append(kwargs["progress"])
            future = Future()
            futures.append(future)
            return future
        with patch.object(app.query_executor, "submit", side_effect=submit):
            app.search.set("first")
            app.refresh_notes()
            app.search.set("second")
            app.refresh_notes()
        callbacks[-1]({"phase": "Searching PDFs", "unit": "PDFs", "current": 143, "total": 520})
        callbacks[0]({"phase": "Searching PDFs", "unit": "PDFs", "current": 99, "total": 100})
        app.poll()
        self.assertEqual(app.note_count.get(), "143 / 520 PDFs")
        self.assertEqual(float(app.search_progress["maximum"]), 520)
        self.assertEqual(float(app.search_progress["value"]), 143)
        self.show_reader()
        from pathlib import Path
        from tests.reader_app_regression import capture_test_window
        capture_test_window(self.root, Path(__file__).resolve().parents[1] / ".test-tmp/item-progress.png")
        futures[-1].set_result([])
        self.root.update()

    def test_footer_switches_between_item_counts_and_unknown_duration_work(self):
        app = self.app
        app.service.activity_state = {"phase": "Checking local PDFs", "detail": "Paper.pdf", "current": 143, "total": 520}
        app.show_work_progress()
        self.assertEqual(str(app.work_progress["mode"]), "determinate")
        self.assertEqual(float(app.work_progress["maximum"]), 520)
        self.assertEqual(float(app.work_progress["value"]), 143)
        self.assertEqual(app.work_phase.get(), "Checking local PDFs · 143 / 520")
        app.service.activity_state = {"phase": "Checking reMarkable", "detail": "", "current": None, "total": None}
        app.show_work_progress()
        self.assertEqual(str(app.work_progress["mode"]), "indeterminate")
        self.assertTrue(app.work_animating)
        app.service.activity_state = {"phase": "Saving notebooks", "detail": "", "current": 0, "total": 2}
        app.show_work_progress()
        self.assertEqual(str(app.work_progress["mode"]), "determinate")
        self.assertEqual(float(app.work_progress["value"]), 0)
        self.assertFalse(app.work_animating)
        app.service.activity_state = None
        app.show_work_progress()
        self.assertFalse(app.work_visible)


if __name__ == "__main__":
    unittest.main()
