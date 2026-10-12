"""Combined viewing stays off Tk; explicit exports bind overwrite consent."""
from concurrent.futures import Future
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from note_organizer.storage import digest_file
from tests import test_ui_audit


class CombinedUIExportTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def tearDown(self):
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        test_ui_audit.UIAuditTests.tearDown(self)

    def show_note(self, **extra):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        future = Future()
        future.set_result([{"document_id": "doc", "key": "note", "path": str(self.pc / "virtual.pdf"),
                            "kind": "highlight", "quote": "Saved note", "page": 3, "page_count": 12,
                            "logical_paper_id": "paper-id", "combined_view_path": str(self.pc / "original.pdf"),
                            "combined_view_page": 3, **extra}])
        app.finish_query(app.query_generation, None, future)
        self.root.update()
        return app

    def test_open_materializes_once_off_tk_then_navigates_to_verified_physical_page(self):
        app = self.show_note()
        entered, release = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        worker_threads = []
        resolved = self.folder / "private-combined.pdf"
        def materialize(store, reference, **kwargs):
            worker_threads.append(threading.get_ident())
            self.assertEqual(reference, "paper-id")
            entered.set()
            release.wait(3)
            return resolved
        try:
            with patch.object(app.pdf_worker, "materialize", side_effect=materialize) as render, \
                    patch("note_organizer.ui.open_pdf_page", return_value=("Opened", True)) as launch:
                app.open_source()
                self.assertTrue(entered.wait(1))
                for _ in range(8):
                    app.open_source()
                heartbeat = []
                self.root.after(0, lambda: heartbeat.append(True))
                self.root.update()
                self.assertTrue(heartbeat)
                self.assertEqual(render.call_count, 1)
                self.assertNotEqual(worker_threads, [main_thread])
                self.assertEqual(app.query_executor.submit(lambda: "search live").result(timeout=1), "search live")
                launch.assert_not_called()
                release.set()
                self.pump_until(lambda: launch.called)
                launch.assert_called_once_with(resolved, 3, app.viewer_preference)
        finally:
            release.set()

    def test_failed_combination_does_not_open_an_unverified_pdf(self):
        app = self.show_note()
        with patch.object(app.pdf_worker, "materialize", side_effect=ValueError("Page order needs review")), \
                patch("note_organizer.ui.open_pdf_page") as launch, \
                patch("note_organizer.ui.messagebox.showerror") as error:
            app.open_source()
            self.pump_until(lambda: error.called)
            launch.assert_not_called()
            self.assertIn("Page order needs review", error.call_args.args[1])

    def test_cloud_review_opens_retained_copy_without_attempting_unverified_combination(self):
        app = self.app
        retained = self.folder / 'needs-review.pdf'
        retained.write_bytes(b'Retained synthetic review copy')
        app.cloud_review.insert('', 'end', iid='review-item', values=('Paper', '/Literature', 'Different edition'))
        app.cloud_review.selection_set('review-item')
        with patch.object(app.view, 'remarkable_items', return_value={'review-item': {'review_pdf': str(retained)}}), \
                patch.object(app.pdf_worker, 'materialize') as render, \
                patch('note_organizer.ui.open_pdf_page', return_value=('Opened retained copy', True)) as launch:
            app.open_cloud_review()
            render.assert_not_called()
            launch.assert_called_once_with(str(retained), 1, app.viewer_preference)

    def test_unavailable_mapping_stops_before_resolver_and_keeps_saved_note(self):
        app = self.show_note(combined_view_unavailable="This tablet page has no verified PC counterpart.")
        with patch.object(app.pdf_worker, "materialize") as render, \
                patch("note_organizer.ui.messagebox.showerror") as error:
            app.open_source()
            render.assert_not_called()
            error.assert_called_once()
            self.assertIn("Saved note", app.preview_text.get("1.0", "end"))

    def test_export_new_file_requires_absence_and_coalesces_pending_inspection(self):
        app = self.show_note()
        destination = self.folder / "annotated.pdf"
        entered, release = threading.Event(), threading.Event()
        def export(store, reference, target, **kwargs):
            self.assertEqual(reference, "paper-id")
            self.assertEqual(kwargs["expected_digest"], None)
            self.assertTrue(kwargs["require_absent"])
            entered.set()
            release.wait(3)
            Path(target).write_bytes(b"Explicit combined export")
            return Path(target)
        try:
            with patch("note_organizer.ui.filedialog.asksaveasfilename", return_value=str(destination)) as chooser, \
                    patch.object(app.pdf_worker, "export_combined", side_effect=export) as publish:
                app.export_note_pdf()
                app.export_note_pdf()
                self.assertEqual(chooser.call_count, 1)
                self.pump_until(entered.is_set)
                self.assertEqual(publish.call_count, 1)
                release.set()
                self.pump_until(lambda: not app.pdf_export_busy)
                self.assertEqual(destination.read_bytes(), b"Explicit combined export")
        finally:
            release.set()

    def test_existing_export_confirmation_receives_exact_snapshot_digest(self):
        app = self.show_note()
        destination = self.folder / "annotated.pdf"
        destination.write_bytes(b"Earlier explicit export")
        expected = digest_file(destination)
        with patch("note_organizer.ui.filedialog.asksaveasfilename", return_value=str(destination)), \
                patch("note_organizer.ui.messagebox.askokcancel", return_value=True) as confirm, \
                patch.object(app.pdf_worker, "export_combined", return_value=destination) as publish:
            app.export_note_pdf()
            self.pump_until(lambda: not app.pdf_export_busy)
            confirm.assert_called_once()
            self.assertEqual(publish.call_args.kwargs["expected_digest"], expected)
            self.assertFalse(publish.call_args.kwargs["require_absent"])

    def test_declining_export_overwrite_keeps_existing_pdf_and_resets_busy(self):
        app = self.show_note()
        destination = self.folder / "annotated.pdf"
        destination.write_bytes(b"Existing PDF")
        with patch("note_organizer.ui.filedialog.asksaveasfilename", return_value=str(destination)), \
                patch("note_organizer.ui.messagebox.askokcancel", return_value=False), \
                patch.object(app.pdf_worker, "export_combined") as publish:
            app.export_note_pdf()
            self.pump_until(lambda: not app.pdf_export_busy)
            publish.assert_not_called()
            self.assertEqual(destination.read_bytes(), b"Existing PDF")


if __name__ == "__main__":
    unittest.main()
