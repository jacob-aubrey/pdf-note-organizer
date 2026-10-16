"""Incremental worker regressions using temporary libraries and no network."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from note_organizer.extraction import extract
from note_organizer.exporting import EXPORT_FORMAT_REVISION
from note_organizer.remarkable_sync import default_config
from note_organizer.service import Service
from note_organizer.storage import Store, canonical
from tests.test_notebook import sample_pdf
from tests.test_remarkable import fixture, folder


class ServicePerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.watched = self.root / "Research"
        self.watched.mkdir()
        self.pid = self.store.add_project(self.watched)
        self.service = Service(self.store)

    def tearDown(self):
        self.service.stop()
        self.temp.cleanup()

    def run_one_iteration(self):
        # Timers stay real; the worker's first idle boundary ends this test.
        self.service.wake = Mock()
        self.service.wake.wait.side_effect = lambda timeout: self.service.stop()
        self.service.run()

    def cloud_item(self, path, digest):
        return {"state": "synced", "path": canonical(path), "digest": digest,
                "hash": digest, "render_revision": 3}

    def test_start_queues_discovery_before_worker_can_check_cloud(self):
        def start_thread():
            self.assertTrue(self.service.sync_requested)
            self.assertEqual(self.service.commands.queue[0][0], "watch")

        with patch("note_organizer.service.threading.Thread") as thread:
            thread.return_value.start.side_effect = start_thread
            self.service.start()
        thread.return_value.start.assert_called_once()

    def test_optional_worker_owns_native_extraction_without_starting_a_job_on_init(self):
        worker = Mock()
        self.service = Service(self.store, pdf_worker=worker)
        worker.extract.assert_not_called()
        worker.render.assert_not_called()
        pdf = self.watched / "paper.pdf"
        sample_pdf(pdf)
        settings = self.store.default_settings()
        worker.extract.return_value = extract(pdf, settings)
        with patch("note_organizer.service.extract", side_effect=AssertionError("Desktop extraction must use the shared worker")):
            self.service.scan(self.store.project(self.pid), pdf)
        worker.extract.assert_called_once_with(pdf, settings)
        self.assertTrue(self.store.entries())

    def test_optional_worker_owns_cloud_rendering(self):
        worker = Mock()
        self.service = Service(self.store, pdf_worker=worker)
        source = folder("Literature")
        item, bundle = fixture(source.id)
        worker.render.return_value = bundle[item.id + ".pdf"]
        from note_organizer.combined_pdf import render_combined_pdf
        from note_organizer.cloud_notes import tablet_only_pdf
        worker.render_combined.side_effect = render_combined_pdf
        worker.tablet_only.side_effect = tablet_only_pdf
        worker.extract.side_effect = extract
        self.store.set_preference("remarkable", {**default_config(self.store.path.parent),
                                                  "integration_enabled": True, "enabled": True,
                                                  "pc_root": str(self.watched), "source_folder_id": source.id})
        self.service.remarkable.client = Mock()
        self.service.remarkable.client.library.return_value = [source, item]
        self.service.remarkable.client.pdf_bundle.return_value = bundle
        with patch("note_organizer.remarkable_sync.annotated_pdf", side_effect=AssertionError("Cloud rendering must use the shared worker")):
            self.assertTrue(self.service.remarkable.sync())
        worker.render.assert_called_once_with(item, bundle)
        worker.render_combined.assert_called_once()
        worker.tablet_only.assert_called_once_with(item, bundle)
        worker.extract.assert_called_once()
        self.assertEqual(self.store.remarkable_items()[item.id]["state"], "synced")

    def test_stop_cancels_shared_worker_and_worker_exit_shuts_it_down(self):
        worker = Mock()
        self.service = Service(self.store, pdf_worker=worker)
        self.service.remarkable.sync = Mock(return_value=False)
        self.service.export_pending = Mock()
        self.run_one_iteration()
        worker.cancel.assert_called_once()
        worker.shutdown.assert_called_once_with(wait=True)

    def test_notebook_format_change_marks_projects_once_without_reading_pdfs(self):
        self.store.export_result(self.pid, "existing-notebook")
        with patch.object(self.store, "mark_dirty", wraps=self.store.mark_dirty) as dirty, \
                patch("note_organizer.service.extract") as reader:
            self.service.upgrade_export_format()
            self.assertTrue(self.store.project(self.pid)["dirty"])
            self.store.export_result(self.pid, "new-notebook")
            self.service.upgrade_export_format()
        dirty.assert_called_once_with(self.pid)
        reader.assert_not_called()
        self.assertFalse(self.store.project(self.pid)["dirty"])
        self.assertEqual(self.store.preference("export_format_revision"), EXPORT_FORMAT_REVISION)

    def test_startup_upgrade_keeps_offline_notebook_unchanged_and_pending(self):
        offline = self.root / "Unavailable drive"
        old_output = self.root / "Existing offline notebook.docx"
        old_output.write_bytes(b"Previous notebook and personal notes")
        old_bytes = old_output.read_bytes()
        offline_id = self.store.add_project(offline, old_output)
        self.store.export_result(offline_id, "old-format")
        self.service.remarkable.sync = Mock(return_value=False)
        with patch("note_organizer.service.extract") as reader, \
                patch("note_organizer.service.export_notebook", return_value=("new-format", None)):
            self.run_one_iteration()
        reader.assert_not_called()
        self.assertTrue(self.store.project(offline_id)["dirty"])
        self.assertEqual(old_output.read_bytes(), old_bytes)
        self.assertFalse(offline.exists())
        self.assertEqual(self.store.preference("export_format_revision"), EXPORT_FORMAT_REVISION)

    def test_export_reads_text_rows_then_fetches_only_drawing_images(self):
        pdf = self.watched / "paper.pdf"
        sample_pdf(pdf)
        self.service.scan(self.store.project(self.pid), pdf)
        entries = self.store.entries()
        drawings = [e for e in entries if e["kind"] == "drawing"]
        highlight = next(e for e in entries if e["kind"] == "highlight")
        # A stored crop from an older policy must never be loaded for Word.
        with self.store.connect() as db:
            db.execute("UPDATE entries SET payload=? WHERE document_id=? AND key=?",
                       (json.dumps({**highlight, "image": "legacy-highlight-crop" * 10000}),
                        highlight["document_id"], highlight["key"]))
        with patch.object(self.store, "entries", wraps=self.store.entries) as query, \
                patch.object(self.store, "entry_image", wraps=self.store.entry_image) as images, \
                patch("note_organizer.service.export_notebook", return_value=("new-notebook", None)) as writer:
            self.service.export_pending()
        query.assert_called_once_with(project_id=self.pid, include_images=False)
        self.assertEqual({call.args for call in images.call_args_list},
                         {(e["document_id"], e["key"]) for e in drawings})
        self.assertEqual(images.call_count, len(drawings))
        written = writer.call_args.args[2]
        self.assertTrue(next(e["image"] for e in written if e["kind"] == "drawing"))
        self.assertTrue(all(not e["image"] for e in written if e["kind"] != "drawing"))

    def test_startup_and_cloud_download_share_one_full_discovery(self):
        pdf = self.watched / "new-cloud-paper.pdf"
        self.service.request_sync()
        self.service.sync = Mock()
        self.service.scan_path = Mock()
        self.service.watch = Mock()
        self.service.export_pending = Mock()

        def download(**kwargs):
            self.store.save_remarkable_item("paper", self.cloud_item(pdf, "new"))
            return True

        self.service.remarkable.sync = Mock(side_effect=download)
        self.run_one_iteration()
        self.service.sync.assert_called_once_with(force=False)
        self.service.scan_path.assert_not_called()
        self.service.watch.assert_called_once()

    def test_changed_cloud_pdf_is_scanned_without_a_full_library_walk(self):
        pdf = self.watched / "changed-paper.pdf"
        self.store.save_remarkable_item("paper", self.cloud_item(pdf, "old"))
        self.service.sync = Mock()
        self.service.scan_path = Mock()
        self.service.watch = Mock()
        self.service.export_pending = Mock()

        def download(**kwargs):
            self.store.save_remarkable_item("paper", self.cloud_item(pdf, "new"))
            return True

        self.service.remarkable.sync = Mock(side_effect=download)
        self.service.command("remarkable_sync")
        self.run_one_iteration()
        self.service.remarkable.sync.assert_called_once_with(force=True, listing_only=False)
        self.service.scan_path.assert_called_once_with(canonical(pdf))
        self.service.sync.assert_not_called()
        self.assertFalse(self.service.cloud_paths)

    def test_review_only_cloud_change_does_not_scan_local_pdfs(self):
        self.service.sync = Mock()
        self.service.scan_path = Mock()
        self.service.watch = Mock()
        self.service.export_pending = Mock()

        def review(**kwargs):
            self.store.save_remarkable_item("paper", {"state": "review", "review_pdf": "not-an-analysis-source.pdf"})
            return True

        self.service.remarkable.sync = Mock(side_effect=review)
        self.run_one_iteration()
        self.service.sync.assert_not_called()
        self.service.scan_path.assert_not_called()

    def test_new_cloud_project_gets_discovery_without_scanning_existing_projects(self):
        new_root = self.root / "New mapped folder"
        new_root.mkdir()
        self.service.sync = Mock()
        self.service.scan_path = Mock()
        self.service.watch = Mock()
        self.service.export_pending = Mock()
        added = []

        def download(**kwargs):
            added.append(self.store.add_project(new_root))
            self.store.save_remarkable_item("paper", self.cloud_item(new_root / "paper.pdf", "new"))
            return True

        self.service.remarkable.sync = Mock(side_effect=download)
        self.run_one_iteration()
        self.service.sync.assert_called_once_with(added[0], False)

    def test_multiple_discovery_requests_and_commands_share_one_scan(self):
        self.service.request_sync()
        self.service.request_sync()
        self.service.command("sync")
        self.service.command("sync", None)
        self.service.sync = Mock()
        self.service.remarkable.sync = Mock(return_value=False)
        self.service.export_pending = Mock()
        self.run_one_iteration()
        self.service.sync.assert_called_once_with(force=False)

    def test_watch_keeps_observer_when_only_documents_or_settings_change(self):
        with patch("note_organizer.service.Observer") as factory:
            factory.return_value.is_alive.return_value = True
            self.service.watch()
            self.store.mark_dirty(self.pid)
            self.service.watch()
            factory.assert_called_once()
            factory.return_value.stop.assert_not_called()
            new_root = self.root / "Another root"
            new_root.mkdir()
            self.store.add_project(new_root)
            self.service.watch()
            self.assertEqual(factory.call_count, 2)
            factory.return_value.stop.assert_called_once()

    def test_unchanged_batch_reads_errors_and_exclusions_once(self):
        for number in range(4):
            pdf = self.watched / f"paper-{number}.pdf"
            sample_pdf(pdf)
            self.service.scan(self.store.project(self.pid), pdf)
        project = self.store.project(self.pid)
        Path(project["output"]).write_bytes(b"Existing notebook")
        self.store.export_result(self.pid, "unchanged")
        with patch.object(self.store, "errors", wraps=self.store.errors) as errors, \
                patch.object(self.store, "preference", wraps=self.store.preference) as preference, \
                patch("note_organizer.service.extract", wraps=extract) as reader:
            self.service.sync()
        reader.assert_not_called()
        errors.assert_called_once_with(self.pid)
        self.assertEqual(sum(call.args[0] == "remarkable" for call in preference.call_args_list), 1)
        self.assertIsNone(self.service.scan_context)

    def test_upgrade_activity_is_visible_and_restored_when_extraction_fails(self):
        pdf = self.watched / "paper.pdf"
        sample_pdf(pdf)
        self.service.scan(self.store.project(self.pid), pdf)
        with self.store.connect() as db:
            db.execute("UPDATE documents SET settings='older-extraction-format'")

        def fail(*args):
            self.assertEqual(self.service.activity_state["phase"], "Updating saved notes")
            self.assertEqual(self.service.activity_state["detail"], pdf.name)
            raise InterruptedError("Stopped intentionally")

        with patch("note_organizer.service.extract", side_effect=fail):
            with self.assertRaises(InterruptedError):
                self.service.scan(self.store.project(self.pid), pdf)
        self.assertIsNone(self.service.activity_state)
        self.assertTrue(self.store.entries())

    def test_cloud_activity_clears_when_check_fails(self):
        def fail(**kwargs):
            self.assertEqual(self.service.activity_state["phase"], "Checking reMarkable")
            raise OSError("Synthetic offline cloud")

        self.service.remarkable.sync = Mock(side_effect=fail)
        with self.assertRaises(OSError):
            self.service.check_cloud()
        self.assertIsNone(self.service.activity_state)
        self.assertFalse(self.service.cloud_busy)

    def test_cloud_download_messages_update_busy_detail_without_database_reads(self):
        def check(**kwargs):
            self.service.post("Downloading reMarkable PDF: synthetic-paper…")
            self.assertEqual(self.service.activity_state["detail"], "Downloading reMarkable PDF: synthetic-paper…")
            return False

        self.service.remarkable.sync = Mock(side_effect=check)
        self.service.check_cloud()
        self.assertIsNone(self.service.activity_state)

    def test_scan_batch_context_clears_after_an_unexpected_walk_error(self):
        with patch("note_organizer.service.os.walk", side_effect=OSError("Synthetic unavailable filesystem")):
            with self.assertRaises(OSError):
                self.service.sync()
        self.assertIsNone(self.service.scan_context)
        self.assertIsNone(self.service.activity_state)

    def test_sync_counts_finished_pdfs_from_one_inventory_and_accounts_for_failures(self):
        import os
        for name in ("first.pdf", "second.pdf", "third.pdf"):
            sample_pdf(self.watched / name)
        states, final = [], []
        def scan(project, path, force):
            states.append(dict(self.service.activity_state))
            if len(states) == 2:
                raise OSError("Synthetic unreadable PDF")
        with patch("note_organizer.service.os.walk", wraps=os.walk) as walk, \
                patch.object(self.service, "scan", side_effect=scan), \
                patch.object(self.service, "export_pending", side_effect=lambda: final.append(self.service.activity_state)), \
                self.assertLogs(level="ERROR"):
            self.service.sync()
        walk.assert_called_once()
        self.assertEqual([(state["current"], state["total"]) for state in states], [(0, 3), (1, 3), (2, 3)])
        self.assertEqual((final[-1]["current"], final[-1]["total"]), (3, 3))
        self.assertEqual(self.store.preference("sync_summary")["pdf_errors"], 1)
        self.assertIsNone(self.service.activity_state)

    def test_sync_preserves_batch_count_during_pdf_extraction(self):
        sample_pdf(self.watched / "first.pdf")
        sample_pdf(self.watched / "second.pdf")
        states = []
        def read(*args):
            states.append(dict(self.service.activity_state))
            return extract(*args)
        with patch("note_organizer.service.extract", side_effect=read):
            self.service.sync()
        self.assertEqual([(state["current"], state["total"]) for state in states], [(0, 2), (1, 2)])
        self.assertTrue(all(state["phase"] == "Reading PDF" for state in states))

    def test_notebook_progress_advances_only_after_each_export(self):
        second = self.root / "Second"
        second.mkdir()
        self.store.add_project(second)
        states = []
        def export(*args, **kwargs):
            states.append(dict(self.service.activity_state))
            return "new-notebook", None
        with patch("note_organizer.service.export_notebook", side_effect=export):
            self.service.export_pending()
        self.assertEqual([(state["current"], state["total"]) for state in states], [(0, 2), (1, 2)])
        self.assertIsNone(self.service.activity_state)


if __name__ == "__main__":
    unittest.main()
