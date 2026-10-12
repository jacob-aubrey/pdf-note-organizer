"""Responsive startup and bounded context jobs, using disposable libraries."""
from concurrent.futures import Future
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import tkinter as tk
import _tkinter
import unittest
from unittest.mock import patch

from PIL import Image

from note_organizer.service import Service
from note_organizer.storage import Store
from note_organizer.ui import App
from note_organizer.image_viewport import ImageViewport
from tests import test_ui_audit
from tests.ui_helpers import settle_library


class UIPerformanceTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def tearDown(self):
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        test_ui_audit.UIAuditTests.tearDown(self)

    def show_entries(self, *kinds):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        future = Future()
        future.set_result([{"document_id": "doc", "key": str(index), "path": str(self.pc / "paper.pdf"),
                            "kind": kind, "quote": f"Passage {index}", "page": index + 1,
                            "page_count": 12, "label": "233"}
                           for index, kind in enumerate(kinds)])
        app.finish_query(app.query_generation, None, future)
        self.root.update()
        return app

    def test_export_status_refresh_does_not_requery_or_rebuild_notes(self):
        paper = self.pc / "paper.pdf"
        project_id = self.store.add_project(self.pc)
        self.store.save_scan(project_id, paper, "digest", "signature", "settings", {},
                             [{"key": "quote", "kind": "highlight", "quote": "Saved passage", "page": 1,
                               "rect": [1, 1, 20, 20]}])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.pump_until(lambda: bool(self.app.entries))
        self.app.notes.selection_set("0")
        with self.store.connect() as db:
            db.execute("UPDATE projects SET dirty=0,exported_at='2026-10-05T12:00:00' WHERE id=?", (project_id,))
        with patch.object(self.store, "entries", wraps=self.store.entries) as query, \
                patch.object(self.app.notes, "delete", wraps=self.app.notes.delete) as delete:
            self.app.refresh()
            settle_library(self.app, self.root)
            self.assertEqual(query.call_count, 0)
            self.assertEqual(delete.call_count, 0)
            self.assertEqual(self.app.notes.selection(), ("0",))

    def test_same_count_changed_text_refreshes_selected_note(self):
        paper = self.pc / "paper.pdf"
        project_id = self.store.add_project(self.pc)
        entry = {"key": "quote", "kind": "highlight", "quote": "First text", "page": 1, "rect": [1, 1, 20, 20]}
        self.store.save_scan(project_id, paper, "digest", "signature", "settings", {}, [entry])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.pump_until(lambda: self.app.entries and self.app.entries[0]["quote"] == "First text")
        self.store.save_scan(project_id, paper, "digest", "signature", "settings", {}, [{**entry, "quote": "Updated text"}])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.pump_until(lambda: self.app.entries and self.app.entries[0]["quote"] == "Updated text")
        self.assertIn("Updated text", self.app.preview_text.get("1.0", "end"))

    def test_full_page_wait_keeps_queries_and_tk_running_and_coalesces_clicks(self):
        app = self.show_entries("drawing", "highlight")
        entered, release = threading.Event(), threading.Event()
        def slow_page(*args):
            entered.set()
            release.wait(3)
            return Image.new("RGB", (200, 300), "white")
        try:
            with patch.object(app.pdf_worker, "materialize", side_effect=lambda store, path, **kw: Path(path)), \
                    patch.object(app, "load_full_page", side_effect=slow_page) as render:
                app.full_page_context()
                self.assertTrue(entered.wait(1))
                window = app.context_window
                for _ in range(12):
                    app.full_page_context()
                self.assertIs(app.context_window, window)
                self.assertEqual(render.call_count, 1)
                heartbeat = []
                self.root.after(0, lambda: heartbeat.append(True))
                self.root.update()
                self.assertTrue(heartbeat)
                # A blocked renderer cannot occupy the single reader executor.
                self.assertEqual(app.query_executor.submit(lambda: "search live").result(timeout=1), "search live")
                self.assertTrue(app.full_page_button.instate(["!disabled"]))
                release.set()
                self.pump_until(lambda: app.context_future.done())
                app.poll()
                self.assertTrue(window.winfo_exists())
                window.destroy()
        finally:
            release.set()

    def test_closed_context_ignores_late_result_and_blocks_duplicate_pending_jobs(self):
        app = self.show_entries("drawing")
        pending = Future()
        pending.set_running_or_notify_cancel()
        with patch.object(app.context_executor, "submit", return_value=pending) as submit:
            app.full_page_context()
            app.context_window.destroy()
            app.full_page_context()
            self.assertIsNone(app.context_window)
            self.assertEqual(submit.call_count, 1)
        # Simulate a job that had already started before its window closed.
        self.assertFalse(pending.cancelled())
        pending.set_result(Image.new("RGB", (200, 300), "white"))
        app.poll()
        self.assertFalse(self.errors)

    def test_full_page_fits_width_and_wheel_scrolls_after_window_resize(self):
        app = self.show_entries("drawing")
        finished = Future()
        finished.set_result(Image.new("RGB", (1800, 3200), "white"))
        with patch.object(app.context_executor, "submit", return_value=finished):
            app.full_page_context()
        window = app.context_window
        window.attributes("-alpha", 0)
        window.geometry("640x480")
        self.root.update()
        app.poll()
        self.root.update()
        canvas = window.context_canvas
        self.assertLessEqual(canvas.image.width(), canvas.winfo_width())
        self.assertEqual(canvas.xview(), (0.0, 1.0))
        self.assertLess(canvas.yview()[1], 1)
        canvas.event_generate("<MouseWheel>", delta=-120)
        self.root.update()
        self.assertGreater(canvas.yview()[0], 0)
        first_width = canvas.image.width()
        window.geometry("1100x700")
        self.root.update()
        self.assertGreater(canvas.image.width(), first_width)
        self.assertLessEqual(canvas.image.width(), canvas.winfo_width())
        self.assertEqual(canvas.xview(), (0.0, 1.0))
        self.assertEqual(canvas.original_image.size, (1800, 3200))
        self.assertEqual(len(canvas.find_all()), 1)
        self.assertFalse(self.errors)
        window.destroy()

    def test_enlarged_image_wheel_pan_and_pointer_zoom(self):
        app = self.app
        app.image = Image.new("RGB", (1400, 2200), "white")
        window = app.enlarge()
        window.attributes("-alpha", 0)
        window.geometry("700x500")
        self.root.update()
        canvas = window.image_canvas
        canvas.event_generate("<MouseWheel>", x=200, y=180, delta=-120)
        self.root.update()
        self.assertGreater(canvas.yview()[0], 0)
        canvas.event_generate("<ButtonPress-1>", x=200, y=180)
        self.assertTrue(canvas.panning)
        self.assertEqual(canvas.cget("cursor"), canvas.pan_cursor)
        self.assertNotEqual(canvas.cget("cursor"), "fleur")
        if self.root.tk.call("tk", "windowingsystem") == "win32":
            self.assertIn("closed-hand.cur", canvas.cget("cursor"))
        canvas.event_generate("<B1-Motion>", x=100, y=80, state=256)
        canvas.event_generate("<ButtonRelease-1>", x=100, y=80)
        self.assertFalse(canvas.panning)
        self.assertEqual(canvas.cget("cursor"), "")
        self.root.update()
        self.assertGreater(canvas.xview()[0], 0)
        before = (canvas.canvasx(200) / canvas.zoom, canvas.canvasy(180) / canvas.zoom)
        canvas.event_generate("<MouseWheel>", x=200, y=180, delta=120, state=4)
        self.root.update()
        self.assertGreater(canvas.zoom, 1)
        after = (canvas.canvasx(200) / canvas.zoom, canvas.canvasy(180) / canvas.zoom)
        self.assertAlmostEqual(before[0], after[0], delta=2)
        self.assertAlmostEqual(before[1], after[1], delta=2)
        canvas.event_generate("<MouseWheel>", x=200, y=180, delta=-120, state=4)
        self.root.update()
        self.assertAlmostEqual(canvas.zoom, 1)
        self.assertEqual(canvas.original_image.size, (1400, 2200))
        self.assertEqual(len(canvas.find_all()), 1)
        self.assertFalse(self.errors)
        window.destroy()

    def test_both_viewers_fit_height_on_resize_and_double_click_returns_to_width(self):
        app = self.show_entries("drawing")
        image = Image.new("RGB", (1600, 2400), "white")
        app.image = image
        enlarged = app.enlarge()
        finished = Future()
        finished.set_result(image)
        with patch.object(app.context_executor, "submit", return_value=finished):
            app.full_page_context()
        context = app.context_window
        self.root.update()
        app.poll()
        for window, canvas in ((enlarged, enlarged.image_canvas), (context, context.context_canvas)):
            with self.subTest(window=window.title()):
                window.attributes("-alpha", 0)
                window.geometry("700x500")
                self.root.update()
                window.fit_height_button.invoke()
                self.root.update()
                self.assertEqual(canvas.fit_mode, "height")
                self.assertAlmostEqual(canvas.image.height(), canvas.winfo_height(), delta=1)
                self.assertEqual(canvas.yview(), (0.0, 1.0))
                fitted_height = canvas.image.height()
                window.geometry("700x650")
                self.root.update()
                self.assertGreater(canvas.image.height(), fitted_height)
                self.assertAlmostEqual(canvas.image.height(), canvas.winfo_height(), delta=1)
                canvas.event_generate("<MouseWheel>", x=200, y=150, delta=120, state=4)
                self.root.update()
                self.assertIsNone(canvas.fit_mode)
                canvas.event_generate("<ButtonPress-1>", x=200, y=150, time=1000)
                canvas.event_generate("<ButtonRelease-1>", x=200, y=150, time=1001)
                canvas.event_generate("<ButtonPress-1>", x=200, y=150, time=1100)
                canvas.event_generate("<ButtonRelease-1>", x=200, y=150, time=1101)
                self.root.update()
                self.assertTrue(canvas.auto_fit_width)
                self.assertAlmostEqual(canvas.image.width(), canvas.winfo_width(), delta=1)
                self.assertEqual(canvas.xview(), (0.0, 1.0))
                self.assertFalse(canvas.panning)
                self.assertEqual(canvas.cget("cursor"), "")
                self.assertIs(canvas.original_image, image)
                self.assertEqual(len(canvas.find_all()), 1)
                window.destroy()
        self.assertFalse(self.errors)

    def test_small_closeup_can_fill_width_and_lost_focus_releases_pan_cursor(self):
        self.app.image = Image.new("RGB", (120, 220), "white")
        window = self.app.enlarge()
        window.attributes("-alpha", 0)
        window.geometry("700x500")
        self.root.update()
        canvas = window.image_canvas
        window.fit_width_button.invoke()
        self.root.update()
        self.assertGreater(canvas.zoom, 1)
        self.assertAlmostEqual(canvas.image.width(), canvas.winfo_width(), delta=1)
        # Give this test's window real Tk focus, then transfer it to a control.
        # A generated FocusOut alone would miss a canvas that never took focus.
        window.focus_force()
        window.fit_width_button.focus_set()
        self.root.update()
        canvas.event_generate("<ButtonPress-1>", x=200, y=150)
        self.assertTrue(canvas.panning)
        self.root.update()
        self.assertIs(canvas.focus_get(), canvas)
        window.fit_width_button.focus_set()
        self.root.update()
        self.assertFalse(canvas.panning)
        self.assertEqual(canvas.cget("cursor"), "")
        self.assertEqual(canvas.original_image.size, (120, 220))
        self.assertFalse(self.errors)
        window.destroy()

    def test_height_fit_near_viewport_ratio_settles_without_scrollbar_oscillation(self):
        window = tk.Toplevel(self.root)
        window.attributes("-alpha", 0)
        window.geometry("600x450")
        viewport = ImageViewport(window, window, lambda text: None, background="white")
        viewport.pack(fill="both", expand=True)
        self.root.update()
        configurations = []
        viewport.canvas.bind("<Configure>", lambda event: configurations.append((event.width, event.height)), add="+")
        viewport.canvas.set_image(Image.new("RGB", (1330, 1000), "white"))
        viewport.canvas.fit_height()
        # Bound event processing so a regression fails instead of hanging Tk.
        for _ in range(200):
            self.root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT)
        self.assertLess(len(configurations), 10)
        self.assertTrue(viewport.horizontal.winfo_ismapped())
        fitted = viewport.canvas.display_size
        for _ in range(100):
            self.root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT)
        self.assertEqual(viewport.canvas.display_size, fitted)
        self.assertAlmostEqual(viewport.canvas.image.height(), viewport.canvas.winfo_height(), delta=1)
        self.assertFalse(self.errors)
        window.destroy()

    def test_full_page_zoom_pan_and_return_to_fit_width(self):
        app = self.show_entries("drawing")
        finished = Future()
        finished.set_result(Image.new("RGB", (1600, 2400), "white"))
        with patch.object(app.context_executor, "submit", return_value=finished):
            app.full_page_context()
        window = app.context_window
        window.attributes("-alpha", 0)
        window.geometry("640x480")
        self.root.update()
        app.poll()
        self.root.update()
        canvas = window.context_canvas
        initial = canvas.zoom
        canvas.event_generate("<MouseWheel>", x=200, y=180, delta=120, state=4)
        self.root.update()
        self.assertGreater(canvas.zoom, initial)
        self.assertFalse(canvas.auto_fit_width)
        self.assertGreater(canvas.display_size[0], canvas.winfo_width())
        before = (canvas.xview()[0], canvas.yview()[0])
        canvas.event_generate("<ButtonPress-1>", x=200, y=180)
        canvas.event_generate("<B1-Motion>", x=100, y=80, state=256)
        canvas.event_generate("<ButtonRelease-1>", x=100, y=80)
        self.root.update()
        self.assertGreater(canvas.yview()[0], before[1])
        self.assertGreater(canvas.xview()[0], before[0])
        zoom = canvas.zoom
        window.geometry("900x600")
        self.root.update()
        self.assertEqual(canvas.zoom, zoom)
        window.fit_width_button.invoke()
        self.root.update()
        self.assertTrue(canvas.auto_fit_width)
        self.assertEqual(canvas.xview(), (0.0, 1.0))
        self.assertLessEqual(canvas.image.width(), canvas.winfo_width())
        self.assertEqual(len(canvas.find_all()), 1)
        self.assertFalse(self.errors)
        window.destroy()

    def test_context_switches_to_new_physical_page_and_does_not_store_raster(self):
        app = self.show_entries("drawing", "drawing", "highlight")
        saved = self.store.path.read_bytes()
        finished = Future()
        finished.set_result(Image.new("RGB", (200, 300), "white"))
        with patch.object(app.context_executor, "submit", return_value=finished):
            app.full_page_context()
            previous = app.context_window
            app.poll()
            app.notes.selection_set("1")
            app.preview()
            app.full_page_context()
            self.assertFalse(previous.winfo_exists())
            self.assertEqual(app.context_window.context_identity, (app.entries[1]["path"], 2))
            app.poll()
            self.assertIn("PDF page 2", app.context_window.title())
            app.context_window.destroy()
            app.notes.selection_set("2")
            app.preview()
            self.assertTrue(app.full_page_button.instate(["disabled"]))
        self.assertEqual(self.store.path.read_bytes(), saved)

    def test_full_page_decoder_uses_physical_page_and_preserves_margins(self):
        stream = BytesIO()
        Image.new("RGB", (950, 400), "white").save(stream, format="PNG")
        with patch.object(self.app.pdf_worker, "materialize", return_value=Path("source.pdf")), \
                patch.object(self.app.pdf_worker, "full_page", return_value=stream.getvalue()) as render:
            image = self.app.load_full_page("source.pdf", 3)
        render.assert_called_once_with("source.pdf", 3)
        self.assertEqual(image.size, (950, 400))

    def test_reader_context_buttons_fit_minimum_window(self):
        app = self.show_entries("drawing")
        self.root.geometry("940x620")
        app.tabs.select(app.notes_tab)
        self.root.deiconify()
        self.root.update()
        right_edge = app.notes_tab.winfo_rootx() + app.notes_tab.winfo_width()
        for widget in (app.source_button, app.enlarge_button, app.full_page_button):
            self.assertGreater(widget.winfo_width(), 30)
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right_edge)

    def test_utility_buttons_stay_in_the_tab_row_when_window_resizes(self):
        app = self.app
        app.tabs.select(app.notes_tab)
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        for size in ("940x620", "1250x820", "1050x700"):
            self.root.geometry(size)
            self.root.update()
            right = app.tabs.winfo_rootx() + app.tabs.winfo_width()
            self.assertAlmostEqual(app.help_button.winfo_rootx() + app.help_button.winfo_width(), right - 2, delta=1)
            self.assertLess(app.settings_button.winfo_rootx(), app.help_button.winfo_rootx())
            page_top = app.notes_tab.winfo_rooty()
            for button in (app.settings_button, app.help_button):
                self.assertGreaterEqual(button.winfo_rooty(), app.tabs.winfo_rooty())
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), page_top)
        self.assertFalse(self.errors)


