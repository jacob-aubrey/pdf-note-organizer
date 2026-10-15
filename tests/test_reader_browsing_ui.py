"""Reader browsing, paper identity and sorting using disposable real PDFs."""
from concurrent.futures import Future
from pathlib import Path
from tkinter import ttk
import unittest
from unittest.mock import patch

import fitz

from note_organizer.storage import digest_file
from note_organizer.reader_results import paper_labels
from note_organizer.research_tools import save_labels
from tests import test_review_controls
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


class ReaderBrowsingUITests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait

    def papers(self):
        """Titles deliberately sort opposite filenames; notes arrive out of page order."""
        project = self.store.add_project(self.pc)
        self.sources = {}
        for filename, title, matching_pages, note_pages in (
                ("zeta.pdf", "Alpha study", (1, 2, 10), (10, 2)),
                ("alpha.pdf", "Zulu study", (1, 3), (3, 1))):
            path = self.pc / filename
            with fitz.open() as document:
                for page_number in range(1, max(matching_pages) + 1):
                    text = (f"iodine experiment {title} page {page_number}; Cited author, Different cited paper"
                            if page_number in matching_pages else f"Control page {page_number}")
                    document.new_page().insert_text((50, 75), text)
                document.save(path)
            self.store.save_scan(project, path, digest_file(path), "sig", "settings",
                                 {"title": title, "pages": max(matching_pages)}, [
                {"key": f"note-{page}", "kind": "text", "page": page,
                 "rect": [1, 2, 3, 4], "comment": f"iodine note {title} page {page}"}
                for page in note_pages])
            self.sources[title] = path
        self.app.refresh()
        settle_library(self.app, self.root)
        self.wait(lambda: len(self.app.entries) == 4 and len(self.app.notes.get_children()) == 4)

    def displayed(self):
        return [self.app.entries[int(row)] for row in self.app.notes.get_children()]

    def order(self):
        return [(entry["metadata"]["title"], "PDF" if entry["kind"] == "pdf" else "Note", entry["page"])
                for entry in self.displayed()]

    def query_all(self):
        self.app.search_scope.set("All")
        self.app.search.set("iodine")
        self.wait(lambda: len(self.app.entries) == 9 and len(self.app.notes.get_children()) == 9)

    def test_scope_is_visible_next_to_search_and_options_do_not_duplicate_it(self):
        app = self.app
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        app.tabs.select(app.notes_tab)
        self.root.geometry("940x700+0+0")
        self.root.update()
        self.assertEqual(tuple(app.search_scope_control.cget("values")), ("Notes", "PDFs", "All"))
        self.assertTrue(app.search_scope_control.instate(["readonly"]))
        self.assertLess(app.search_label.winfo_rootx(), app.search_scope_control.winfo_rootx())
        self.assertLess(app.search_scope_control.winfo_rootx(), app.search_entry.winfo_rootx())
        self.assertTrue(app.search_options_button.cget("text").startswith("Search filters"))
        app.search_scope.set("PDFs")
        app.search_options()
        scopes = [widget for widget in descendants(self.root) if isinstance(widget, ttk.Radiobutton)
                  and widget.cget("text") in {"All", "PDFs", "Notes"}]
        self.assertEqual(scopes, [])
        cancel = next(widget for widget in descendants(self.root)
                      if isinstance(widget, ttk.Button) and widget.cget("text") == "Cancel")
        cancel.invoke()
        self.assertEqual(app.search_scope.get(), "PDFs")

    def test_empty_scope_browses_documents_and_selects_reader_without_indexing_or_raster_preview(self):
        self.papers()
        app = self.app
        with patch.object(app.pdf_worker, "text_pages") as indexed, \
                patch.object(app.pdf_worker, "text_pages_cancellable") as cancellable_indexed, \
                patch.object(app.pdf_worker, "search_page") as rendered, \
                patch.object(app.context_executor, "submit") as context:
            app.search_scope.set("PDFs")
            self.wait(lambda: len(app.entries) == 2 and len(app.notes.get_children()) == 2)
            self.assertTrue(all(entry["kind"] == "pdf" and entry.get("pdf_document") for entry in app.entries))
            self.assertEqual({Path(entry["path"]) for entry in app.entries}, set(self.sources.values()))
            for row in app.notes.get_children():
                app.notes.selection_set(row)
                app.preview()
                self.assertIn(Path(app.selected_entry()["path"]).name, app.preview_text.get("1.0", "end"))
                self.assertIsNone(app.image)
                self.assertEqual(app.pdf_reader.entry["path"], app.selected_entry()["path"])
                self.assertEqual(app.pdf_reader.entry["page"], 1)
                self.assertFalse(app.source_button.instate(["disabled"]))
                with patch.object(app, "open_pdf") as opened:
                    app.open_source()
                opened.assert_called_once_with(app.selected_entry()["path"], 1, source_only=True)
            app.search_scope.set("All")
            self.wait(lambda: len(app.entries) == 6 and len(app.notes.get_children()) == 6)
            self.assertEqual(sum(bool(entry.get("pdf_document")) for entry in app.entries), 2)
            self.assertEqual(sum(entry["kind"] == "text" for entry in app.entries), 4)
            indexed.assert_not_called()
            cancellable_indexed.assert_not_called()
            rendered.assert_not_called()
            context.assert_not_called()
        app.search_scope.set("Notes")
        self.wait(lambda: len(app.entries) == 4 and len(app.notes.get_children()) == 4)
        self.assertTrue(all(entry["kind"] == "text" for entry in app.entries))

    def test_query_replaces_documents_with_page_matches_and_clearing_restores_browsing(self):
        self.papers()
        app = self.app
        app.search_scope.set("PDFs")
        self.wait(lambda: len(app.entries) == 2)
        app.search.set("iodine")
        self.wait(lambda: len(app.entries) == 5 and len(app.notes.get_children()) == 5)
        self.assertTrue(all(entry["kind"] == "pdf" and not entry.get("pdf_document") for entry in app.entries))
        self.assertEqual(self.order(), [("Alpha study", "PDF", 1), ("Alpha study", "PDF", 2),
                                       ("Alpha study", "PDF", 10), ("Zulu study", "PDF", 1),
                                       ("Zulu study", "PDF", 3)])
        app.search.set("")
        self.wait(lambda: len(app.entries) == 2 and len(app.notes.get_children()) == 2)
        self.assertTrue(all(entry.get("pdf_document") for entry in app.entries))

    def test_paper_grouping_numeric_pages_and_type_toggle_keep_selected_source(self):
        self.papers()
        self.query_all()
        app = self.app
        paper_order = [("Alpha study", "Note", 2), ("Alpha study", "Note", 10),
                       ("Alpha study", "PDF", 1), ("Alpha study", "PDF", 2), ("Alpha study", "PDF", 10),
                       ("Zulu study", "Note", 1), ("Zulu study", "Note", 3),
                       ("Zulu study", "PDF", 1), ("Zulu study", "PDF", 3)]
        self.assertEqual(self.order(), paper_order)
        self.assertIn("paper", app.notes.cget("columns"))
        for row in app.notes.get_children():
            self.assertIn(app.entries[int(row)]["metadata"]["title"], app.notes.set(row, "paper"))
        selected_row = app.notes.get_children()[4]
        app.notes.selection_set(selected_row)
        selected = (app.selected_entry()["document_id"], app.selected_entry()["key"])
        self.root.tk.call(app.notes.heading("kind", "command"))
        self.assertEqual(self.order(), [entry for entry in paper_order if entry[1] == "Note"] +
                                      [entry for entry in paper_order if entry[1] == "PDF"])
        self.assertEqual((app.selected_entry()["document_id"], app.selected_entry()["key"]), selected)
        self.root.tk.call(app.notes.heading("kind", "command"))
        self.assertEqual(self.order(), [entry for entry in paper_order if entry[1] == "PDF"] +
                                      [entry for entry in paper_order if entry[1] == "Note"])
        self.root.tk.call(app.notes.heading("paper", "command"))
        self.assertEqual(self.order(), paper_order)
        self.assertEqual(app.notes.selection(), (selected_row,))

    def test_result_tooltip_identifies_actual_source_before_cited_excerpt(self):
        self.papers()
        self.query_all()
        app = self.app
        row = next(row for row in app.notes.get_children() if app.entries[int(row)]["kind"] == "pdf")
        entry = app.entries[int(row)]
        for column in app.notes.cget("columns"):
            with self.subTest(column=column):
                tooltip = app.notes.tooltip.value(row, column)
                self.assertTrue(tooltip.startswith(entry["metadata"]["title"]))
                self.assertIn(Path(entry["path"]).name, tooltip)
                self.assertIn(f"PDF page {entry['page']}", tooltip)
                self.assertLess(tooltip.index(Path(entry["path"]).name), tooltip.index(entry["quote"]))
                self.assertLess(tooltip.index(f"PDF page {entry['page']}"), tooltip.index(entry["quote"]))

    def test_scope_change_applies_existing_query_and_keeps_rows_until_replacement_ready(self):
        self.papers()
        app = self.app
        app.search.set("iodine")
        self.wait(lambda: app.note_count.get() == "4 notes" and app.search_after is None)
        previous_rows = app.notes.get_children()
        previous_values = [app.notes.item(row, "values") for row in previous_rows]
        app.notes.selection_set(previous_rows[-1])
        pending = Future()
        with patch.object(app.query_executor, "submit", return_value=pending) as submitted:
            app.search_scope.set("PDFs")
            submitted.assert_called_once()
            self.assertEqual(submitted.call_args.args[3], "PDFs")
            self.assertEqual(submitted.call_args.kwargs["query"], "iodine")
            self.assertEqual(app.notes.get_children(), previous_rows)
            self.assertEqual([app.notes.item(row, "values") for row in previous_rows], previous_values)
            self.assertEqual(app.notes.selection(), (previous_rows[-1],))
            pending.set_result([])
            self.wait(lambda: not app.entries and not app.notes.get_children())

    def test_document_opens_its_selected_source_without_combining_other_versions(self):
        self.papers()
        app = self.app
        app.tabs.select(app.notes_tab)
        app.search_scope.set("PDFs")
        self.wait(lambda: len(app.entries) == 2)
        entry = app.selected_entry()
        with patch.object(app, "materialize_pdf", side_effect=AssertionError("Must open the selected source")), \
                patch.object(app, "launch_pdf") as launched:
            app.open_entry_pdf(entry)
            self.wait(lambda: launched.called)
        launched.assert_called_once_with(Path(entry["path"]), 1, "notes")

    def test_browsed_citation_export_respects_collection_filter(self):
        self.papers()
        app = self.app
        app.tabs.select(app.notes_tab)
        chosen = next(entry["document_id"] for entry in app.entries if entry["metadata"]["title"] == "Alpha study")
        save_labels(self.store, chosen, {"tag": "Chosen"})
        app.label_filter.set("tag: Chosen")
        app.search_scope.set("PDFs")
        self.wait(lambda: len(app.entries) == 1 and app.entries[0].get("pdf_document"))
        target = str(self.folder / "selected.ris")
        with patch("note_organizer.ui.filedialog.asksaveasfilename", return_value=target), \
                patch("note_organizer.ui.export_citations", return_value=1) as exported:
            app.export_citation_selection()
            self.wait(lambda: exported.called)
        exported.assert_called_once_with(self.store, [chosen], target)


class ReaderIdentityTests(unittest.TestCase):
    def test_same_title_and_filename_in_different_folders_have_distinct_labels(self):
        entries = [{"path": str(Path(folder) / "paper.pdf"), "metadata": {"title": "Same title"}}
                   for folder in ("Folder A", "Folder B")]
        labels = list(paper_labels(entries).values())
        self.assertEqual(len(set(labels)), 2)
        self.assertIn("Folder A", labels[0])
        self.assertIn("Folder B", labels[1])


if __name__ == "__main__":
    unittest.main()
