"""Selectable review copies and explicit, reversible deletion of disposable PDFs."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from note_organizer import library_files
from note_organizer.storage import canonical, digest_file
from tests import test_review_controls


class LibraryReviewFileTests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait
    review = test_review_controls.ReviewControlTests.review
    duplicate_papers = test_review_controls.ReviewControlTests.duplicate_papers

    def file_review(self):
        registry, sources, paths = self.duplicate_papers()
        review = self.review()
        review.checked_scope = str(self.pc)
        review.rows = {"copies": {"id": "copies", "kind": "local_duplicate", "title": "Same paper",
            "reason": "These PDFs have the same bytes", "sources": sources,
            "local_paths": list(map(str, paths)), "actions": ["link_papers"]}}
        review.render()
        review.tree.selection_set("copies")
        review.selected()
        return review, registry, sources, paths

    def select_copy(self, review, path):
        key = next(key for key, value in review.copy_paths.items() if Path(value) == path)
        review.local_copies.selection_set(key)
        review.copy_selected()

    def test_local_rows_replace_dropdown_and_drive_actions_details_and_copy(self):
        review, registry, sources, paths = self.file_review()
        self.assertEqual(len(review.local_copies.get_children()), 2)
        self.assertNotIn("paths", review.__dict__)
        for path in reversed(paths):
            self.select_copy(review, path)
            self.assertEqual(Path(review.selected_path()), path)
            self.assertIn(str(path), review.details.get("1.0", "end"))
            self.assertIn(str(path), review.local_path_copy.tooltip.text())
            with patch.object(self.app, "open_path") as opened:
                review.open_pdf_button.invoke()
                review.open_folder_button.invoke()
            self.assertEqual(opened.call_args_list[0].args, (str(path),))
            self.assertEqual(opened.call_args_list[1].args, (str(path.parent),))
            with patch.object(review.local_copies, "clipboard_clear"), patch.object(review.local_copies, "clipboard_append") as copied:
                review.local_path_copy.invoke()
            copied.assert_called_once_with(str(path))
            self.assertFalse(review.delete_pdf_button.instate(["disabled"]))
        review.selected()
        self.assertEqual(Path(review.selected_path()), paths[0])
        review.local_copies.selection_remove(review.local_copies.selection())
        review.copy_selected()
        self.assertTrue(review.delete_pdf_button.instate(["disabled"]))
        self.assertTrue(review.open_pdf_button.instate(["disabled"]))
        self.assertTrue(review.local_path_copy.instate(["disabled"]))

    def test_cancelled_delete_identifies_exact_file_and_changes_nothing(self):
        review, registry, sources, paths = self.file_review()
        self.select_copy(review, paths[1])
        before = [path.read_bytes() for path in paths]
        with patch("note_organizer.workflow_ui.messagebox.askokcancel", return_value=False) as confirm, \
                patch.object(self.app.service, "storage_action") as recycle:
            review.delete_pdf_button.invoke()
            self.wait(lambda: not review.busy)
        self.assertIn(canonical(paths[1]), confirm.call_args.args[1])
        recycle.assert_not_called()
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertIn("cancelled", review.feedback.get())

    def test_changed_copy_is_not_confirmed_or_recycled(self):
        review, registry, sources, paths = self.file_review()
        paths[0].write_bytes(paths[0].read_bytes() + b"new edit")
        with patch("note_organizer.workflow_ui.messagebox.askokcancel") as confirm, \
                patch.object(self.app.service, "storage_action") as recycle:
            review.delete_pdf_button.invoke()
            self.wait(lambda: not review.busy)
        confirm.assert_not_called()
        recycle.assert_not_called()
        self.assertTrue(paths[0].exists())
        self.assertIn("changed", review.feedback.get())

    def test_confirmed_delete_uses_selected_copy_and_retains_notes_and_identity(self):
        review, registry, sources, paths = self.file_review()
        self.select_copy(review, paths[1])
        before_notes = self.store.entries()
        source_ids = [source["id"] for source in sources]
        # Only disposable synthetic files are removed by this mock. Production
        # always calls Windows' recycle operation, with no unlink fallback.
        with patch("note_organizer.workflow_ui.messagebox.askokcancel", return_value=True), \
                patch.object(library_files, "_recycle_windows", side_effect=lambda path, digest: Path(path).unlink()) as recycled:
            review.delete_pdf_button.invoke()
            self.wait(lambda: not review.busy and not review.check_button.instate(["disabled"]))
        recycled.assert_called_once_with(canonical(paths[1]), sources[1]["digest"])
        self.assertTrue(paths[0].exists())
        self.assertFalse(paths[1].exists())
        self.assertEqual([source["id"] for source in registry.sources()], source_ids)
        self.assertEqual(len(self.store.entries()), len(before_notes))
        records = {row["path"]: row for row in self.store.documents()}
        self.assertFalse(records[canonical(paths[0])]["missing"])
        self.assertTrue(records[canonical(paths[1])]["missing"])
        self.assertEqual(len(registry.revisions(source_ids[1])), 1)

    def test_recycle_failure_keeps_both_copies_and_actions_recover(self):
        review, registry, sources, paths = self.file_review()
        with patch("note_organizer.workflow_ui.messagebox.askokcancel", return_value=True), \
                patch.object(library_files, "_recycle_windows", side_effect=OSError("Recycle Bin unavailable")):
            review.delete_pdf_button.invoke()
            self.wait(lambda: not review.busy)
        self.assertTrue(all(path.exists() for path in paths))
        self.assertIn("unavailable", review.feedback.get())
        self.assertFalse(review.delete_pdf_button.instate(["disabled"]))
        self.assertFalse(any(row["missing"] for row in self.store.documents()))

    def test_delete_disabled_during_scan_or_without_checked_scope(self):
        review, registry, sources, paths = self.file_review()
        review.checked_scope = ""
        review.open_actions()
        self.assertTrue(review.delete_pdf_button.instate(["disabled"]))
        review.checked_scope = str(self.pc)
        with patch("note_organizer.workflow_ui.background"):
            review.check()
        self.assertTrue(review.delete_pdf_button.instate(["disabled"]))


class ReviewedPDFTests(unittest.TestCase):
    def test_confirmation_proof_rejects_outside_roots_directories_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inside = root / "scope"
            inside.mkdir()
            path = inside / "paper.pdf"
            path.write_bytes(b"disposable PDF bytes")
            proof = library_files.reviewed_pdf(path, inside)
            self.assertEqual(proof["digest"], digest_file(path))
            with self.assertRaises(ValueError):
                library_files.reviewed_pdf(path, root / "elsewhere")
            with self.assertRaises(ValueError):
                library_files.reviewed_pdf(inside, inside)
            path.write_bytes(b"changed bytes")
            with self.assertRaisesRegex(ValueError, "changed"):
                library_files.reviewed_pdf(path, inside, proof["digest"])

    def test_recycle_flags_require_recycling_and_stop_on_error(self):
        self.assertTrue(library_files.RECYCLE_FLAGS & 0x00080000)
        self.assertTrue(library_files.RECYCLE_FLAGS & 0x00100000)
        self.assertTrue(library_files.RECYCLE_FLAGS & 0x0400)
        self.assertTrue(library_files.RECYCLE_FLAGS & 0x20000000)


if __name__ == "__main__":
    unittest.main()
