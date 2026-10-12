"""Review controls use disposable files, libraries and hidden Tk windows."""
from concurrent.futures import Future
from pathlib import Path
import time
from tkinter import ttk
import unittest
from unittest.mock import patch

import fitz

from note_organizer.extraction import extract, scan_fingerprint
from note_organizer.paper_registry import Registry
from note_organizer.storage import DEFAULT_SETTINGS, canonical, digest_file
from note_organizer.view_state import read_view
from tests import test_ui_audit
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class ReviewControlTests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp

    def tearDown(self):
        self.app.preview_cancel.set()
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        test_ui_audit.UIAuditTests.tearDown(self)

    def wait(self, predicate, timeout=6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            self.app.poll()
            if predicate():
                self.assertFalse(self.errors)
                return
            time.sleep(.005)
        self.fail("Review action did not settle")

    def review(self):
        review = self.app.review_library()
        review.window.attributes("-alpha", 0)
        review.window.withdraw()
        self.wait(lambda: hasattr(review, "undo_operation"))
        return review

    def rows(self):
        return {
            "z": {"id": "z", "kind": "local_duplicate", "title": "Zulu paper", "reason": "Z explanation " * 40,
                  "local_paths": [str(self.pc / "location-needle.pdf")], "sources": [{"path": "first", "digest": "one"}], "actions": []},
            "a": {"id": "a", "kind": "local_duplicate", "title": "alpha paper", "reason": "A explanation",
                  "local_paths": [], "sources": [], "actions": []},
            "linked": {"id": "linked", "kind": "paper_match", "title": "Beta linked", "reason": "Confirmed",
                       "confidence": "confirmed_link", "local_paths": [], "sources": [], "actions": []},
            "kept": {"id": "kept", "kind": "local_not_compared", "title": "Gamma separate", "reason": "Keep this copy",
                     "local_paths": [], "sources": [], "actions": []},
        }

    def populated_review(self):
        review = self.review()
        review.rows = self.rows()
        review.choices[review.choice_key(review.rows["kept"])] = True
        review.render()
        return review

    def test_saved_recovery_copies_remain_visible_after_restart(self):
        previous = self.pc / "paper.pdf.old.preserved"
        previous.write_bytes(b"previous complete paper")
        self.store.save_remarkable_item("recovery", {"recovery_paths": [str(previous)], "state": "synced"})
        self.app.view = read_view(self.store.path)
        self.app.render_view()
        self.assertIn("1 previous PDF copy retained for recovery", self.app.local_sync_summary.get())
        self.assertEqual(self.app.details_button.winfo_manager(), "pack")
        self.assertEqual(self.app.details_button.cget("text"), "View sync details")
        self.app.show_sync_details()
        self.assertIn(str(previous), self.app.activity.get("1.0", "end"))
        self.assertEqual(self.app.activity_toggle.cget("text"), "Hide sync details")
        self.app.toggle_activity()
        self.assertEqual(self.app.activity_toggle.cget("text"), "Show sync details")
        self.app.show_sync_details()
        self.assertEqual(self.app.activity.get("1.0", "end").count(str(previous)), 1)

    def test_sorting_filters_selection_and_counts(self):
        review = self.populated_review()
        self.assertEqual(set(review.tree.get_children()), {"a", "z"})
        review.tree.selection_set("z")
        self.root.tk.call(review.tree.heading("name", "command"))
        self.assertEqual(review.tree.get_children(), ("a", "z"))
        self.assertEqual(review.tree.selection(), ("z",))
        self.assertIn("▲", review.tree.heading("name", "text"))
        self.root.tk.call(review.tree.heading("name", "command"))
        self.assertEqual(review.tree.get_children(), ("z", "a"))
        self.assertIn("▼", review.tree.heading("name", "text"))
        self.assertIn("2 shown · 2 need review · 1 already linked · 1 kept separate", review.feedback.get())
        review.review_state.set("All findings")
        self.assertEqual(len(review.tree.get_children()), 4)
        review.finding_type.set("Local duplicate")
        self.assertEqual(set(review.tree.get_children()), {"a", "z"})
        review.search.set("LOCATION-NEEDLE")
        self.assertEqual(review.tree.get_children(), ("z",))
        self.assertIn("1 shown · 2 need review", review.feedback.get())
        review.search.set("")
        review.finding_type.set("All types")
        review.review_state.set("Already linked")
        self.assertEqual(review.tree.get_children(), ("linked",))

    def test_widened_review_cell_contains_full_explanation_and_controls_fit(self):
        review = self.populated_review()
        explanation = review.rows["z"]["reason"]
        review.tree.column("reason", width=1800)
        self.assertEqual(review.tree.set("z", "reason"), explanation)
        review.tree.selection_set("z")
        review.selected()
        self.assertIn(explanation, review.details.get("1.0", "end"))
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        review.window.geometry("1000x700")
        review.window.deiconify()
        self.root.update()
        self.assertGreater(review.tree.winfo_height(), 60)
        for button in (review.check_button, review.link_button, review.keep_button, review.again_button, review.undo_button):
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                 review.window.winfo_rooty() + review.window.winfo_height() + 2)
        review.window.withdraw()
        self.root.withdraw()

    def test_double_click_separator_fits_full_cell_and_keeps_other_columns_responsive(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("1100x700+0+0")
        self.app.tabs.select(self.app.remarkable_tab)
        self.root.deiconify()
        tree = self.app.cloud_review
        title = "Complete scientific paper title " * 20
        self.app.update_rows(tree, [("fit", (title, "Cloud location", "Needs review"))])
        tree.column("name", width=110, minwidth=90, stretch=False)
        self.root.update()
        x = next(x for x in range(tree.winfo_width())
                 if tree.identify_region(x, 10) == "separator" and tree.identify_column(x) == "#1")
        for _ in range(2):
            tree.event_generate("<ButtonPress-1>", x=x, y=10)
            tree.event_generate("<ButtonRelease-1>", x=x, y=10)
        self.root.update()
        self.assertFalse(self.errors)
        self.assertGreater(tree.column("name", "width"), 1000)
        self.assertEqual(tree.set("fit", "name"), title)
        self.assertEqual(tree.user_columns, {"name"})
        self.assertTrue(tree.column("reason", "stretch"))
        self.root.withdraw()

    def test_older_scan_completion_cannot_replace_newer_findings_or_status(self):
        review = self.review()
        pending = []
        def defer(app, function, success, error=None):
            pending.append((success, error))
        with patch("note_organizer.workflow_ui.background", side_effect=defer):
            review.check()
            review.check()
        latest = {**self.rows()["a"], "id": "new", "title": "New finding"}
        earlier = {**self.rows()["a"], "id": "old", "title": "Old finding"}
        pending[1][0]([latest])
        status = review.feedback.get()
        pending[0][0]([earlier])
        pending[0][1](RuntimeError("Obsolete scan failure"))
        self.assertEqual(review.tree.get_children(), ("new",))
        self.assertEqual(review.feedback.get(), status)
        self.assertFalse(review.check_button.instate(["disabled"]))

    def test_keep_separate_persists_across_dialogs_and_review_again_clears_it(self):
        review = self.review()
        review.rows = {"a": self.rows()["a"]}
        review.render()
        review.tree.selection_set("a")
        review.selected()
        self.assertFalse(review.keep_button.instate(["disabled"]))
        review.keep_button.invoke()
        self.wait(lambda: not review.busy)
        key = review.choice_key(review.rows["a"])
        self.assertTrue(self.store.preference("reconciliation_choices")[key])
        self.assertFalse(review.tree.get_children())
        review.close()
        reopened = self.review()
        reopened.rows = {"a": self.rows()["a"]}
        reopened.review_state.set("Kept separate")
        self.assertEqual(reopened.tree.get_children(), ("a",))
        reopened.tree.selection_set("a")
        reopened.selected()
        self.assertFalse(reopened.again_button.instate(["disabled"]))
        reopened.again_button.invoke()
        self.wait(lambda: not reopened.busy)
        self.assertNotIn(key, self.store.preference("reconciliation_choices"))
        reopened.review_state.set("Needs review")
        self.assertEqual(reopened.tree.get_children(), ("a",))

    def duplicate_papers(self):
        first, second = self.pc / "first.pdf", self.pc / "second.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.add_text_annot((50, 100), "Preserve this annotation")
            document.save(first)
        second.write_bytes(first.read_bytes())
        project = self.store.add_project(self.pc)
        registry = Registry(self.store)
        sources = []
        for path in (first, second):
            digest, signature, metadata, notes = extract(path, DEFAULT_SETTINGS)
            self.store.save_scan(project, path, digest, signature, scan_fingerprint(DEFAULT_SETTINGS), metadata, notes)
            sources.append(registry.register_local(path))
        return registry, sources, [first, second]

    def test_link_rescans_into_already_linked_and_undo_restores_sources(self):
        registry, sources, paths = self.duplicate_papers()
        before = {source["id"]: source["paper_id"] for source in sources}
        digests = [digest_file(path) for path in paths]
        review = self.review()
        review.check()
        self.wait(lambda: review.rows and not review.check_button.instate(["disabled"]))
        row = next(row for row in review.rows.values() if row["kind"] == "local_duplicate")
        review.tree.selection_set(row["id"])
        review.selected()
        with patch("note_organizer.workflow_ui.messagebox.askokcancel", return_value=True):
            review.link_button.invoke()
            self.wait(lambda: getattr(review, "undo_operation", None) is not None
                      and any(review.state(row) == "Already linked" for row in review.rows.values()))
        self.assertEqual(len({source["paper_id"] for source in registry.sources()}), 1)
        self.assertFalse(review.undo_button.instate(["disabled"]))
        review.review_state.set("Already linked")
        self.assertTrue(review.tree.get_children())
        with patch("note_organizer.workflow_ui.messagebox.askokcancel", return_value=True):
            review.undo_button.invoke()
            self.wait(lambda: review.undo_operation is None and not review.check_button.instate(["disabled"]))
        self.assertEqual({source["id"]: source["paper_id"] for source in registry.sources()}, before)
        self.assertIsNone(registry.latest_link_operation())
        self.assertTrue(review.undo_button.instate(["disabled"]))
        self.assertEqual([digest_file(path) for path in paths], digests)
        self.assertTrue(any(row[0] == "export_pending" for row in list(self.app.service.commands.queue)))

    def test_open_folder_buttons_follow_selected_root_and_disable_without_one(self):
        first = self.store.add_project(self.pc)
        other = self.folder / "Other"
        other.mkdir()
        second = self.store.add_project(other)
        unavailable = self.folder / "Unavailable"
        unavailable.mkdir()
        missing = self.store.add_project(unavailable)
        unavailable.rmdir()
        self.app.refresh()
        settle_library(self.app, self.root)
        for project, expected in ((first, self.pc), (second, other)):
            self.app.projects.selection_set(str(project))
            self.app.project_selected()
            with patch.object(self.app, "open_path") as opened:
                self.app.library_folder_button.invoke()
                self.app.notes_folder_button.invoke()
            self.assertEqual([canonical(call.args[0]) for call in opened.call_args_list],
                             [canonical(expected), canonical(expected)])
        self.app.reader_folder.current(0)
        self.app.reader_folder_selected()
        self.assertTrue(self.app.notes_folder_button.instate(["disabled"]))
        with patch.object(self.app, "open_path") as opened:
            self.app.notes_folder_button.invoke()
        opened.assert_not_called()
        self.app.projects.selection_set(str(missing))
        self.app.project_selected()
        self.assertTrue(self.app.library_folder_button.instate(["disabled"]))
        self.assertTrue(self.app.notes_folder_button.instate(["disabled"]))

    def test_old_async_library_snapshot_cannot_replace_new_inbox_configuration(self):
        self.app.inbox.initialize()
        old = read_view(self.store.path)
        self.app.inbox.save_config({"naming_mode": "Basic", "online_metadata_lookup_enabled": False})
        future = Future()
        future.set_result(old)
        self.app.finish_view(future)
        self.assertEqual(self.app.inbox.config()["naming_mode"], "Basic")
        self.assertFalse(self.app.inbox.config()["online_metadata_lookup_enabled"])
        self.assertEqual(self.store.preference("inbox")["naming_mode"], "Basic")

    def test_filing_recovery_remains_available_without_modifying_retained_copies(self):
        self.app.inbox.initialize()
        source = self.folder / "Incoming" / "download.pdf"
        source.parent.mkdir()
        source.write_bytes(b"changed download")
        target = self.pc / "retained.pdf"
        target.write_bytes(b"original retained copy")
        with self.store.connect() as database:
            database.execute("""INSERT INTO inbox_jobs(id,source,path,signature,digest,details,state,created_at,error)
                VALUES(?,?,?,?,?,?,?,?,?)""", ("recovery", canonical(source), canonical(target), "signature", "digest", "{}",
                                             "error", "2026-10-08", "Original changed; inspect both copies."))
        before = (source.read_bytes(), target.read_bytes())
        for _ in range(2):
            window = self.app.filing_recovery()
            window.attributes("-alpha", 0)
            window.withdraw()
            tree = next(widget for widget in descendants(window) if isinstance(widget, ttk.Treeview))
            self.wait(lambda: tree.exists("recovery"))
            tree.selection_set("recovery")
            tree.event_generate("<<TreeviewSelect>>")
            self.root.update()
            buttons = {widget.cget("text"): widget for widget in descendants(window) if isinstance(widget, ttk.Button)}
            with patch.object(self.app, "open_path") as opened:
                buttons["Open inbox"].invoke()
                buttons["Open containing folder"].invoke()
            self.assertEqual([canonical(call.args[0]) for call in opened.call_args_list],
                             [canonical(source.parent), canonical(target.parent)])
            self.assertEqual((source.read_bytes(), target.read_bytes()), before)
            self.assertEqual(self.app.inbox.list_recovery_errors()[0]["job_id"], "recovery")
            buttons["Close"].invoke()


if __name__ == "__main__":
    unittest.main()
