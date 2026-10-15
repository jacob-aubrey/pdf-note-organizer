"""Library search controls stay usable while asynchronous queries change state."""
from concurrent.futures import Future
import unittest
from unittest.mock import patch

from tests import test_review_controls


class SearchScopeStateTests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait

    def assert_search_available(self):
        self.assertTrue(self.app.search_scope_control.instate(["readonly", "!disabled"]))
        self.assertTrue(self.app.search_entry.instate(["!disabled", "!readonly"]))

    def select_scope(self, value):
        """Use Tk's actual selection binding without moving desktop focus."""
        control = self.app.search_scope_control
        index = tuple(control.cget("values")).index(value)
        self.root.tk.call("ttk::combobox::SelectEntry", str(control), index)
        self.assertEqual(self.app.search_scope.get(), value)
        self.assert_search_available()

    def test_startup_unlock_restores_scope_as_readonly(self):
        self.assertTrue(self.app.library_loaded)
        self.assertEqual(self.app.initial_controls, [])
        self.assert_search_available()
        for scope, expected in (("PDFs", "0 PDFs"), ("All", "0 items"), ("Notes", "0 notes")):
            self.select_scope(scope)
            self.wait(lambda: self.app.note_count.get() == expected)
            self.assert_search_available()

    def test_pending_search_does_not_lock_scope_or_query_and_stale_reply_is_ignored(self):
        app = self.app
        pending = []

        def submit(*args, **kwargs):
            future = Future()
            future.set_running_or_notify_cancel()
            pending.append((future, args[3], kwargs["query"]))
            return future

        with patch.object(app.query_executor, "submit", side_effect=submit):
            self.select_scope("PDFs")
            self.assertEqual(app.note_count.get(), "Loading results…")
            self.assertTrue(app.reader_search_busy)
            app.search_entry.insert(0, "iodine")
            app.refresh_notes()
            self.assertEqual(app.note_count.get(), "Searching PDFs…")
            self.select_scope("Notes")
            self.assertEqual(pending[-1][1:], ("Notes", "iodine"))
            self.assert_search_available()
            generation = app.query_generation
            pending[0][0].set_result([])
            self.root.update()
            app.poll()
            self.assertEqual(app.query_generation, generation)
            self.assertEqual(app.note_count.get(), "Searching notes…")
            self.assertTrue(app.reader_search_busy)
            self.assertEqual(app.search_scope.get(), "Notes")
            pending[-1][0].set_result([])
            self.wait(lambda: app.note_count.get() == "0 notes")
            for future, _, _ in pending:
                if not future.done():
                    future.set_result([])
        self.assert_search_available()

    def test_invalid_boolean_query_can_be_cleared_or_changed_in_each_scope(self):
        app = self.app
        for scope in ("Notes", "PDFs", "All"):
            with self.subTest(scope=scope):
                self.select_scope(scope)
                app.search_entry.delete(0, "end")
                app.search_entry.insert(0, "iodine AND (")
                app.refresh_notes()
                self.wait(lambda: app.note_count.get() == "Check search")
                self.assertTrue(app.search_error.get())
                self.assert_search_available()
                app.clear_search()
                expected = {"Notes": "0 notes", "PDFs": "0 PDFs", "All": "0 items"}[scope]
                self.wait(lambda: app.note_count.get() == expected and not app.search_error.get())
                self.assertEqual(app.search_scope.get(), scope)
                self.assert_search_available()

    def test_query_failure_leaves_controls_available_for_recovery(self):
        app = self.app
        failed = Future()
        failed.set_exception(OSError("Temporary library read failure"))
        with patch.object(app.query_executor, "submit", return_value=failed):
            self.select_scope("PDFs")
            self.wait(lambda: app.note_count.get() == "Could not load notes")
        self.assert_search_available()
        self.select_scope("All")
        self.wait(lambda: app.note_count.get() == "0 items")
        self.assert_search_available()

    def test_tab_switch_and_pdf_reader_events_do_not_disable_library_search(self):
        app = self.app
        self.select_scope("PDFs")
        self.wait(lambda: app.note_count.get() == "0 PDFs")
        for event in ({"kind": "state", "loaded": False},
                      {"kind": "error", "message": "Reader unavailable"},
                      {"kind": "state", "loaded": True, "page": 1}):
            with self.subTest(event=event):
                app.pdf_reader.handle_event({**event, "id": app.pdf_reader.generation})
                app.tabs.select(app.library_tab)
                self.root.update()
                app.tabs.select(app.notes_tab)
                self.root.update()
                self.assert_search_available()
        self.select_scope("Notes")
        self.wait(lambda: app.note_count.get() == "0 notes")


if __name__ == "__main__":
    unittest.main()
