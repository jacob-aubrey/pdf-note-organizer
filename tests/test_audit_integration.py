"""Disposable integration checks for serialized settings and isolated review."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import fitz

from note_organizer.inbox import InboxController
from note_organizer.pdf_worker import PDFWorker
from note_organizer import pdf_worker, remarkable_cloud
from note_organizer.reconciliation import scan_reconciliation
from note_organizer.remarkable_cloud import CloudError, atomic_write
from note_organizer.remarkable_sync import RemarkableSync, default_config, retained_recovery_paths
from note_organizer.service import Service
from note_organizer.storage import DEFAULT_SETTINGS, Store, canonical, timestamp
from note_organizer.workflow_ui import ReconciliationWindow
from note_organizer.ui import App
from tests import test_remarkable as cloud_fixtures


TEMP_ROOT = Path(__file__).resolve().parents[1] / "tmp" / "combined-tests"


def inspect_with_source_change(path):
    """Cause a real file change inside only a disposable spawned process."""
    from note_organizer.storage import digest_file
    def read_then_change(value):
        digest = digest_file(value)
        source = Path(value)
        source.write_bytes(source.read_bytes() + b"\n% changed during inspection\n")
        return digest
    with patch("note_organizer.storage.digest_file", side_effect=read_then_change):
        return pdf_worker._inspect(path)


def inspect_cancel_at_completion(path):
    """Cancel the shared process event at its last filesystem boundary."""
    version = pdf_worker._file_version
    calls = 0
    def observe(value):
        nonlocal calls
        result = version(value)
        calls += 1
        if calls == 2:
            pdf_worker._cancel_event.set()
        return result
    with patch.object(pdf_worker, "_file_version", side_effect=observe):
        return pdf_worker._inspect(path)


class PreferencesIntegrationTests(unittest.TestCase):
    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="preferences-integration-", dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.incoming, self.library, self.data = (self.root / name for name in ("Inbox", "Library", "data"))
        self.incoming.mkdir()
        self.library.mkdir()
        self.store = Store(self.data / "library.sqlite3")
        self.inbox = InboxController(self.store, self.data)
        self.inbox.save_config({"watch_folder": str(self.incoming), "library_root": str(self.library),
                                "naming_mode": "Basic", "enabled": False})
        self.service = Service(self.store, interval=3600)
        self.service.inbox = self.inbox
        self.service.upgrade_export_format = Mock()
        self.service.watch = Mock()
        self.service.sync = Mock()
        self.service.check_cloud = Mock(return_value=False)
        self.service.export_pending = Mock()
        self.store.set_preference("pdf_viewer", {"viewer": "system"})
        self.store.set_preference("default_settings", dict(DEFAULT_SETTINGS))
        self.store.set_preference("remarkable", {"integration_enabled": False, "source_folder_id": "saved-source",
                                                "pc_root": str(self.library), "mappings": {"saved": str(self.library)}})

    def tearDown(self):
        self.service.stop()
        if self.service.thread:
            self.service.thread.join(timeout=5)
            self.assertFalse(self.service.thread.is_alive())
        self.inbox.stop()
        self.temp.cleanup()

    def draft(self):
        return {"naming_mode": "Automatic", "online_metadata_lookup_enabled": False}

    def choices(self):
        return self.draft(), {"viewer": "adobe"}, {"grouping": "Whole page", "notebook_style": "Detailed"}, {"send_new_pdfs": True}

    def preferences(self):
        return {key: self.store.preference(key) for key in ("inbox", "pdf_viewer", "default_settings", "remarkable")}

    def test_late_failure_rolls_back_all_tabs_review_invalidation_and_cached_generation(self):
        path = self.incoming / "reviewed.pdf"
        with self.store.connect() as db:
            db.execute("INSERT INTO inbox_items VALUES(?,?,?,?,?,?,?)",
                       (canonical(path), "saved-signature", "review", '{"title":"Saved title"}', "Saved.pdf", "", timestamp()))
            db.execute("""CREATE TRIGGER reject_last_tab BEFORE INSERT ON preferences
                          WHEN NEW.key='remarkable'
                          BEGIN SELECT RAISE(ABORT,'late preferences failure'); END""")
        before, generation = self.preferences(), self.inbox._metadata_generation
        observed = {"saved": "observation"}
        self.inbox._observed = dict(observed)
        choices = list(self.choices())
        choices[0] = {**choices[0], "api_key": "synthetic-new-key", "gemini_enabled": True}
        with patch("note_organizer.inbox._protect_for_current_windows_user", return_value="synthetic-protected-key"), \
             patch("note_organizer.inbox._unprotect_for_current_windows_user", return_value="synthetic-new-key"):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "late preferences failure"):
                self.service.apply_preferences(*choices)
        self.assertEqual(self.preferences(), before)
        self.assertEqual(self.inbox.config()["naming_mode"], "Basic")
        self.assertEqual(self.inbox._metadata_generation, generation)
        self.assertEqual(self.inbox._observed, observed)
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM inbox_items WHERE path=?", (canonical(path),)).fetchone()
        self.assertEqual((row["status"], row["details"], row["proposed_filename"]),
                         ("review", '{"title":"Saved title"}', "Saved.pdf"))

    def test_live_worker_serializes_prior_cloud_edits_and_preferences_on_one_thread(self):
        entered, release, queued = threading.Event(), threading.Event(), threading.Event()
        self.service.check_cloud.side_effect = lambda: entered.set() or release.wait(timeout=5) or False
        real_command, real_apply = self.service.command, self.service.apply_preferences
        writes = []
        def command(name, *args):
            real_command(name, *args)
            if name == "preferences":
                queued.set()
        def apply(*args):
            writes.append(threading.get_ident())
            return real_apply(*args)
        self.service.command, self.service.apply_preferences = command, apply
        self.service.start()
        with ThreadPoolExecutor(max_workers=1) as caller:
            try:
                self.assertTrue(entered.wait(timeout=2))
                self.service.command("remarkable_settings", {"source_folder_id": "newer-source"})
                pending = caller.submit(self.service.save_preferences, *self.choices())
                self.assertTrue(queued.wait(timeout=2))
                self.assertEqual(self.store.preference("remarkable")["source_folder_id"], "saved-source")
                release.set()
                result = pending.result(timeout=5)
            finally:
                release.set()
        self.assertEqual(writes, [self.service.thread.ident])
        self.assertEqual(result["naming_mode"], "Automatic")
        saved = self.store.preference("remarkable")
        self.assertEqual(saved["source_folder_id"], "newer-source")
        self.assertEqual(saved["mappings"], {"saved": str(self.library)})
        self.assertTrue(saved["send_new_pdfs"])

    def test_shutdown_cancels_pending_save_without_any_preferences_commit(self):
        entered, release, queued = threading.Event(), threading.Event(), threading.Event()
        self.service.check_cloud.side_effect = lambda: entered.set() or release.wait(timeout=5) or False
        real_command = self.service.command
        saved_future = []
        def command(name, *args):
            real_command(name, *args)
            if name == "preferences":
                saved_future.append(args[1])
                queued.set()
        self.service.command = command
        before = self.preferences()
        self.service.start()
        with ThreadPoolExecutor(max_workers=1) as caller:
            try:
                self.assertTrue(entered.wait(timeout=2))
                pending = caller.submit(self.service.save_preferences, *self.choices())
                self.assertTrue(queued.wait(timeout=2))
                self.service.stop()
                with self.assertRaisesRegex(InterruptedError, "closing"):
                    pending.result(timeout=2)
                self.assertTrue(saved_future[0].cancelled())
            finally:
                release.set()
        self.assertEqual(self.preferences(), before)

    def test_shutdown_waits_for_an_already_running_save_and_reports_committed_result(self):
        entered, release = threading.Event(), threading.Event()
        real_apply = self.service.apply_preferences
        def apply(*args):
            entered.set()
            release.wait(timeout=5)
            return real_apply(*args)
        self.service.apply_preferences = apply
        self.service.start()
        with ThreadPoolExecutor(max_workers=1) as caller:
            try:
                pending = caller.submit(self.service.save_preferences, *self.choices())
                self.assertTrue(entered.wait(timeout=2))
                self.service.stop()
                with self.assertRaises(TimeoutError):
                    pending.result(timeout=.35)
                release.set()
                result = pending.result(timeout=5)
            finally:
                release.set()
        self.assertEqual(result["naming_mode"], "Automatic")
        self.assertEqual(self.store.preference("pdf_viewer"), {"viewer": "adobe"})
        self.assertEqual(self.store.preference("default_settings")["grouping"], "Whole page")

    def test_shutdown_rejects_late_save_when_no_worker_is_alive(self):
        before = self.preferences()
        self.service.stop()
        with self.assertRaisesRegex(InterruptedError, "closing"):
            self.service.save_preferences(*self.choices())
        self.assertEqual(self.preferences(), before)

    def test_completed_operation_timeout_is_propagated_without_rewaiting(self):
        # Bound the broken wait to two iterations so a regression cannot leave
        # a live infinite-spin thread behind in the test runner.
        future = Mock()
        future.done.return_value = True
        timed_waits = []
        def result(timeout=None):
            if timeout is not None:
                timed_waits.append(timeout)
                if len(timed_waits) > 1:
                    raise RuntimeError("incorrectly waited again")
            raise TimeoutError("completed save timed out")
        future.result.side_effect = result
        self.service.thread = Mock()
        self.service.thread.is_alive.return_value = True
        try:
            with patch("note_organizer.service.Future", return_value=future), patch.object(self.service, "command"):
                with self.assertRaisesRegex(TimeoutError, "completed save timed out"):
                    self.service.save_preferences(*self.choices())
        finally:
            self.service.thread = None
        self.assertEqual(timed_waits, [.25])

    def test_successful_commit_at_wait_timeout_boundary_returns_its_saved_result(self):
        future = Mock()
        future.done.return_value = True
        saved = {"naming_mode": "Automatic"}
        future.result.side_effect = [TimeoutError("wait boundary"), saved]
        self.assertEqual(self.service.wait_for_action(future), saved)
        self.assertEqual(future.result.call_args_list[1].kwargs, {})

    def test_relocation_updates_inbox_snapshot_under_its_lock_using_public_method(self):
        project_id = self.store.add_project(self.library)
        destination = self.root / "Moved library"
        destination.mkdir()
        real_relocate, real_snapshot = self.store.relocate_project, self.inbox.set_config_snapshot
        order = []
        def relocate(*args):
            self.assertTrue(self.inbox._lock._is_owned())
            order.append("relocate")
            return real_relocate(*args)
        def snapshot(config):
            self.assertTrue(self.inbox._lock._is_owned())
            self.assertEqual(config["library_root"], canonical(destination))
            order.append("snapshot")
            return real_snapshot(config)
        self.store.relocate_project = relocate
        self.inbox.set_config_snapshot = snapshot
        self.service.check_cloud.side_effect = lambda: self.service.stop() or False
        self.service.command("relocate", project_id, str(destination))
        self.service.run()
        self.assertEqual(order, ["relocate", "snapshot"])
        self.assertEqual(self.inbox.config()["library_root"], canonical(destination))
        self.assertEqual(self.store.project(project_id)["root"], canonical(destination))


class IsolatedReviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="review-integration-", dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.library = self.root / "Library"
        self.library.mkdir()
        self.path = self.library / "synthetic paper.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((60, 80), "Synthetic highlighted result")
            page.add_highlight_annot(page.search_for("highlighted result"))
            pdf.set_metadata({"title": "Synthetic metadata title"})
            pdf.save(self.path)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.worker = PDFWorker()

    def tearDown(self):
        self.worker.shutdown(wait=True)
        self.temp.cleanup()

    def test_inspection_uses_spawned_process_returns_annotation_count_and_preserves_pdf(self):
        before = self.path.read_bytes()
        digest, metadata, count, error = self.worker.inspect(self.path)
        self.assertEqual(digest, hashlib.sha256(before).hexdigest())
        self.assertEqual(metadata["title"], "Synthetic metadata title")
        self.assertEqual((count, error), (1, ""))
        process = next(iter(self.worker._pool._processes.values()))
        self.assertNotEqual(process.pid, os.getpid())
        self.assertEqual(self.path.read_bytes(), before)

    def test_malformed_pdf_becomes_read_error_and_process_can_inspect_next_file(self):
        malformed = self.library / "malformed.pdf"
        malformed.write_bytes(b"Not a PDF")
        before = self.store.path.read_bytes()
        rows = scan_reconciliation(self.store, {"integration_enabled": False}, local_root=self.library,
                                   inspect_pdf=self.worker.inspect)
        failures = [row for row in rows if row["kind"] == "local_read_error"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["local_paths"], [canonical(malformed)])
        self.assertIn("Could not inspect", failures[0]["reason"])
        self.assertEqual(self.worker.inspect(self.path)[2], 1)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_password_pdf_returns_explicit_uninspected_response(self):
        locked = self.library / "locked.pdf"
        with fitz.open() as pdf:
            pdf.new_page()
            pdf.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="synthetic-owner", user_pw="synthetic-user")
        digest, metadata, annotations, error = self.worker.inspect(locked)
        self.assertEqual(digest, hashlib.sha256(locked.read_bytes()).hexdigest())
        self.assertIsInstance(metadata, dict)
        self.assertIsNone(annotations)
        self.assertIn("requires a password", error)

    def test_source_change_inside_real_process_rejects_inspection(self):
        with self.assertRaisesRegex(OSError, "changed during comparison"):
            self.worker._call(inspect_with_source_change, str(self.path))

    def test_reconciliation_reports_changed_inspector_response(self):
        original = hashlib.sha256(self.path.read_bytes()).hexdigest()
        rows = scan_reconciliation(self.store, {"integration_enabled": False}, local_root=self.library,
             inspect_pdf=lambda _: ("different-digest", {"title": "Changed"}, 2, ""))
        failures = [row for row in rows if row["kind"] == "local_read_error"]
        self.assertEqual(len(failures), 1)
        self.assertIn("changed during comparison", failures[0]["reason"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), original)

    def test_cancel_before_inspection_does_not_spawn_native_process(self):
        self.worker.cancel()
        with self.assertRaises(InterruptedError):
            self.worker.inspect(self.path)
        self.assertIsNone(self.worker._pool)

    def test_cancel_at_process_completion_rejects_native_result(self):
        with self.assertRaises(InterruptedError):
            self.worker._call(inspect_cancel_at_completion, str(self.path))

    def test_review_cancel_during_last_inspector_call_rejects_scan_result(self):
        cancelled = threading.Event()
        def inspect(path):
            result = self.worker.inspect(path)
            cancelled.set()
            return result
        with self.assertRaises(InterruptedError):
            scan_reconciliation(self.store, {"integration_enabled": False}, cancelled.is_set,
                                local_root=self.library, inspect_pdf=inspect)

    def test_review_window_passes_isolated_inspector_and_cancellation_to_background_scan(self):
        window = ReconciliationWindow.__new__(ReconciliationWindow)
        window.app = SimpleNamespace(store=self.store, pdf_worker=self.worker,
                                     cloud_config=lambda: {"integration_enabled": False})
        window.scope = Mock()
        window.scope.get.return_value = str(self.library)
        window.feedback, window.check_button = Mock(), Mock()
        window.busy = False
        window.open_actions = Mock()
        window.set_review_status = Mock()
        window.cancelled = threading.Event()
        window.scan_generation = 0
        with patch("note_organizer.workflow_ui.background") as background, patch("note_organizer.reconciliation.scan_reconciliation", return_value=[]) as scan:
            window.check()
            background.call_args.args[1]()
        self.assertEqual(scan.call_args.kwargs["inspect_pdf"], self.worker.inspect)
        self.assertEqual(scan.call_args.kwargs["local_root"], str(self.library))
        cancelled = scan.call_args.args[2]
        self.assertFalse(cancelled())
        window.cancelled.set()
        self.assertTrue(cancelled())


class GuardedRecoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="guarded-integration-", dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        self.path = self.root / "known managed [id].pdf"
        self.original = b"Known previous managed output"
        self.path.write_bytes(self.original)
        self.digest = hashlib.sha256(self.original).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    @unittest.skipUnless(os.name == "nt", "Mandatory Windows file guards")
    def test_failed_preserved_cleanup_reports_retained_original_location(self):
        with patch.object(remarkable_cloud, "_delete_guarded", side_effect=PermissionError("Synthetic preserved cleanup denial")):
            retained = atomic_write(self.path, b"Verified new output", expected_digest=self.digest)
        preserved = [path for path in self.root.iterdir() if path.name.endswith(".preserved")]
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].read_bytes(), self.original)
        self.assertEqual(self.path.read_bytes(), b"Verified new output")
        self.assertEqual(retained, preserved[0])

    @unittest.skipUnless(os.name == "nt", "Mandatory Windows file guards")
    def test_stale_expected_digest_preserves_original_and_does_not_create_recovery_artifacts(self):
        self.path.write_bytes(b"Concurrent edit already saved")
        with self.assertRaises(CloudError):
            atomic_write(self.path, b"Cloud", expected_digest=self.digest)
        self.assertEqual(self.path.read_bytes(), b"Concurrent edit already saved")
        self.assertEqual(list(self.root.iterdir()), [self.path])

    @unittest.skipUnless(os.name == "nt", "Mandatory Windows file guards")
    def test_successful_sync_persists_recovery_location_until_original_is_removed(self):
        store = Store(self.root / "data" / "library.sqlite3")
        post = Mock()
        engine = RemarkableSync(store, threading.Event(), post)
        source = cloud_fixtures.folder("Literature")
        item, bundle = cloud_fixtures.fixture(source.id)
        # Ordinary sync now reuses originals without replacing a permanent
        # reading PDF. Review PDF publication still needs recovery protection.
        bundle[next(name for name in bundle if name.endswith('.rm'))] = b'unsupported scene'
        engine.client = Mock()
        engine.client.library.return_value = [source, item]
        engine.client.pdf_bundle.return_value = bundle
        config = {**default_config(store.path.parent), "integration_enabled": True,
                  "enabled": True, "pc_root": str(self.root), "source_folder_id": source.id}
        store.set_preference("remarkable", config)
        self.assertTrue(engine.sync())
        initial = store.remarkable_items()[item.id]
        old_output = Path(initial["review_pdf"]).read_bytes()
        item.hash = "b" * 64
        with patch.object(remarkable_cloud, "_delete_guarded", side_effect=PermissionError("Synthetic cleanup denial")):
            self.assertTrue(engine.sync())
        saved = store.remarkable_items()[item.id]
        self.assertEqual(saved["state"], "review")
        self.assertEqual(saved["hash"], item.hash)
        self.assertIsInstance(saved["recovery_paths"], list)
        self.assertEqual(len(saved["recovery_paths"]), 1)
        retained = Path(saved["recovery_paths"][0])
        self.assertEqual(retained.read_bytes(), old_output)
        self.assertTrue(any(str(retained) in call.args[0] for call in post.call_args_list))
        self.assertFalse(engine.sync())
        self.assertEqual(store.remarkable_items()[item.id]["recovery_paths"], [str(retained)])
        retained.unlink()
        self.assertFalse(engine.sync())
        self.assertEqual(store.remarkable_items()[item.id]["recovery_paths"], [])
        self.assertEqual(engine.client.pdf_bundle.call_count, 2)

    def test_inaccessible_known_recovery_copy_keeps_its_evidence(self):
        paths = [str(self.path)]
        with patch.object(Path, "stat", side_effect=PermissionError("Synthetic access denial")):
            self.assertEqual(retained_recovery_paths(paths), paths)

    def test_persistent_recovery_summary_ignores_malformed_nonarray_fields(self):
        app = SimpleNamespace(view=Mock())
        app.view.remarkable_items.return_value = {
            "valid": {"recovery_paths": [str(self.path), str(self.path)]},
            "missing": {"recovery_paths": None},
            "malformed": {"recovery_paths": str(self.root / "not an array.preserved")},
        }
        self.assertEqual(App.saved_recovery_paths(app), [str(self.path)])


if __name__ == "__main__":
    unittest.main()
