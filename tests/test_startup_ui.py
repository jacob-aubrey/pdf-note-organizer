"""Startup stays visually stable while local preparation runs off the Tk loop."""
import gc
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from note_organizer.startup import StartupSplash


class StartupSplashTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.release = threading.Event()
        self.entered = threading.Event()
        self.app = SimpleNamespace(library_loaded=False, closing=False, reader_search_busy=False,
            notes_after=None, refresh_needed=False, library_future=object(), close=Mock())
        self.failed = Mock()
        self.built = Mock(side_effect=self.build)
        self.splash = None

    def tearDown(self):
        self.release.set()
        if self.splash:
            self.splash.wait_closed()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.assertFalse(self.errors)
        self.splash = self.root = None
        gc.collect()

    def prepare(self, report):
        report("Importing existing notes…")
        self.worker_thread = threading.get_ident()
        self.entered.set()
        self.release.wait(5)
        return "prepared library"

    def build(self, library):
        self.assertEqual(library, "prepared library")
        self.assertEqual(threading.get_ident(), self.ui_thread)
        self.root.geometry("940x620+0+0")
        ttk.Label(self.root, text="Ready workspace").pack(fill="x")
        return self.app

    def start(self, prepare=None, build=None):
        self.ui_thread = threading.get_ident()
        self.splash = StartupSplash(self.root, prepare or self.prepare, build or self.built, self.failed)
        return self.splash

    def wait(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                self.assertFalse(self.errors)
                return
            time.sleep(.005)
        self.fail("Startup did not settle")

    def test_splash_is_branded_and_library_preparation_keeps_tk_responsive(self):
        splash = self.start()
        self.wait(self.entered.is_set)
        self.wait(lambda: splash.message.get() == "Importing existing notes…")
        heartbeat = []
        self.root.after(0, lambda: heartbeat.append(True))
        self.wait(lambda: heartbeat)
        self.assertNotEqual(self.worker_thread, self.ui_thread)
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertTrue(splash.window.winfo_viewable())
        self.assertEqual(float(splash.window.attributes("-alpha")), 1)
        self.assertGreater(splash.logo.width(), 0)
        self.assertTrue(splash.cancel_button.tooltip.enabled)
        self.built.assert_not_called()

    def test_reveal_waits_for_saved_contents_and_scheduled_result_batches(self):
        splash = self.start()
        self.release.set()
        self.wait(lambda: splash.app is not None)
        self.assertEqual(float(self.root.attributes("-alpha")), 0)
        self.assertFalse(splash.revealed)
        self.app.refresh_needed, self.app.library_future = True, None
        self.wait(lambda: splash.message.get() == "Waiting for library access…")
        self.app.library_loaded, self.app.reader_search_busy = True, True
        self.wait(lambda: splash.message.get() == "Loading papers and notes…")
        self.app.reader_search_busy, self.app.notes_after = False, "pending batch"
        self.root.update()
        self.assertFalse(splash.revealed)
        self.app.notes_after = None
        self.wait(lambda: splash.revealed)
        self.assertEqual(float(self.root.attributes("-alpha")), 1)
        self.assertTrue(splash.closed)
        self.assertFalse(splash.window.winfo_exists())
        self.assertIsNone(splash.pending)

    def test_background_sync_and_cloud_work_do_not_delay_reveal(self):
        self.app.service = SimpleNamespace(busy=True, cloud_busy=True)
        self.app.cloud_path_future = Mock(done=Mock(return_value=False))
        self.app.library_loaded = True
        splash = self.start()
        self.release.set()
        self.wait(lambda: splash.revealed)
        self.assertTrue(self.app.service.busy)

    def test_cancel_while_preparing_never_builds_or_reveals_the_app(self):
        splash = self.start()
        self.wait(self.entered.is_set)
        splash.cancel()
        self.assertFalse(splash.closed)
        self.assertIn("Closing:", splash.message.get())
        self.assertIn("safely", splash.cancel_button.tooltip.text())
        self.release.set()
        self.wait(lambda: splash.closed)
        splash.wait_closed()
        self.root.update()
        self.assertFalse(splash.revealed)
        self.assertIsNone(splash.pending)
        self.built.assert_not_called()

    def test_cancel_before_preparation_starts_does_not_start_a_worker(self):
        prepare = Mock()
        splash = self.start(prepare=prepare)
        splash.cancel()
        self.root.update()
        self.assertTrue(splash.closed)
        self.assertIsNone(splash.future)
        prepare.assert_not_called()

    def test_cancel_after_build_uses_the_apps_safe_shutdown(self):
        splash = self.start()
        self.release.set()
        self.wait(lambda: splash.app is not None)
        splash.cancel()
        splash.cancel()
        self.app.close.assert_called_once()
        self.assertFalse(splash.revealed)

    def test_preparation_and_build_errors_remove_splash_and_keep_error_details(self):
        for phase in ("prepare", "build"):
            with self.subTest(phase=phase):
                problem = ValueError(f"Synthetic {phase} failure")
                splash = self.start(
                    prepare=Mock(side_effect=problem) if phase == "prepare" else lambda _: "prepared library",
                    build=Mock(side_effect=problem) if phase == "build" else None)
                self.wait(lambda: self.failed.called)
                self.failed.assert_called_once_with(problem)
                self.assertTrue(splash.closed)
                self.assertFalse(splash.revealed)
                self.assertEqual(self.root.state(), "withdrawn")
                splash.wait_closed()
                self.failed.reset_mock()

    def test_root_destroyed_during_startup_leaves_no_preparation_thread(self):
        splash = self.start()
        self.wait(self.entered.is_set)
        self.root.destroy()
        self.release.set()
        splash.wait_closed()
        self.assertTrue(splash.closed)
        self.assertIsNone(splash.pending)


class StartupWorkspaceTests(unittest.TestCase):
    def test_actual_saved_library_and_responsive_layout_are_ready_at_reveal(self):
        from note_organizer.service import Service
        from note_organizer.storage import Store, digest_file
        from note_organizer.ui import App
        from tests.reader_app_regression import capture_test_window
        import pymupdf

        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            store = Store(data / "library.sqlite3")
            project = store.add_project(data)
            path = data / "Startup paper.pdf"
            with pymupdf.open() as document:
                document.new_page().insert_text((45, 60), "Startup test paper")
                document.save(path)
            store.save_scan(project, path, digest_file(path), "sig", "settings", {"title": "Startup paper"},
                [{"key": f"note-{i}", "kind": "highlight", "page": 1,
                  "rect": [45, 45, 150, 65], "quote": f"Saved note {i}"} for i in range(205)])
            root = tk.Tk()
            root.withdraw()
            errors, apps = [], []
            root.report_callback_exception = lambda *args: errors.append(args)

            def build(library):
                app = App(root, library, data)
                apps.append(app)
                return app

            splash = None
            release = threading.Event()
            def prepared(report):
                release.wait(5)
                return store
            try:
                with patch.object(Service, "start"), patch("note_organizer.pdf_reader.PDFReader.load_entry"):
                    splash = StartupSplash(root, prepared, build, lambda exc: errors.append(exc))
                    root.update()
                    destination = Path(__file__).resolve().parents[1] / ".test-tmp" / "startup-splash.png"
                    destination.parent.mkdir(exist_ok=True)
                    capture_test_window(splash.window, destination)
                    release.set()
                    deadline = time.monotonic() + 8
                    while not splash.revealed and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.005)
                    self.assertTrue(splash.revealed, splash.message.get())
                    app = apps[0]
                    self.assertTrue(app.library_loaded)
                    self.assertFalse(app.reader_search_busy)
                    self.assertIsNone(app.notes_after)
                    self.assertEqual(len(app.notes.get_children()), 205)
                    self.assertEqual(app.tabs.select(), str(app.notes_tab))
                    self.assertEqual(float(root.attributes("-alpha")), 1)
                    self.assertGreater(app.reader_pane.sashpos(0), 100)
                    widths = [app.reader_folder.winfo_width(), app.reader_paper.winfo_width(), app.label_picker.winfo_width()]
                    self.assertLessEqual(max(widths)-min(widths), 1)
                    geometry = root.geometry()
                    def visible_layout(parent):
                        result = {}
                        for widget in parent.winfo_children():
                            if widget.winfo_ismapped():
                                result[str(widget)] = (widget.winfo_x(), widget.winfo_y(), widget.winfo_width(), widget.winfo_height())
                                result.update(visible_layout(widget))
                        return result
                    layout = visible_layout(root)
                    end = time.monotonic() + .2
                    while time.monotonic() < end:
                        root.update()
                        time.sleep(.005)
                    self.assertEqual(root.geometry(), geometry)
                    self.assertEqual(visible_layout(root), layout)
                    self.assertFalse(errors)
            finally:
                release.set()
                if splash:
                    splash.wait_closed()
                for app in apps:
                    app.closing = True
                    app.pdf_reader.close()
                    app.inbox.stop()
                    app.service.stop()
                    app.query_cancel.set()
                    app.preview_cancel.set()
                    app.workflow_executor.shutdown(wait=True, cancel_futures=True)
                    app.context_executor.shutdown(wait=True, cancel_futures=True)
                    app.query_executor.shutdown(wait=True, cancel_futures=True)
                    app.pdf_worker.shutdown(wait=True)
                for pending in root.tk.call("after", "info"):
                    root.after_cancel(pending)
                root.destroy()
                apps.clear()
                splash = app = root = None
                gc.collect()


