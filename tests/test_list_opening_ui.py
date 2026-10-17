"""Library-to-Reader handoff and row-specific file activation."""
import gc
from pathlib import Path
import unittest
from unittest.mock import patch

import pymupdf

from note_organizer.storage import canonical, digest_file
from tests import test_ui_audit
from tests.ui_helpers import settle_library
from tests.test_preferences_ui import descendants
from note_organizer.widgets import DataTable


class ListOpeningUITests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    pump_until = test_ui_audit.UIAuditTests.pump_until

    def tearDown(self):
        test_ui_audit.UIAuditTests.tearDown(self)
        self.assertFalse(self.errors)
        # Reclaim completed Tk fixtures here, before a later worker allocation
        # triggers cyclic collection on a thread that cannot call Tcl.
        self.app = self.root = None
        gc.collect()

    def paper(self, name="Paper.pdf", notes=False, folder=None):
        folder = folder or self.pc
        folder.mkdir(exist_ok=True)
        project = self.store.add_project(folder)
        path = folder / name
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 80), "A paper to read")
            pdf.save(path)
        self.store.save_scan(project, path, digest_file(path), "sig", "settings", {"title": name},
                            [{"key": "note", "kind": "highlight", "page": 1, "rect": [50, 65, 150, 85], "quote": "A paper"}]
                            if notes else [])
        return project, self.store.document_at(project, path)["id"], path

    def refresh(self):
        self.app.refresh()
        settle_library(self.app, self.root)

    def select_paper(self, project, document):
        self.app.projects.selection_set(str(project))
        self.app.project_selected()
        self.app.papers.selection_set(document)
        self.app.paper_selected()

    def show(self, tab=None, window=None):
        native = getattr(self, "enable_pdf_reader", False)
        if native:
            from tests.reader_app_regression import require_private_desktop
            require_private_desktop()
        # WebView2 can stop painting a fully transparent ancestor on hosted
        # Windows. These real viewer tests already run on an isolated desktop.
        self.root.attributes("-alpha", 1 if native else 0)
        width = min(1250, self.root.winfo_screenwidth() - 32) if native else 1250
        height = min(820, self.root.winfo_screenheight() - 80) if native else 820
        self.root.geometry(f"{width}x{height}+0+0")
        self.app.tabs.select(tab or self.app.library_tab)
        self.root.deiconify()
        if window:
            window.attributes("-alpha", 0)
            window.deiconify()
        self.root.update()

    def activate(self, tree, row, keyboard=False):
        tree.see(row)
        tree.focus_force()
        self.root.update()
        if keyboard:
            tree.selection_set(row)
            tree.focus(row)
            tree.event_generate("<KeyPress-Return>")
        else:
            x, y, width, height = tree.bbox(row)
            self.click_time = getattr(self, "click_time", 1000) + 1000
            for index in range(2):
                tree.event_generate("<ButtonPress-1>", x=x+12, y=y+height//2, time=self.click_time+index*50)
                tree.event_generate("<ButtonRelease-1>", x=x+12, y=y+height//2, time=self.click_time+index*50+10)
        self.root.update()

    def test_library_handoff_loads_unannotated_pdf_despite_previous_reader_filters(self):
        project, document, path = self.paper()
        self.refresh()
        app = self.app
        app.search.set("a term this paper does not contain")
        app.label_filter.set("tag: Missing")
        app.note_type = "Typed notes"
        app.refresh_notes()
        self.pump_until(lambda: not app.reader_search_busy)
        self.select_paper(project, document)
        app.tabs.select(app.library_tab)
        app.view_notes()
        self.pump_until(lambda: not app.reader_search_busy)
        self.assertEqual(app.search.get(), "")
        self.assertEqual(app.label_filter.get(), "All papers")
        self.assertEqual(app.note_type, "All notes")
        self.assertEqual(app.tabs.select(), str(app.notes_tab))
        self.assertEqual(app.reader_views.select(), str(app.pdf_reader))
        self.assertEqual(app.reader_project_ids[app.reader_folder.current()-1], project)
        self.assertEqual(app.reader_paper_ids[app.reader_paper.current()-1], document)
        self.assertEqual(app.selected_entry()["document_id"], document)
        self.assertTrue(app.selected_entry()["pdf_document"])
        self.assertEqual(canonical(app.pdf_reader.entry["path"]), canonical(path))

    def test_library_double_click_and_enter_load_selected_paper_and_its_notes(self):
        project, first, path = self.paper("First.pdf", notes=True)
        _, second, other = self.paper("Second.pdf")
        self.refresh()
        self.select_paper(project, first)
        self.show()
        self.activate(self.app.papers, second)
        self.pump_until(lambda: not self.app.reader_search_busy)
        self.assertEqual(self.app.selected_entry()["document_id"], second)
        self.assertEqual(canonical(self.app.pdf_reader.entry["path"]), canonical(other))
        self.show()
        self.activate(self.app.papers, first, keyboard=True)
        self.pump_until(lambda: not self.app.reader_search_busy)
        self.assertEqual(self.app.selected_entry()["document_id"], first)
        self.assertTrue(self.app.selected_entry()["pdf_document"])
        self.assertEqual(len(self.app.entries), 2)
        self.assertEqual(canonical(self.app.pdf_reader.entry["path"]), canonical(path))
        generation = self.app.query_generation
        self.app.view_notes()
        self.pump_until(lambda: not self.app.reader_search_busy)
        self.assertGreater(self.app.query_generation, generation)
        self.assertIsNotNone(self.app.pdf_reader.entry)

    def test_library_labels_and_send_action_follow_current_paper(self):
        project, document, _ = self.paper()
        self.refresh()
        self.select_paper(project, document)
        menu = self.app.library_paper_actions.action_menu
        self.assertEqual(self.app.library_source_button.cget("text"), "Open externally")
        labels = [widget.cget("text") for widget in descendants(self.app.library_tab) if widget.winfo_class() == "TButton"]
        self.assertIn("View in Reader", labels)
        self.assertNotIn("Send selected PDF…", labels)
        self.assertEqual(menu.entrycget("Send selected PDF…", "state"), "normal")
        with patch.object(self.app, "send_pdf_path") as send:
            menu.invoke("Send selected PDF…")
        send.assert_called_once()
        self.app.papers.selection_remove(self.app.papers.selection())
        self.app.paper_selected()
        self.assertEqual(menu.entrycget("Send selected PDF…", "state"), "disabled")

    def test_watched_folder_activation_opens_only_clicked_row_and_ignores_headings(self):
        first, _, path = self.paper()
        second, _, other = self.paper(folder=self.folder / "Other")
        self.refresh()
        self.show()
        tree = self.app.projects
        with patch.object(self.app, "open_file_or_folder") as opened:
            self.activate(tree, str(second))
            self.assertEqual(canonical(opened.call_args.args[0]), canonical(other.parent))
            self.activate(tree, str(first), keyboard=True)
            self.assertEqual(canonical(opened.call_args.args[0]), canonical(path.parent))
            before = opened.call_count
            for index in range(2):
                tree.event_generate("<ButtonPress-1>", x=30, y=10, time=9000+index*50)
                tree.event_generate("<ButtonRelease-1>", x=30, y=10, time=9010+index*50)
            self.root.update()
            self.assertEqual(opened.call_count, before)
            for index in range(2):
                tree.event_generate("<ButtonPress-1>", x=30, y=tree.winfo_height()-8, time=11000+index*50)
                tree.event_generate("<ButtonRelease-1>", x=30, y=tree.winfo_height()-8, time=11010+index*50)
            tree.set_status("Loading folders…")
            self.activate(tree, str(first), keyboard=True)
            self.assertEqual(opened.call_count, before)
            tree.set_status()

    def test_review_copy_activation_handles_multiple_selection_folders_and_tablet_sources(self):
        from tests.test_library_review_updates import LibraryReviewUpdatesTests
        from tests.test_review_controls import ReviewControlTests
        # Use the same disposable duplicate fixtures as the review action tests.
        self.wait = ReviewControlTests.wait.__get__(self)
        self.review = ReviewControlTests.review.__get__(self)
        self.duplicate_papers = ReviewControlTests.duplicate_papers.__get__(self)
        from tests.test_library_review_files import LibraryReviewFileTests
        self.file_review = LibraryReviewFileTests.file_review.__get__(self)
        review, _, _, paths = LibraryReviewUpdatesTests.three_copies(self)
        review.rows["copies"]["local_paths"].append(str(self.pc))
        review.rows["copies"]["sources"].append({"kind": "cloud", "cloud_id": "remote", "digest": "hash"})
        review.selected()
        self.show(window=review.window)
        review.local_copies.selection_set(["0", "1", "2"])
        with patch.object(self.app, "open_file_or_folder") as opened:
            self.activate(review.local_copies, "1")
            opened.assert_called_once_with(str(paths[1]))
            self.activate(review.local_copies, "3", keyboard=True)
            self.assertEqual(opened.call_args.args, (str(self.pc),))
            before = opened.call_count
            self.activate(review.local_copies, "cloud:remote", keyboard=True)
            self.assertEqual(opened.call_count, before)
            self.assertIn("tablet source", review.feedback.get())

    def test_cloud_folder_and_pdf_rows_report_unavailable_local_content(self):
        self.show(self.app.remarkable_tab)
        with patch.object(self.app, "open_file_or_folder") as opened, patch("note_organizer.ui.messagebox.showinfo") as info:
            self.app.cloud_folders.set("missing", "local", "Needs mapping")
            self.activate(self.app.cloud_folders, "missing", keyboard=True)
            opened.assert_not_called()
            self.assertIn("/Literature/Missing", info.call_args.args[1])
            self.app.cloud_review.insert("", "end", iid="not-downloaded", values=("Remote paper", "/Literature", "Not downloaded"))
            self.activate(self.app.cloud_review, "not-downloaded", keyboard=True)
            self.assertIn("not been downloaded", info.call_args.args[1])

    def test_pdf_and_missing_file_opening_use_existing_external_routes(self):
        _, _, path = self.paper()
        with patch.object(self.app, "open_pdf") as pdf, patch.object(self.app, "open_path") as folder:
            self.app.open_file_or_folder(path)
            pdf.assert_called_once_with(path, source_only=True)
            self.app.open_file_or_folder(path.parent)
            folder.assert_called_once_with(path.parent)
        with patch("note_organizer.ui.messagebox.showerror") as error:
            self.app.open_file_or_folder(self.pc / "Missing.pdf")
        self.assertIn("Missing.pdf", error.call_args.args[1])

    def test_inbox_opens_the_file_and_keeps_identification_explicit(self):
        _, _, path = self.paper()
        inbox = self.app.inbox_view
        inbox.render([{"path": str(path), "name": path.name, "status": "ready", "signature": "sig"}])
        self.show(self.app.inbox_tab)
        with patch.object(self.app, "open_file_or_folder") as opened, patch.object(self.app.inbox, "prepare") as identify:
            self.activate(inbox.tree, str(path))
        opened.assert_called_once_with(str(path))
        identify.assert_not_called()

    def test_supplement_candidates_and_attachments_open_their_exact_file_or_link(self):
        from note_organizer.research_ui import SupplementsWindow
        _, document, path = self.paper()
        with patch("note_organizer.research_ui.background"):
            dialog = SupplementsWindow(self.app, document, path)
        dialog.tree.set_status()
        dialog.local_links = [{"label": "Local PDF", "source": "Library", "path": str(path)}]
        dialog.web_links = [{"label": "Publisher file", "source": "Publisher", "url": "https://example.org/si.pdf"}]
        dialog.show_links()
        dialog.attached.set_status()
        dialog.saved = [{"path": str(path)}]
        self.app.update_rows(dialog.attached, [("0", (str(path),))])
        self.show(window=dialog.window)
        with patch.object(self.app, "open_file_or_folder") as opened, patch("note_organizer.research_ui.webbrowser.open") as browser:
            self.activate(dialog.tree, "0", keyboard=True)
            opened.assert_called_once_with(str(path))
            self.activate(dialog.attached, "0")
            self.assertEqual(opened.call_count, 2)
            self.activate(dialog.tree, "1", keyboard=True)
            browser.assert_called_once_with("https://example.org/si.pdf")

    def test_extra_pdf_review_opens_copy_only_when_idle(self):
        from note_organizer.storage_ui import LegacyCleanupDialog
        _, _, path = self.paper()
        with patch("note_organizer.storage_ui.background"):
            dialog = LegacyCleanupDialog(self.app)
        dialog.loaded([{"name": "Reading copy", "path": str(path), "status": "blocked", "reasons": ["Keep this copy"]}])
        self.show(window=dialog.window)
        with patch.object(self.app, "open_file_or_folder") as opened:
            self.activate(dialog.tree, "0", keyboard=True)
            opened.assert_called_once_with(str(path))
            dialog.busy = "removing"
            self.activate(dialog.tree, "0", keyboard=True)
            self.assertEqual(opened.call_count, 1)
        dialog.busy = ""

    def test_transfers_open_local_files_but_grouped_recovery_reveals_locations(self):
        _, _, path = self.paper()
        self.store.set_preference("remarkable_outbox", [{"id": "transfer", "path": str(path), "state": "waiting"}])
        self.refresh()
        window = self.app.transfers()
        table = next(widget for widget in descendants(window) if isinstance(widget, DataTable))
        self.show(window=window)
        with patch.object(self.app, "open_file_or_folder") as opened:
            self.activate(table, "transfer", keyboard=True)
            opened.assert_called_once_with(str(path))
        window.destroy()
        with patch("note_organizer.ui.background") as background:
            recovery = self.app.filing_recovery()
        background.call_args.args[2]([{"job_id": "retained", "source": str(path), "path": str(path.with_name("Retained.pdf")), "error": "Inspect both copies"}])
        table = next(widget for widget in descendants(recovery) if isinstance(widget, DataTable))
        self.show(window=recovery)
        with patch.object(self.app, "open_file_or_folder") as opened:
            self.activate(table, "retained", keyboard=True)
            opened.assert_not_called()
        self.assertEqual(table.selection(), ("retained",))


class NativeLibraryHandoffTests(unittest.TestCase):
    enable_pdf_reader = True
    setUp = test_ui_audit.UIAuditTests.setUp
    pump_until = test_ui_audit.UIAuditTests.pump_until
    paper = ListOpeningUITests.paper
    refresh = ListOpeningUITests.refresh
    select_paper = ListOpeningUITests.select_paper
    show = ListOpeningUITests.show
    activate = ListOpeningUITests.activate

    def tearDown(self):
        self.app.pdf_reader.close()
        self.app.pdf_reader.wait_closed()
        self.app.context_executor.shutdown(wait=True, cancel_futures=True)
        test_ui_audit.UIAuditTests.tearDown(self)
        self.assertFalse(self.errors)

    def test_double_click_loads_real_embedded_pdf_without_reselecting_dropdowns(self):
        project, document, path = self.paper(notes=True)
        self.refresh()
        self.select_paper(project, document)
        self.show()
        self.activate(self.app.papers, document)
        self.pump_until(lambda: self.app.pdf_reader.loaded and not self.app.reader_search_busy, timeout=30)
        self.assertEqual(canonical(self.app.pdf_reader.entry["path"]), canonical(path))
        self.assertEqual(self.app.selected_entry()["document_id"], document)
        self.assertEqual(len(self.app.entries), 2)


if __name__ == "__main__":
    unittest.main()
