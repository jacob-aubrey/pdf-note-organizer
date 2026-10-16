"""Visible review work, ordinary multi-selection, and exact selected actions."""
from pathlib import Path
import unittest
from unittest.mock import patch

from note_organizer import library_files
from note_organizer.storage import canonical
from tests import test_library_review_files, test_review_controls


class LibraryReviewUpdatesTests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait
    review = test_review_controls.ReviewControlTests.review
    duplicate_papers = test_review_controls.ReviewControlTests.duplicate_papers
    file_review = test_library_review_files.LibraryReviewFileTests.file_review

    def three_copies(self):
        review, registry, sources, paths = self.file_review()
        third = self.pc / "third.pdf"
        third.write_bytes(paths[0].read_bytes())
        paths.append(third)
        sources.append(registry.register_local(third))
        review.rows["copies"]["local_paths"].append(str(third))
        review.selected()
        return review, registry, sources, paths

    def show(self, review):
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        review.window.geometry("1000x700+0+0")
        review.window.deiconify()
        self.root.update()

    def choose(self, review, indices):
        review.local_copies.selection_set([str(index) for index in indices])
        review.copy_selected()

    def test_control_and_shift_click_select_copies_and_selection_survives_refresh(self):
        review, _, _, _ = self.three_copies()
        self.show(review)
        tree = review.local_copies
        def click(row, state=0):
            x, y, width, height = tree.bbox(str(row))
            tree.event_generate("<ButtonPress-1>", x=x+12, y=y+height//2, state=state)
            tree.event_generate("<ButtonRelease-1>", x=x+12, y=y+height//2, state=state)
            self.root.update()
        click(0)
        click(2, 4)  # Control toggles an independent selection.
        self.assertEqual(set(tree.selection()), {"0", "2"})
        review.selected()
        self.assertEqual(set(tree.selection()), {"0", "2"})
        self.assertFalse(review.link_button.instate(["disabled"]))
        click(2, 4)
        self.assertEqual(tree.selection(), ("0",))
        click(0)
        click(2, 1)  # Shift selects a range.
        self.assertEqual(set(tree.selection()), {"0", "1", "2"})
        self.assertTrue(review.open_pdf_button.instate(["disabled"]))
        self.assertFalse(review.delete_pdf_button.instate(["disabled"]))

    def test_link_uses_only_the_selected_subset(self):
        review, registry, sources, paths = self.three_copies()
        self.choose(review, [0, 2])
        with patch("note_organizer.workflow_ui.messagebox.askokcancel", return_value=True) as confirm:
            review.link_button.invoke()
            self.wait(lambda: registry.latest_link_operation() is not None and not review.checking)
        identities = {source["id"]: source["paper_id"] for source in registry.sources()}
        self.assertEqual(identities[sources[0]["id"]], identities[sources[2]["id"]])
        self.assertNotEqual(identities[sources[0]["id"]], identities[sources[1]["id"]])
        self.assertIn(canonical(paths[0]), confirm.call_args.args[1])
        self.assertIn(canonical(paths[2]), confirm.call_args.args[1])
        self.assertNotIn(canonical(paths[1]), confirm.call_args.args[1])

    def test_batch_delete_confirmation_lists_only_selection_and_can_cancel(self):
        review, _, _, paths = self.three_copies()
        self.choose(review, [0, 2])
        with patch.object(self.app.service, "storage_action") as recycled:
            review.delete_pdf_button.invoke()
            self.wait(lambda: getattr(review, "confirmation", None) is not None)
            text = review.confirmation.details.text.get("1.0", "end")
            self.assertIn(canonical(paths[0]), text)
            self.assertIn(canonical(paths[2]), text)
            self.assertNotIn(canonical(paths[1]), text)
            review.confirmation.cancel_button.invoke()
        recycled.assert_not_called()
        self.assertTrue(all(path.exists() for path in paths))
        self.assertFalse(review.busy)
        self.assertEqual(set(review.local_copies.selection()), {"0", "2"})

    def test_batch_delete_recycles_selected_files_and_reports_partial_failure(self):
        review, registry, sources, paths = self.three_copies()
        self.choose(review, [0, 2])
        before_notes = len(self.store.entries())
        def recycle(path, digest):
            if canonical(path) == canonical(paths[0]):
                raise OSError("Synthetic locked PDF")
            Path(path).unlink()  # Only disposable test files; production requires recycling.
        with patch.object(library_files, "_recycle_windows", side_effect=recycle) as recycled:
            review.update_more_menu()
            index = next(index for index, control in review.menu_actions if control == review.delete_pdf_button)
            review.more_menu.invoke(index)
            self.wait(lambda: getattr(review, "confirmation", None) is not None)
            review.confirmation.confirm_button.invoke()
            self.wait(lambda: not review.busy and not review.checking)
        self.assertEqual({call.args[0] for call in recycled.call_args_list}, {canonical(paths[0]), canonical(paths[2])})
        self.assertTrue(paths[0].exists())
        self.assertTrue(paths[1].exists())
        self.assertFalse(paths[2].exists())
        self.assertEqual(len(self.store.entries()), before_notes)
        self.assertEqual(len(registry.sources()), 3)
        self.assertIn("1 file needs attention", review.feedback.get())
        self.assertIn("Synthetic locked PDF", review.details.get("1.0", "end"))

    def test_changed_batch_member_stops_before_any_confirmation_or_removal(self):
        review, _, _, paths = self.three_copies()
        self.choose(review, [0, 2])
        paths[2].write_bytes(paths[2].read_bytes() + b"new edit")
        with patch.object(self.app.service, "storage_action") as recycled:
            review.delete_pdf_button.invoke()
            self.wait(lambda: not review.busy)
        recycled.assert_not_called()
        self.assertIsNone(getattr(review, "confirmation", None))
        self.assertTrue(all(path.exists() for path in paths))
        self.assertIn("changed", review.feedback.get())

    def test_check_is_visible_in_both_lists_and_failure_restores_previous_selection(self):
        review, _, _, _ = self.three_copies()
        self.choose(review, [0, 2])
        self.show(review)
        children = review.tree.get_children()
        with patch("note_organizer.workflow_ui.background") as job:
            review.check()
        self.root.update()
        self.assertTrue(review.checking)
        for tree in (review.tree, review.local_copies):
            self.assertEqual(tree.status_message, "Checking library…")
            self.assertTrue(tree.status_label.winfo_ismapped())
            self.assertGreater(tree.status_label.winfo_height(), 20)
        self.assertEqual(review.tree.get_children(), children)
        self.assertTrue(review.link_button.instate(["disabled"]))
        self.assertTrue(review.delete_pdf_button.instate(["disabled"]))
        from tests.reader_app_regression import capture_test_window
        capture_test_window(review.window, Path(__file__).resolve().parents[1] / ".test-tmp/review-checking.png")
        job.call_args.args[3](OSError("Synthetic folder unavailable"))
        self.assertFalse(review.checking)
        self.assertIsNone(review.tree.status_message)
        self.assertEqual(set(review.local_copies.selection()), {"0", "2"})
        self.assertIn("unavailable", review.feedback.get())

    def test_map_is_visible_only_when_relevant_and_dialog_names_the_tablet_folder(self):
        review, _, _, _ = self.file_review()
        review.rows["folder"] = {"id": "folder", "kind": "folder_difference", "title": "Missing folder",
            "reason": "Choose its PC counterpart", "local_paths": [], "sources": [],
            "folder_ids": ["missing"], "actions": ["review_mapping"]}
        review.render()
        review.tree.selection_set("folder")
        review.selected()
        self.show(review)
        self.assertTrue(review.map_button.winfo_ismapped())
        self.assertFalse(review.map_button.instate(["disabled"]))
        self.assertFalse(review.send_button.winfo_ismapped())
        self.assertFalse(review.delete_pdf_button.winfo_ismapped())
        with patch("note_organizer.ui.filedialog.askdirectory", return_value="") as picker:
            review.map_button.invoke()
        self.assertIn("/Literature/Missing", picker.call_args.kwargs["title"])
        self.assertIs(picker.call_args.kwargs["parent"], review.window)
        from tests.reader_app_regression import capture_test_window
        capture_test_window(review.window, Path(__file__).resolve().parents[1] / ".test-tmp/review-mapping.png")
        review.tree.selection_set("copies")
        review.selected()
        self.root.update()
        self.assertFalse(review.map_button.winfo_ismapped())
        y_positions = {control.winfo_y() for control in review.review_actions.controls if control.winfo_ismapped()}
        self.assertEqual(len(y_positions), 1)

    def test_tablet_source_is_an_explicit_selectable_link_target(self):
        review, _, _, paths = self.file_review()
        review.rows["copies"]["sources"].append({"kind": "cloud", "cloud_id": "tablet-copy", "title": "Tablet paper", "digest": "hash"})
        review.selected()
        review.local_copies.selection_set(["0", "cloud:tablet-copy"])
        review.copy_selected()
        self.assertEqual(len(review.selected_sources()), 2)
        self.assertFalse(review.link_button.instate(["disabled"]))
        self.assertTrue(review.delete_pdf_button.instate(["disabled"]))
        self.assertEqual(review.selected_paths(), [str(paths[0])])

    def test_large_link_selection_uses_a_scrollable_confirmation_and_can_cancel(self):
        review, _, _, _ = self.file_review()
        review.rows["copies"]["sources"].extend(
            {"kind": "cloud", "cloud_id": f"tablet-{index}", "title": f"Tablet copy {index}", "digest": "hash"}
            for index in range(5))
        review.selected()
        review.local_copies.selection_set(review.local_copies.get_children())
        review.copy_selected()
        with patch.object(self.app.service, "paper_identity_action") as linked:
            review.link_button.invoke()
            self.assertIsNotNone(review.confirmation)
            self.assertIn("tablet-4", review.confirmation.details.text.get("1.0", "end"))
            review.confirmation.cancel_button.invoke()
        linked.assert_not_called()
        self.assertFalse(review.busy)


if __name__ == "__main__":
    unittest.main()
