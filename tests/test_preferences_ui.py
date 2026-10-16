"""Preferences stay readable and apply only explicitly saved choices."""
from concurrent.futures import Future, ThreadPoolExecutor
import json
from pathlib import Path
import queue
from types import SimpleNamespace
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from note_organizer.dialogs import PreferencesDialog
from note_organizer.service import Service
from note_organizer.storage import DEFAULT_SETTINGS, Store
from note_organizer.theme import apply_theme
from note_organizer.widgets import Tooltip, fit_dialog


class DeferredExecutor:
    """Delay diagnostics deliberately; never inspect the user's actual libraries."""

    def __init__(self):
        self.future = Future()
        self.submitted = None

    def submit(self, function, *args):
        self.submitted = function, args
        return self.future


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class PreferencesUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.data = self.folder / "data"
        self.store = Store(self.data / "library.sqlite3")
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        apply_theme(self.root)
        self.service = Service(self.store)
        self.executor = DeferredExecutor()
        self.workflow_executor = ThreadPoolExecutor(max_workers=1)
        self.app = SimpleNamespace(root=self.root, store=self.store, data_dir=self.data,
                                   service=self.service, viewer_preference={"viewer": "system"},
                                   query_executor=self.executor, dialog_results=queue.Queue(),
                                   workflow_executor=self.workflow_executor, workflow_futures=set(),
                                   workflow_results=queue.Queue(),
                                   open_path=Mock(), show_sync_details=Mock())
        # Availability must be reproducible across machines running the suite.
        self.ocr_patch = patch("note_organizer.dialogs.shutil.which", return_value=None)
        self.ocr_patch.start()
        self.dialog = PreferencesDialog(self.app)
        self.root.update()

    def tearDown(self):
        self.ocr_patch.stop()
        self.service.stop()
        self.workflow_executor.shutdown(wait=True, cancel_futures=True)
        for pending in self.root.tk.call("after", "info"):
            self.root.after_cancel(pending)
        self.root.destroy()
        self.temp.cleanup()

    def queued_commands(self):
        commands = []
        while not self.service.commands.empty():
            commands.append(self.service.commands.get_nowait())
        return commands

    def settle_save(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            try:
                success, failure, future = self.app.workflow_results.get_nowait()
            except queue.Empty:
                time.sleep(.01)
                continue
            self.app.workflow_futures.discard(future)
            try:
                result = future.result()
            except Exception as exc:
                failure(exc)
            else:
                success(result)
            return
        self.fail("Preferences save did not complete")

    def test_defaults_commit_and_existing_folder_settings_remain_intact(self):
        existing_id = self.store.add_project(self.folder / "Existing")
        self.dialog.processing.group.set("Whole page")
        self.dialog.processing.layout.set("Detailed")
        self.dialog.save()
        self.settle_save()
        self.assertEqual(self.app.viewer_preference, {"viewer": "system"})
        self.assertEqual(json.loads(self.store.project(existing_id)["settings"]), DEFAULT_SETTINGS)
        saved = self.store.default_settings()
        self.assertEqual((saved["grouping"], saved["notebook_style"]), ("Whole page", "Detailed"))
        self.assertEqual(json.loads(self.store.project(existing_id)["settings"]), DEFAULT_SETTINGS)
        new_id = self.store.add_project(self.folder / "Future")
        self.assertEqual(json.loads(self.store.project(new_id)["settings"]), saved)
        self.assertEqual(self.store.preference("pdf_viewer"), {"viewer": "system"})
        self.assertEqual(self.queued_commands(), [])
        self.assertFalse(self.dialog.window.winfo_exists())
        self.assertFalse(self.errors)

    def test_pdf_viewer_explains_windows_default_without_an_app_override(self):
        self.assertIn("Windows default PDF application", self.dialog.viewer_help.get())
        self.assertIn("physical page", self.dialog.viewer_help.get())
        self.assertFalse(hasattr(self.dialog, "viewer_path"))

    def test_save_replaces_legacy_viewer_override_with_windows_default(self):
        self.app.viewer_preference = {"viewer": "adobe"}
        self.store.set_preference("pdf_viewer", self.app.viewer_preference)
        self.dialog.save()
        self.settle_save()
        self.assertEqual(self.app.viewer_preference, {"viewer": "system"})
        self.assertEqual(self.store.preference("pdf_viewer"), {"viewer": "system"})
        self.assertEqual(self.queued_commands(), [])

    def test_failed_save_keeps_dialog_and_all_preferences(self):
        with self.store.connect() as db:
            db.execute("""CREATE TRIGGER reject_defaults BEFORE INSERT ON preferences
                          WHEN NEW.key='default_settings'
                          BEGIN SELECT RAISE(ABORT, 'synthetic preferences failure'); END""")
        self.dialog.processing.group.set("Whole page")
        self.dialog.save()
        self.settle_save()
        self.assertTrue(self.dialog.window.winfo_exists())
        self.assertFalse(self.dialog.saving)
        self.assertFalse(self.dialog.save_button.instate(["disabled"]))
        self.assertIn("Preferences were not saved", self.dialog.save_status.get())
        self.assertIsNone(self.store.preference("pdf_viewer"))
        self.assertIsNone(self.store.preference("default_settings"))
        self.assertEqual(self.app.viewer_preference, {"viewer": "system"})
        self.assertEqual(self.queued_commands(), [])

    def test_whole_page_disables_distance_and_explains_choice(self):
        gap = next(w for w in descendants(self.dialog.window) if isinstance(w, ttk.Spinbox) and str(w.cget("textvariable")) == str(self.dialog.processing.gap))
        self.dialog.processing.group.set("Whole page")
        self.assertTrue(gap.instate(["disabled"]))
        self.assertIn("All drawings on a page", self.dialog.processing.explanation.get())
        self.dialog.processing.group.set("Nearby lines")
        self.assertFalse(gap.instate(["disabled"]))
        self.assertIn("unavailable", self.dialog.processing.explanation.get())

    def test_ocr_unavailable_does_not_save_invalid_preferences(self):
        self.dialog.processing.ocr.set(True)
        with patch("note_organizer.dialogs.messagebox.showerror") as error:
            self.dialog.save()
        self.assertEqual(error.call_args.args[0], "Transcription unavailable")
        self.assertFalse(self.queued_commands())
        self.assertTrue(self.dialog.window.winfo_exists())

    def test_buttons_fields_and_selectors_have_meaningful_tooltips(self):
        interactive = (ttk.Button, ttk.Checkbutton, ttk.Combobox, ttk.Spinbox, ttk.Entry)
        controls = [w for w in descendants(self.dialog.window) if isinstance(w, interactive)]
        self.assertGreaterEqual(len(controls), 13)
        for widget in controls:
            with self.subTest(widget=widget):
                self.assertIsInstance(getattr(widget, "tooltip", None), Tooltip)
                text = widget.tooltip.text() if callable(widget.tooltip.text) else widget.tooltip.text
                self.assertGreater(len(text), 20)

    def test_diagnostics_future_updates_via_ui_queue_without_changes(self):
        self.store.set_preference("remarkable", {"pc_root": "Saved PC folder", "enabled": False})
        self.store.set_preference("pdf_viewer", {"viewer": "system"})
        before = self.store.path.read_bytes()
        result = {"active": {"name": "Project library", "documents": 2, "notes": 12},
                  "alternatives": [{"name": "Installed app library", "path": str(self.folder / "Other"), "documents": 7, "notes": 99}]}
        completion = threading.Thread(target=lambda: self.executor.future.set_result(result))
        completion.start()
        completion.join()
        self.assertEqual(self.dialog.diagnostics.get(), "Checking saved libraries…")
        window, callback, future = self.app.dialog_results.get_nowait()
        self.assertEqual(window, self.dialog.window)
        callback(future)
        self.root.update()
        self.assertIn("Other saved library: Installed app library", self.dialog.diagnostics.get())
        self.assertIn("No databases are merged or moved", self.dialog.diagnostics.get())
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse(self.queued_commands())
        self.assertEqual(self.dialog.library_path_entry.get(), str(self.data.resolve()))
        self.assertEqual(str(self.dialog.library_path_entry.cget("state")), "readonly")
        self.assertEqual(self.dialog.diagnostics_display.text.get("1.0", "end-1c"), self.dialog.diagnostics.get())
        self.assertFalse(self.errors)

    def test_cancel_and_open_diagnostic_buttons_do_not_save_edits(self):
        self.dialog.processing.group.set("Whole page")
        buttons = {w.cget("text"): w for w in descendants(self.dialog.window) if isinstance(w, ttk.Button)}
        buttons["Open data folder"].invoke()
        self.app.open_path.assert_called_once_with(self.data)
        buttons["Show sync details"].invoke()
        self.app.show_sync_details.assert_called_once_with()
        buttons["Cancel"].invoke()
        self.assertFalse(self.queued_commands())
        self.assertIsNone(self.store.preference("default_settings"))

    def test_preferences_dialog_fits_a_typical_laptop_height(self):
        self.root.update_idletasks()
        self.assertLess(self.dialog.window.winfo_reqheight(), 700)
        self.assertLess(self.dialog.window.winfo_reqwidth(), 780)

    def test_dialog_is_clamped_when_parent_is_near_the_screen_edge(self):
        window = self.dialog.window
        parent = SimpleNamespace(winfo_rootx=lambda: window.winfo_screenwidth()-8,
                                 winfo_rooty=lambda: window.winfo_screenheight()-8,
                                 winfo_width=lambda: 940, winfo_height=lambda: 620)
        fit_dialog(window, parent)
        self.root.update_idletasks()
        self.assertLessEqual(window.winfo_rootx()+window.winfo_width(), window.winfo_screenwidth())
        self.assertLessEqual(window.winfo_rooty()+window.winfo_height(), window.winfo_screenheight())


if __name__ == "__main__":
    unittest.main()
