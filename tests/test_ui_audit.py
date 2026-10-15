"""Routing clarity and responsiveness, using only disposable synthetic data."""
from concurrent.futures import Future
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from note_organizer.service import Service
from note_organizer.storage import Store
from note_organizer.ui import App
from note_organizer.widgets import Tooltip
from note_organizer.remarkable_sync import default_config
from tests.ui_helpers import settle_library


class UIAuditTests(unittest.TestCase):
    def setUp(self):
        # Most UI tests use synthetic note records and exercise Tk controls.
        # The dedicated reader integration checks opt into the native runtime.
        if not getattr(self, "enable_pdf_reader", False):
            self.reader_load_patch = patch("note_organizer.pdf_reader.PDFReader.load_entry")
            self.reader_load_mock = self.reader_load_patch.start()
            self.addCleanup(self.reader_load_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.pc = self.folder / "Sorted"
        self.pc.mkdir()
        (self.pc / "Matched").mkdir()
        self.store = Store(self.folder / "data" / "library.sqlite3")
        self.config = {**default_config(self.store.path.parent), "integration_enabled": True, "pc_root": str(self.pc), "source_folder_id": "literature"}
        self.store.set_preference("remarkable", self.config)
        self.catalog = [
            {"id": "literature", "path": "/Literature", "name": "Literature", "ancestor_ids": [], "parent": ""},
            {"id": "matched", "path": "/Literature/Matched", "name": "Matched", "ancestor_ids": ["literature"], "parent": "literature"},
            {"id": "missing", "path": "/Literature/Missing", "name": "Missing", "ancestor_ids": ["literature"], "parent": "literature"},
            {"id": "bible", "path": "/Bible Notes", "name": "Bible Notes", "ancestor_ids": [], "parent": ""},
        ]
        self.store.set_preference("remarkable_folders", self.catalog)
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        with patch.object(Service, "start"):
            self.app = App(self.root, self.store, self.store.path.parent)
            settle_library(self.app, self.root)
        self.root.update()

    def tearDown(self):
        self.app.pdf_reader.close()
        self.app.closing = True
        self.app.inbox.stop()
        self.app.workflow_executor.shutdown(wait=True, cancel_futures=True)
        self.app.service.stop()
        self.app.pdf_worker.shutdown(wait=True)
        self.app.query_cancel.set()
        self.app.query_executor.shutdown(wait=True, cancel_futures=True)
        for pending in self.root.tk.call("after", "info"):
            self.root.after_cancel(pending)
        self.root.destroy()
        self.temp.cleanup()

    def pump_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.005)
        self.assertTrue(predicate())
        self.assertFalse(self.errors)

    def test_folder_table_shows_only_source_with_actual_destination(self):
        app = self.app
        self.assertEqual(set(app.cloud_folders.get_children()), {"literature", "matched", "missing"})
        self.assertIn("bible", app.cloud_scope_ids)
        self.assertEqual(app.cloud_folders.item("matched", "values")[1], str((self.pc / "Matched").resolve()))
        self.assertEqual(app.cloud_folders.item("missing", "values")[1], "Needs mapping")
        self.assertIn("No PDFs have been checked", app.cloud_review_empty.get())
        self.assertTrue(app.cloud_map_button.instate(["disabled"]))
        self.assertTrue(app.cloud_open_button.instate(["disabled"]))
        self.assertTrue(app.cloud_folders.cget("xscrollcommand"))

    def test_unsaved_source_survives_refresh_and_manual_sync_applies_it(self):
        app = self.app
        app.cloud_scope.current(0)
        app.refresh_cloud()
        self.assertEqual(app.cloud_routing_values()[0], "")
        self.assertIn("Unsaved", app.cloud_apply_status.get())
        app.cloud_scope.current(app.cloud_scope_ids.index("bible"))
        app.sync_cloud_now()
        name, args = app.service.commands.get_nowait()
        self.assertEqual(name, "remarkable_settings")
        self.assertEqual(args[0]["source_folder_id"], "bible")
        self.assertEqual(app.service.commands.get_nowait()[0], "remarkable_sync")

    def test_automatic_checkbox_applies_independently_and_reports_pending(self):
        app = self.app
        app.service.remarkable.vault.path.parent.mkdir(parents=True, exist_ok=True)
        app.service.remarkable.vault.path.touch()
        app.refresh()
        settle_library(app, self.root)
        app.cloud_enabled.set(True)
        app.toggle_cloud_sync()
        name, args = app.service.commands.get_nowait()
        self.assertEqual((name, args), ("remarkable_settings", ({"enabled": True},)))
        self.assertIn("Applying", app.cloud_status.get())
        self.store.set_preference("remarkable", {**self.config, "enabled": True})
        app.refresh()
        settle_library(app, self.root)
        app.refresh_cloud_status()
        self.assertIn("Automatic checks on", app.cloud_status.get())
        self.assertNotIn("Applying", app.cloud_status.get())
        self.assertTrue(app.cloud_enabled.get())

    def test_mapping_source_updates_visible_pc_counterpart(self):
        alternate = self.folder / "Alternate"
        alternate.mkdir()
        with patch("note_organizer.ui.filedialog.askdirectory", return_value=str(alternate)):
            self.app.set_cloud_mapping("literature")
        self.assertEqual(self.app.cloud_pc_root.get(), str(alternate.resolve()))
        name, args = self.app.service.commands.get_nowait()
        self.assertEqual(name, "remarkable_settings")
        self.assertEqual(args[0]["pc_root"], str(alternate.resolve()))
        self.assertEqual(self.app.service.commands.get_nowait(), ("remarkable_map", ("literature", None)))

    def test_cloud_controls_fit_minimum_window(self):
        self.root.geometry("940x620")
        self.app.tabs.select(self.app.remarkable_tab)
        self.root.deiconify()
        self.root.update()
        tab = self.app.remarkable_tab
        for widget in (self.app.cloud_scope, self.app.cloud_map_button, self.app.cloud_open_button,
                       self.app.cloud_review_map_button, self.app.cloud_sync_button):
            right = widget.winfo_rootx() + widget.winfo_width()
            self.assertLessEqual(right, tab.winfo_rootx() + tab.winfo_width() + 2)
        self.assertGreater(self.app.cloud_review.winfo_height(), 30)
        self.root.withdraw()

    def test_slow_query_does_not_block_tk_and_stale_result_cannot_replace_search(self):
        app = self.app
        entered, release = threading.Event(), threading.Event()
        calls = []
        def slow_entries(**options):
            calls.append(options["query"])
            entered.set()
            release.wait(2)
            if options["cancelled"]():
                raise InterruptedError()
            return []
        with patch.object(self.store, "entries", side_effect=slow_entries):
            app.search.set("old")
            started = time.monotonic()
            app.refresh_notes()
            self.assertLess(time.monotonic() - started, .2)
            self.assertTrue(entered.wait(1))
            heartbeat = []
            self.root.after(0, lambda: heartbeat.append(True))
            self.root.update()
            self.assertTrue(heartbeat)
            app.search.set("new")
            app.refresh_notes()
            release.set()
            self.pump_until(lambda: app.note_count.get() == "0 notes")
            self.assertEqual(calls[-1], "new")

    def test_batched_rows_keep_selection_made_during_load(self):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        future = Future()
        rows = [{"document_id": "doc", "key": str(i), "path": str(self.pc / "paper.pdf"),
                 "kind": "highlight", "quote": f"Passage {i}", "label": "2", "page": 2}
                for i in range(350)]
        future.set_result(rows)
        app.finish_query(app.query_generation, None, future)
        self.assertEqual(len(app.notes.get_children()), 100)
        app.notes.selection_set("50")
        self.pump_until(lambda: len(app.notes.get_children()) == 350)
        self.assertEqual(app.notes.selection(), ("50",))
        self.assertIsNone(app.image)
        self.assertTrue(app.source_button.instate(["!disabled"]))

    def test_background_burst_refreshes_once_and_repeated_sync_is_coalesced(self):
        app = self.app
        app.next_refresh = 0
        for i in range(50):
            app.service.post(f"Imported {i}", True)
        with patch.object(app, "refresh") as refresh:
            app.poll()
            app.service.post("Another import", True)
            app.poll()
            self.assertEqual(refresh.call_count, 1)
        for _ in range(20):
            app.service.command("remarkable_sync")
        self.assertEqual(app.service.commands.qsize(), 1)

    def test_slow_drawing_preview_keeps_tk_live_and_cannot_replace_new_selection(self):
        app = self.app
        entered, release = threading.Event(), threading.Event()
        def slow_image(*args, **kwargs):
            entered.set()
            release.wait(2)
            return "unused-cancelled-image"
        app.query_cancel.set()
        app.query_generation += 1
        rows = [{"document_id": "doc", "key": str(i), "path": str(self.pc / "paper.pdf"),
                 "kind": "drawing" if i == 0 else "highlight", "quote": f"Passage {i}", "label": "2", "page": 2}
                for i in range(2)]
        future = Future()
        future.set_result(rows)
        with patch.object(self.store, "entry_image", side_effect=slow_image):
            app.finish_query(app.query_generation, None, future)
            self.assertTrue(entered.wait(1))
            app.notes.selection_set("1")
            heartbeat = []
            self.root.after(0, lambda: heartbeat.append(True))
            self.root.update()
            self.assertTrue(heartbeat)
            self.assertIn("Passage 1", app.preview_text.get("1.0", "end"))
            release.set()
            self.pump_until(lambda: app.preview_future.done())
            app.poll()
            self.assertIsNone(app.image)
            self.assertEqual(app.notes.selection(), ("1",))

    def test_tooltip_teardown_cancels_pending_and_visible_help(self):
        button = ttk.Button(self.root, text="Help")
        tip = Tooltip(button, "Short explanation")
        tip.schedule()
        self.assertIsNotNone(tip.pending)
        button.destroy()
        self.assertIsNone(tip.pending)
        button = ttk.Button(self.root, text="Help")
        tip = Tooltip(button, "Short explanation")
        with patch.object(tip, "pointer_over", return_value=True):
            tip.show()
        self.assertIsNotNone(tip.window)
        button.destroy()
        self.root.update()
        self.assertIsNone(tip.window)
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