class StartupEntryPointTests(unittest.TestCase):
    def test_entry_point_reveals_ready_app_and_preserves_cleanup(self):
        self.run_launch()

    def test_entry_point_reports_library_preparation_failure(self):
        self.run_launch("library")

    def test_entry_point_keeps_missing_package_guidance(self):
        self.run_launch("package")

    def run_launch(self, failure=None):
        from contextlib import ExitStack
        from note_organizer import main as launcher
        from note_organizer import ui, storage, startup

        observed, errors = [], []
        app = SimpleNamespace(library_loaded=True, closing=False, reader_search_busy=False,
            notes_after=None, refresh_needed=False, library_future=None, pdf_reader=Mock(), inbox=Mock(),
            workflow_executor=Mock(), service=SimpleNamespace(stop=Mock(), thread=None),
            query_cancel=Mock(), preview_cancel=Mock(), pdf_worker=Mock(),
            context_executor=Mock(), query_executor=Mock())

        class ObservedSplash(StartupSplash):
            def __init__(self, root, *args):
                root.report_callback_exception = lambda *args: (errors.append(args), root.quit())
                root.after(4000, root.quit)
                super().__init__(root, *args)

            def reveal(self):
                super().reveal()
                observed.append((self.root.state(), float(self.root.attributes("-alpha")), self.closed))
                self.root.after_idle(self.root.quit)

        def build(root, store, data):
            if failure == "package":
                raise ModuleNotFoundError("Missing synthetic package", name="synthetic_package")
            root.geometry("940x620+0+0")
            ttk.Label(root, text="Ready workspace").pack()
            return app

        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(launcher, "resolve_data_directory", return_value=Path(folder)))
            stack.enter_context(patch.object(launcher, "should_import_legacy", return_value=True))
            stack.enter_context(patch.object(launcher, "RotatingFileHandler"))
            stack.enter_context(patch.object(launcher.logging, "basicConfig"))
            stack.enter_context(patch.object(launcher.logging, "error"))
            shown = stack.enter_context(patch.object(launcher.messagebox, "showerror"))
            store = stack.enter_context(patch.object(storage, "Store",
                side_effect=ValueError("Synthetic library failure") if failure == "library" else None))
            stack.enter_context(patch.object(ui, "App", side_effect=build))
            stack.enter_context(patch.object(startup, "StartupSplash", ObservedSplash))
            launcher.main()
            self.assertFalse(errors)
            if failure:
                shown.assert_called_once()
                self.assertFalse(observed)
                message = shown.call_args.args[1]
                self.assertIn("Synthetic library failure" if failure == "library" else "synthetic_package", message)
                if failure == "package":
                    self.assertIn(".venv", message)
            else:
                self.assertEqual(observed, [("normal", 1, True)])
                shown.assert_not_called()
                store.return_value.import_legacy.assert_called_once()
                app.pdf_reader.wait_closed.assert_called_once()
                app.pdf_worker.shutdown.assert_called_once_with(wait=True)


if __name__ == "__main__":
    unittest.main()
