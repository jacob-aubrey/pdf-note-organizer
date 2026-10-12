"""Combined workflows use disposable inputs and never access cloud accounts."""
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from docx import Document

from note_organizer.service import Service
from note_organizer.storage import Store
from note_organizer.ui import App
from tests.ui_helpers import settle_library


class CombinedWorkflowUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = Store(self.folder / "data" / "library.sqlite3")
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        with patch.object(Service, "start"):
            self.app = App(self.root, self.store, self.store.path.parent)
            settle_library(self.app, self.root)

    def tearDown(self):
        self.app.closing = True
        self.app.inbox.stop()
        self.app.service.stop()
        self.app.pdf_worker.shutdown(wait=True)
        self.app.query_cancel.set()
        self.app.preview_cancel.set()
        self.app.workflow_executor.shutdown(wait=True, cancel_futures=True)
        self.app.query_executor.shutdown(wait=True, cancel_futures=True)
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.temp.cleanup()

    def settle_actions(self, predicate=lambda: True):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.root.update()
            self.app.poll()
            if predicate() and all(future.done() for future in self.app.workflow_futures) and self.app.workflow_results.empty():
                return
            time.sleep(.01)
        self.fail("Literature action did not settle")

    def commands(self):
        results = []
        while not self.app.service.commands.empty():
            results.append(self.app.service.commands.get_nowait())
        return results

    def test_fresh_app_hides_tablet_tab_and_opens_inbox(self):
        self.assertEqual(self.app.tabs.tab(self.app.remarkable_tab, "state"), "hidden")
        self.assertEqual(self.app.tabs.select(), str(self.app.inbox_tab))
        self.assertFalse(self.app.cloud_config()["integration_enabled"])
        self.assertFalse(self.app.inbox.config()["enabled"])

    def test_toggle_reveals_tab_then_hides_it_without_losing_routes(self):
        config = {"integration_enabled": True, "pc_root": str(self.folder / "Sorted"),
                  "source_folder_id": "literature", "mappings": {"child": str(self.folder / "child")}}
        self.store.set_preference("remarkable", config)
        self.app.refresh()
        settle_library(self.app, self.root)
        self.assertEqual(self.app.tabs.tab(self.app.remarkable_tab, "state"), "normal")
        self.app.tabs.select(self.app.remarkable_tab)
        self.store.set_preference("remarkable", {**config, "integration_enabled": False})
        self.app.refresh()
        settle_library(self.app, self.root)
        self.assertEqual(self.app.tabs.tab(self.app.remarkable_tab, "state"), "hidden")
        self.assertEqual(self.app.tabs.select(), str(self.app.library_tab))
        self.assertEqual(self.store.preference("remarkable")["mappings"], config["mappings"])

    def test_connections_settings_commit_explicit_enable_with_writes_off(self):
        self.app.global_settings()
        fields = self.app.preferences_dialog.integration
        self.assertFalse(fields.master.get())
        self.assertTrue(all(check.instate(["disabled"]) for check in fields.checks))
        fields.master.set(True)
        self.app.preferences_dialog.save()
        self.settle_actions()
        self.assertTrue(self.store.preference("remarkable")["integration_enabled"])
        self.assertFalse(any(name in {"viewer", "defaults", "remarkable_settings"} for name, _ in self.commands()))
        self.assertFalse(self.store.preference("remarkable", {}).get("send_new_pdfs", False))

    def test_word_filing_preserves_type_and_never_enters_pdf_pipeline(self):
        watch, library = self.folder / "Inbox", self.folder / "Topics"
        watch.mkdir()
        library.mkdir()
        self.app.inbox.save_config({"watch_folder": str(watch), "library_root": str(library), "naming_mode": "Basic"})
        self.app.inbox.stable_seconds = 0
        document = Document()
        document.core_properties.title = "Research protocol"
        document.add_paragraph("These are methods for the study.")
        source = watch / "protocol.docx"
        document.save(source)
        self.app.inbox.refresh()
        self.app.inbox.refresh()
        prepared = self.app.inbox.prepare(source)
        result = self.app.inbox.file_item(source, "Research_protocol.docx", library, expected_signature=prepared["signature"])
        self.assertFalse(result["is_pdf"])
        self.assertTrue(Path(result["path"]).is_file())
        self.assertFalse(source.exists())
        with patch.object(self.app.inbox_view, "load_rows"):
            self.settle_actions()
        self.assertFalse(any(name in {"filed_pdf", "remarkable_upload"} for name, _ in self.commands()))
        self.assertEqual(self.store.projects(), [])
        self.assertEqual(self.store.documents(), [])

    def test_pdf_filing_hands_off_once_to_worker(self):
        result = {"path": str(self.folder / "paper.pdf"), "is_pdf": True, "job_id": "saved-job"}
        self.app.workflow_events.put(("inbox_filed", result))
        with patch.object(self.app.inbox_view, "load_rows"):
            self.app.poll()
        self.assertEqual([command for command in self.commands() if command[0] == "filed_pdf"], [("filed_pdf", (result,))])

    def save_synthetic_gemini_key(self):
        with patch("note_organizer.inbox._protect_for_current_windows_user", return_value="synthetic-protected-key"), patch("note_organizer.inbox._unprotect_for_current_windows_user", return_value="synthetic-own-key"):
            self.app.inbox.save_config({"api_key": "synthetic-own-key", "gemini_enabled": True})

    def test_staging_key_removal_does_not_change_the_saved_key_or_live_settings(self):
        self.save_synthetic_gemini_key()
        saved = self.store.preference("inbox")
        self.app.global_settings()
        fields = self.app.preferences_dialog.sorting
        with patch.object(self.app.inbox, "remove_api_key") as removal:
            fields.remove_key_button.invoke()
        removal.assert_not_called()
        self.assertEqual(self.store.preference("inbox"), saved)
        self.assertTrue(self.app.inbox.config()["gemini_enabled"])
        self.assertEqual(fields.key_status.get(), "Key will be removed when you save.")
        self.assertEqual(fields.remove_key_button.cget("text"), "Undo removal")
        self.assertTrue(fields.key_entry.instate(["disabled"]))
        self.assertTrue(fields.gemini_toggle.instate(["disabled"]))
        self.assertFalse(fields.gemini_enabled.get())
        self.assertEqual(fields.values()["api_key"], "")

    def test_cancelling_settings_discards_key_removal_and_other_draft_edits(self):
        self.save_synthetic_gemini_key()
        saved = self.store.preference("inbox")
        self.app.global_settings()
        dialog = self.app.preferences_dialog
        fields = dialog.sorting
        fields.library.set(str(self.folder / "Unsaved draft"))
        fields.remove_key_button.invoke()
        dialog.cancel()
        self.assertEqual(self.store.preference("inbox"), saved)
        self.app.global_settings()
        reopened = self.app.preferences_dialog.sorting
        self.assertEqual(reopened.key_status.get(), "Key saved for your Windows account")
        self.assertTrue(reopened.gemini_enabled.get())
        self.assertEqual(reopened.library.get(), "")
        self.assertEqual(reopened.api_key.get(), "")

    def test_undo_key_removal_keeps_other_draft_edits_and_prior_gemini_choice(self):
        self.save_synthetic_gemini_key()
        saved = self.store.preference("inbox")
        self.app.global_settings()
        fields = self.app.preferences_dialog.sorting
        fields.gemini_enabled.set(False)
        fields.api_key.set("synthetic-replacement-key")
        fields.library.set(str(self.folder / "Draft library"))
        fields.remove_key_button.invoke()
        fields.remove_key_button.invoke()
        self.assertFalse(fields.gemini_enabled.get())
        self.assertFalse(fields.key_entry.instate(["disabled"]))
        self.assertFalse(fields.gemini_toggle.instate(["disabled"]))
        self.assertEqual(fields.remove_key_button.cget("text"), "Remove saved key")
        self.assertEqual(fields.key_status.get(), "Key saved for your Windows account")
        self.assertEqual(fields.values()["api_key"], "synthetic-replacement-key")
        self.assertEqual(fields.library.get(), str(self.folder / "Draft library"))
        self.assertEqual(self.store.preference("inbox"), saved)

    def test_saving_key_removal_deletes_the_key_and_turns_gemini_off(self):
        self.save_synthetic_gemini_key()
        self.app.global_settings()
        dialog = self.app.preferences_dialog
        fields = dialog.sorting
        fields.api_key.set("synthetic-replacement-key")
        fields.remove_key_button.invoke()
        dialog.save()
        self.settle_actions()
        saved = self.store.preference("inbox")
        self.assertNotIn("api_key", saved)
        self.assertNotIn("api_key_protected", saved)
        self.assertFalse(saved["gemini_enabled"])
        self.assertFalse(self.app.inbox.config()["api_key_present"])
        self.app.global_settings()
        reopened = self.app.preferences_dialog.sorting
        self.assertEqual(reopened.key_status.get(), "No Gemini key saved")
        self.assertTrue(reopened.remove_key_button.instate(["disabled"]))

    def test_failed_save_preserves_the_key_and_allows_undo(self):
        self.save_synthetic_gemini_key()
        saved = self.store.preference("inbox")
        self.app.global_settings()
        dialog = self.app.preferences_dialog
        fields = dialog.sorting
        fields.library.set(str(self.store.path.parent))
        fields.remove_key_button.invoke()
        dialog.save()
        self.settle_actions(lambda: not dialog.saving)
        self.assertTrue(dialog.window.winfo_exists())
        self.assertEqual(self.store.preference("inbox"), saved)
        self.assertTrue(self.app.inbox.config()["api_key_present"])
        self.assertEqual(fields.remove_key_button.cget("text"), "Undo removal")
        self.assertFalse(fields.remove_key_button.instate(["disabled"]))
        fields.remove_key_button.invoke()
        self.assertNotIn("api_key", fields.values())
        self.assertTrue(fields.gemini_enabled.get())

    def test_late_preferences_failure_preserves_key_and_all_draft_tabs(self):
        self.save_synthetic_gemini_key()
        saved = self.store.preference("inbox")
        self.app.global_settings()
        dialog = self.app.preferences_dialog
        dialog.sorting.remove_key()
        dialog.processing.group.set("Whole page")
        dialog.integration.master.set(True)
        with self.store.connect() as db:
            db.execute("""CREATE TRIGGER reject_defaults BEFORE INSERT ON preferences
                          WHEN NEW.key='default_settings'
                          BEGIN SELECT RAISE(ABORT, 'synthetic preferences failure'); END""")
        dialog.save()
        self.settle_actions(lambda: not dialog.saving)
        self.assertTrue(dialog.window.winfo_exists())
        self.assertIn("Preferences were not saved", dialog.save_status.get())
        self.assertEqual(self.store.preference("inbox"), saved)
        self.assertTrue(self.app.inbox.config()["api_key_present"])
        self.assertIsNone(self.store.preference("pdf_viewer"))
        self.assertIsNone(self.store.preference("default_settings"))
        self.assertFalse(self.store.preference("remarkable", {}).get("integration_enabled", False))
        self.assertTrue(dialog.integration.master.get())
        self.assertEqual(dialog.processing.group.get(), "Whole page")
        self.assertTrue(dialog.sorting.key_removal_pending)
        dialog.sorting.undo_key_removal()
        self.assertNotIn("api_key", dialog.sorting.values())
        self.assertTrue(dialog.sorting.gemini_enabled.get())
        dialog.cancel()
        self.assertEqual(self.store.preference("inbox"), saved)

    def test_same_path_content_change_clears_stale_review(self):
        view = self.app.inbox_view
        path = str(self.folder / "changed.pdf")
        row = {"path": path, "name": "changed.pdf", "status": "review", "signature": "first"}
        view.render([row])
        view.tree.selection_set(path)
        view.review_path, view.review_signature = path, "first"
        view.filename.set("reviewed.pdf")
        view.render([{**row, "signature": "second", "status": "ready"}])
        self.assertIsNone(view.review_path)
        self.assertTrue(view.file_button.instate(["disabled"]))
        self.assertIn("Review it again", view.feedback.get())

    def test_async_save_applies_only_connection_choices_from_save_click(self):
        self.app.global_settings()
        dialog = self.app.preferences_dialog
        dialog.sorting.mode.set("Local only")
        entered, release = threading.Event(), threading.Event()
        original_save = self.app.service.save_preferences
        def save_preferences(draft, preference, settings, integration_changes):
            entered.set()
            release.wait(3)
            return original_save(draft, preference, settings, integration_changes)
        try:
            with patch.object(self.app.service, "save_preferences", side_effect=save_preferences):
                dialog.save()
                self.assertTrue(entered.wait(1))
                self.assertTrue(dialog.saving)
                self.assertTrue(dialog.save_button.instate(["disabled"]))
                dialog.integration.master.set(True)
                dialog.cancel()
                self.assertTrue(dialog.window.winfo_exists())
                release.set()
                self.settle_actions()
        finally:
            release.set()
        self.assertFalse(any(name == "remarkable_settings" for name, _ in self.commands()))
        self.assertFalse(self.store.preference("remarkable", {}).get("integration_enabled", False))

    def test_retry_lookup_bypasses_cache_and_preserves_edited_name(self):
        view = self.app.inbox_view
        path = str(self.folder / "paper.pdf")
        row = {"path": path, "name": "paper.pdf", "status": "review", "signature": "reviewed"}
        view.render([row])
        view.tree.selection_set(path)
        view.review_path, view.review_signature = path, "reviewed"
        view.proposal = "old_proposal.pdf"
        view.filename.set("my_edited_name.pdf")
        with patch.object(self.app.inbox, "prepare", return_value={"signature": "reviewed", "proposed_filename": "new_proposal.pdf"}) as prepare:
            view.review(force=True)
            self.settle_actions(lambda: not view.busy)
        prepare.assert_called_once_with(path, force=True)
        self.assertEqual(view.filename.get(), "my_edited_name.pdf")

    def test_refresh_event_reads_rows_without_starting_a_scan_loop(self):
        self.app.workflow_events.put(("inbox_changed", {"count": 0}))
        with patch.object(self.app.inbox_view, "load_rows") as rows, patch.object(self.app.inbox_view, "refresh") as scan:
            self.app.poll()
        rows.assert_called_once()
        scan.assert_not_called()

    def test_duplicate_review_is_background_and_local_by_default(self):
        folder = self.folder / "Sorted"
        folder.mkdir()
        self.app.inbox.save_config({"library_root": str(folder)})
        window = self.app.review_library()
        entered, release = threading.Event(), threading.Event()
        def scan(*args, **kwargs):
            entered.set()
            release.wait(3)
            return []
        try:
            with patch("note_organizer.reconciliation.scan_reconciliation", side_effect=scan) as check:
                window.check()
                self.assertTrue(entered.wait(1))
                self.root.update()
                self.assertTrue(window.check_button.instate(["disabled"]))
                self.assertFalse(check.call_args.args[1]["integration_enabled"])
                release.set()
                self.settle_actions(lambda: not window.check_button.instate(["disabled"]))
        finally:
            release.set()
            window.close()
        self.assertEqual(self.store.documents(), [])
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