class StartupResponsivenessTests(unittest.TestCase):
    def test_locked_database_never_blocks_window_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "library.sqlite3")
            writer = sqlite3.connect(store.path)
            writer.execute("BEGIN EXCLUSIVE")
            root = tk.Tk()
            root.withdraw()
            app = None
            try:
                with patch.object(Service, "start"):
                    started = time.monotonic()
                    app = App(root, store, store.path.parent)
                    self.assertLess(time.monotonic() - started, 1)
                    heartbeat = []
                    root.after(0, lambda: heartbeat.append(True))
                    root.update()
                    self.assertTrue(heartbeat)
                    self.assertFalse(app.library_loaded)
                    self.assertTrue(app.search_entry.instate(["disabled"]))
                    self.assertTrue(app.settings_button.instate(["disabled"]))
                    self.assertTrue(app.help_button.instate(["!disabled"]))
                    app.show_work_progress()
                    self.assertEqual(app.work_phase.get(), "Loading library")
                    # The failed background read leaves the window live, then
                    # the next snapshot enables controls after the writer exits.
                    deadline = time.monotonic() + 2
                    while app.library_future is not None and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.005)
                    self.assertIsNone(app.library_future)
                    writer.rollback()
                    app.refresh()
                    settle_library(app, root)
                    self.assertTrue(app.library_loaded)
                    self.assertTrue(app.search_entry.instate(["!disabled"]))
                    self.assertTrue(app.settings_button.instate(["!disabled"]))
            finally:
                writer.close()
                if app:
                    app.closing = True
                    app.service.stop()
                    app.pdf_worker.shutdown(wait=True)
                    app.context_executor.shutdown(wait=True, cancel_futures=True)
                    app.query_executor.shutdown(wait=True, cancel_futures=True)
                for pending in root.tk.call("after", "info"):
                    root.after_cancel(pending)
                root.destroy()


if __name__ == "__main__":
    unittest.main()
