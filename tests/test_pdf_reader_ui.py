"""Reader lifecycle and Tk controls without launching an actual browser."""
from concurrent.futures import Future
from pathlib import Path
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from note_organizer.pdf_reader import PDFReader
from tests import test_ui_audit


class PDFReaderLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.resolver = Mock(side_effect=lambda entry, cancelled: {
            "path": entry["path"], "page": entry["page"], "title": entry["key"], "rect": None})
        self.external, self.expand = Mock(), Mock()
        self.reader = PDFReader(self.root, self.resolver, self.external, self.expand)
        self.reader.pack(fill="both", expand=True)
        self.start_host_patch = patch.object(self.reader, "start_host")
        self.start_host = self.start_host_patch.start()

    def tearDown(self):
        self.reader.close()
        self.reader.executor.shutdown(wait=True, cancel_futures=True)
        self.start_host_patch.stop()
        for pending in self.root.tk.call("after", "info"):
            self.root.after_cancel(pending)
        self.root.destroy()

    def wait(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                self.assertFalse(self.errors)
                return
            time.sleep(.005)
        self.fail("PDF reader action did not settle")

    def show(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("700x500+0+0")
        self.root.deiconify()
        self.root.update()

    @staticmethod
    def entry(key="first", **changes):
        return {"document_id": "paper", "key": key, "kind": "highlight",
                "path": str(Path(key + ".pdf").resolve()), "page": 2, **changes}

    def test_selection_resolves_only_after_reader_is_mapped_and_same_identity_coalesces(self):
        entry = self.entry()
        self.reader.set_entry(entry, ["tantalum"])
        first_generation = self.reader.generation
        self.reader.set_entry(dict(entry), ["tantalum"])
        self.assertEqual(self.reader.generation, first_generation)
        self.assertTrue(self.reader.awaiting_entry)
        self.resolver.assert_not_called()
        self.start_host.assert_not_called()
        self.show()
        self.wait(lambda: self.reader.pending is not None)
        self.resolver.assert_called_once()
        self.assertEqual(self.resolver.call_args.args[0], entry)
        self.assertEqual(self.reader.pending["terms"], ["tantalum"])
        self.assertEqual(self.reader.pending["id"], first_generation)
        self.start_host.assert_called_once()

    def test_title_edit_updates_heading_without_resetting_pdf_or_search(self):
        entry = self.entry(metadata={"title": "Original title"}, search_hits=[{"field":"title", "text":"gold"}])
        self.reader.set_entry(entry, ["gold"])
        self.show()
        self.wait(lambda: self.reader.pending is not None)
        self.reader.loaded = True
        self.reader.state = {"page": 8, "scale": 2, "scrollTop": 890}
        self.reader.match_selection = {"index": 2, "term": "gold"}
        generation, identity = self.reader.generation, self.reader.identity
        cancellation = self.reader.cancelled
        connection = self.reader.connection = Mock()
        renamed = {**entry, "logical_paper_title": "The revised paper title"}
        self.reader.set_entry(renamed, ["gold"])
        connection.send.assert_called_once_with({"command": "title",
            "title": "The revised paper title", "id": generation})
        self.assertEqual(self.reader.pending["title"], "The revised paper title")
        self.assertEqual(self.reader.entry, renamed)
        self.assertEqual(self.reader.generation, generation)
        self.assertEqual(self.reader.identity, identity)
        self.assertTrue(self.reader.loaded)
        self.assertFalse(cancellation.is_set())
        self.assertEqual(self.reader.state, {"page": 8, "scale": 2, "scrollTop": 890})
        self.assertEqual(self.reader.match_selection, {"index": 2, "term": "gold"})
        self.resolver.assert_called_once()
        connection.send.reset_mock()
        self.reader.set_entry(dict(renamed), ["gold"])
        connection.send.assert_not_called()

    def test_title_edit_during_resolution_wins_over_captured_old_metadata(self):
        entered, release = threading.Event(), threading.Event()
        def resolve(entry, cancelled):
            entered.set()
            release.wait(3)
            return {"path": entry["path"], "page": entry["page"],
                    "title": entry["metadata"]["title"], "rect": None}
        self.resolver.side_effect = resolve
        entry = self.entry(metadata={"title": "Original title"}, search_hits=[{"field":"title", "text":"gold"}])
        self.show()
        try:
            self.reader.set_entry(entry)
            self.assertTrue(entered.wait(1))
            generation = self.reader.generation
            current_hits = [{"field":"quote", "text":"gold"}]
            self.reader.set_entry({**entry, "metadata": {"title": "Latest title"}, "search_hits": current_hits})
            release.set()
            self.wait(lambda: self.reader.pending is not None)
            self.assertEqual(self.reader.pending["title"], "Latest title")
            self.assertEqual(self.reader.pending["mainHits"], current_hits)
            self.assertEqual(self.reader.generation, generation)
            self.resolver.assert_called_once()
        finally:
            release.set()

    def test_slow_stale_resolution_cannot_open_the_previously_selected_pdf(self):
        entered, release = threading.Event(), threading.Event()
        cancellation = []
        def resolve(entry, cancelled):
            if entry["key"] == "first":
                entered.set()
                release.wait(3)
                cancellation.append(cancelled())
            return {"path": entry["path"], "page": entry["page"], "title": entry["key"], "rect": None}
        self.resolver.side_effect = resolve
        self.show()
        try:
            self.reader.set_entry(self.entry("first"))
            self.assertTrue(entered.wait(1))
            self.reader.set_entry(self.entry("second", page=7))
            heartbeat = []
            self.root.after(0, lambda: heartbeat.append(True))
            self.root.update()
            self.assertTrue(heartbeat)
            release.set()
            self.wait(lambda: self.reader.pending is not None and self.reader.pending["title"] == "second")
            self.assertEqual(cancellation, [True])
            self.assertEqual(self.reader.pending["page"], 7)
            self.start_host.assert_called_once()
        finally:
            release.set()

    def test_clear_cancels_pending_resolution_and_revokes_the_displayed_document(self):
        self.reader.set_entry(self.entry())
        cancellation = self.reader.cancelled
        connection = self.reader.connection = Mock()
        self.reader.set_entry(None)
        self.assertTrue(cancellation.is_set())
        self.assertIsNone(self.reader.entry)
        self.assertIsNone(self.reader.pending)
        self.assertFalse(self.reader.awaiting_entry)
        self.assertFalse(self.reader.loaded)
        sent = connection.send.call_args.args[0]
        self.assertEqual(sent["command"], "clear")
        self.assertEqual(sent["id"], self.reader.generation)

    def test_resolver_error_offers_retry_and_keeps_external_action_available(self):
        self.resolver.side_effect = FileNotFoundError("Locate this PDF in Library")
        self.reader.set_entry(self.entry())
        self.show()
        self.wait(lambda: "Locate this PDF" in self.reader.message.get())
        self.assertEqual(self.reader.retry.winfo_manager(), "pack")
        self.assertFalse(self.reader.loaded)
        self.start_host.assert_not_called()
        self.reader.handle_event({"kind": "external", "id": self.reader.generation})
        self.external.assert_called_once()
        old_generation = self.reader.generation
        self.resolver.side_effect = lambda entry, cancelled: {
            "path": entry["path"], "page": entry["page"], "title": entry["key"], "rect": None}
        self.reader.retry.invoke()
        self.wait(lambda: self.reader.pending is not None)
        self.assertGreater(self.reader.generation, old_generation)
        self.assertEqual(self.resolver.call_count, 2)
        self.start_host.assert_called_once()

    def test_stale_host_events_cannot_replace_current_state_or_surface_old_errors(self):
        self.reader.set_entry(self.entry("first"))
        old_generation = self.reader.generation
        self.reader.set_entry(self.entry("second"))
        self.reader.handle_event({"kind": "state", "id": old_generation, "loaded": True})
        self.reader.handle_event({"kind": "error", "id": old_generation, "message": "Old paper failed"})
        self.assertFalse(self.reader.loaded)
        self.assertNotIn("Old paper", self.reader.message.get())
        self.reader.handle_event({"kind": "state", "id": self.reader.generation, "loaded": True, "page": 2})
        self.assertTrue(self.reader.loaded)
        self.assertEqual(self.reader.state["page"], 2)

    def test_match_navigation_uses_loaded_reader_and_changed_scan_reloads_selection(self):
        entry = self.entry(source_digest="old", source_note_revision=1)
        self.reader.set_entry(entry)
        connection = self.reader.connection = Mock()
        self.reader.select_match(3)
        connection.send.assert_not_called()
        self.reader.loaded = True
        self.reader.select_match(3)
        connection.send.assert_called_once_with({"command": "match", "index": 3})
        generation = self.reader.generation
        self.reader.set_entry({**entry, "source_digest": "new", "source_note_revision": 2})
        self.assertGreater(self.reader.generation, generation)
        self.assertFalse(self.reader.loaded)

    def test_requested_hit_is_sent_with_open_without_waiting_for_loaded_event(self):
        self.reader.set_entry(self.entry())
        requested = {"index": 2, "term": "gold", "fitWidth": True}
        self.reader.select_match(requested)
        self.show()
        self.wait(lambda: self.reader.pending is not None)
        self.assertEqual(self.reader.pending["match"], requested)
        self.assertIsNone(self.reader.pending_match)
        self.reader.connection = connection = Mock()
        self.reader.handle_event({"kind": "state", "id": self.reader.generation, "loaded": True})
        connection.send.assert_not_called()

    def test_close_is_idempotent_and_cancels_all_scheduled_reader_work(self):
        self.reader.set_entry(self.entry())
        cancelled = self.reader.cancelled
        self.reader.close()
        self.reader.close()
        self.assertTrue(self.reader.closed)
        self.assertTrue(cancelled.is_set())
        self.assertIsNone(self.reader.poll_after)
        self.assertIsNone(self.reader.process)

    def test_retry_preserves_current_occurrence_but_another_result_clears_it(self):
        self.reader.set_entry(self.entry())
        selection = {"index": 2, "term": "gold", "context": "Third gold occurrence"}
        self.reader.loaded = True
        with patch.object(self.reader, "send"):
            self.reader.select_match(selection)
            self.reader.reload()
        self.assertEqual(self.reader.pending_match, selection)
        self.assertEqual(self.reader.match_selection, selection)
        self.reader.set_entry(self.entry("second"))
        self.assertIsNone(self.reader.pending_match)
        self.assertIsNone(self.reader.match_selection)

    def test_layout_warning_keeps_the_loaded_pdf_visible(self):
        self.reader.set_entry(self.entry())
        self.reader.loaded = True
        self.reader.native = Mock()
        with self.assertLogs(level="WARNING"):
            self.reader.handle_event({"kind": "warning", "id": self.reader.generation,
                "message": "ResizeObserver loop completed with undelivered notifications."})
        self.assertTrue(self.reader.loaded)
        self.reader.native.show.assert_not_called()
        self.assertIn("ResizeObserver", self.reader.last_warning)


class PDFReaderAppControlsTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = test_ui_audit.UIAuditTests.tearDown
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def selection(self):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        rows = [{"document_id": "paper", "key": f"note-{page}", "kind": "highlight",
                 "path": str(self.pc / "paper.pdf"), "page": page,
                 "rect": [10, 20, 80, 40], "quote": f"Selected note page {page}"} for page in (1, 2)]
        future = Future()
        future.set_result(rows)
        app.finish_query(app.query_generation, None, future)
        self.root.attributes("-alpha", 0)
        self.root.geometry("1100x760+0+0")
        app.tabs.select(app.notes_tab)
        self.root.deiconify()
        self.root.update()
        return app

    def test_note_details_expand_and_collapse_without_changing_reader_selection(self):
        app = self.selection()
        selected = app.notes.selection()
        identity = app.pdf_reader.identity
        generation = app.pdf_reader.generation
        self.assertFalse(app.note_details.winfo_ismapped())
        app.show_details.set(True)
        app.toggle_note_details()
        self.root.update()
        self.assertTrue(app.note_details.winfo_ismapped())
        self.assertIn("Selected note page", app.preview_text.get("1.0", "end"))
        app.show_details.set(False)
        app.toggle_note_details()
        self.root.update()
        self.assertFalse(app.note_details.winfo_ismapped())
        self.assertEqual(app.notes.selection(), selected)
        self.assertEqual(app.pdf_reader.identity, identity)
        self.assertEqual(app.pdf_reader.generation, generation)

    def test_expand_restore_keeps_result_selection_reader_identity_and_split(self):
        app = self.selection()
        app.notes.selection_set("1")
        self.root.update()
        selected, identity = app.notes.selection(), app.pdf_reader.identity
        app.reader_pane.sashpos(0, 350)
        split = app.reader_pane.sashpos(0)
        app.toggle_reader_expanded()
        self.root.update()
        self.assertTrue(app.reader_expanded)
        self.assertEqual(len(app.reader_pane.panes()), 1)
        self.assertEqual(app.reader_expand_button.cget("text"), "Exit reading mode")
        app.toggle_reader_expanded()
        self.root.update()
        self.assertFalse(app.reader_expanded)
        self.assertEqual(len(app.reader_pane.panes()), 2)
        self.assertEqual(app.reader_expand_button.cget("text"), "Reading mode")
        self.assertLessEqual(abs(app.reader_pane.sashpos(0) - split), 2)
        self.assertEqual(app.notes.selection(), selected)
        self.assertEqual(app.pdf_reader.identity, identity)

    def test_expansion_adds_vertical_space_and_restores_filters_and_note_details(self):
        app = self.selection()
        app.show_details.set(True)
        app.toggle_note_details()
        self.root.update()
        original_height = app.reader_views.winfo_height()
        original_query, original_scope = app.search.get(), app.search_scope.get()
        app.toggle_reader_expanded()
        self.root.update()
        self.assertFalse(app.reader_controls.winfo_ismapped())
        self.assertFalse(app.note_details.winfo_ismapped())
        self.assertGreater(app.reader_views.winfo_height(), original_height + 100)
        app.toggle_reader_expanded()
        self.root.update()
        self.assertTrue(app.reader_controls.winfo_ismapped())
        self.assertTrue(app.note_details.winfo_ismapped())
        self.assertTrue(app.show_details.get())
        self.assertEqual(app.search.get(), original_query)
        self.assertEqual(app.search_scope.get(), original_scope)
        self.assertLessEqual(abs(app.reader_views.winfo_height() - original_height), 2)

    def test_search_placeholder_tracks_scope_without_adding_search_terms(self):
        app = self.selection()
        field = app.search_entry.placeholder
        app.search.set("")
        for scope, hint in (("Notes", "Search notes…"), ("PDFs", "Search PDF text…"),
                            ("All", "Search notes and PDF text…")):
            app.search_scope.set(scope)
            self.assertEqual(field.label.cget("text"), hint)
            self.assertEqual(app.search.get(), "")

    def test_reader_startup_error_keeps_original_pdf_external_button_available(self):
        app = self.selection()
        app.pdf_reader.handle_event({"kind": "error", "id": app.pdf_reader.generation,
                                     "message": "WebView2 Runtime is unavailable"})
        self.assertIn("WebView2", app.pdf_reader.message.get())
        self.assertFalse(app.source_button.instate(["disabled"]))
        self.assertEqual(app.source_button.cget("text"), "Open externally")
        with patch("note_organizer.ui.open_pdf_page", return_value=("Opened default viewer", True)) as opened:
            app.source_button.invoke()
        opened.assert_called_once_with(str(self.pc / "paper.pdf"), app.selected_entry()["page"], {"viewer": "system"})


if __name__ == "__main__":
    unittest.main()
