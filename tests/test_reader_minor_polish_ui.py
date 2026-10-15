"""Minor reader controls and every PDF occurrence using disposable local data."""
from tkinter import font, ttk
import unittest
from unittest.mock import patch

import fitz

from note_organizer.research_tools import save_labels
from note_organizer.storage import digest_file
from tests import test_review_controls
from tests.ui_helpers import settle_library


class ReaderMinorPolishUITests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait

    def show(self, width=940):
        self.root.attributes("-alpha", 0)
        self.root.geometry(f"{width}x760+0+0")
        self.app.tabs.select(self.app.notes_tab)
        self.root.deiconify()
        self.root.update()

    def paper(self):
        project = self.store.add_project(self.pc)
        path = self.pc / "occurrences.pdf"
        with fitz.open() as document:
            page = document.new_page(width=612, height=1200)
            for index in range(5):
                text = f"Tantalum occurrence {index + 1}. " + "Ordinary context words. " * 20
                remaining = page.insert_textbox(fitz.Rect(45, 40 + index * 220, 565, 245 + index * 220),
                                                text, fontsize=10)
                self.assertGreaterEqual(remaining, 0)
            document.save(path)
        self.store.save_scan(project, path, digest_file(path), "sig", "settings", {"title": "Five occurrences"}, [
            {"key": "highlight", "kind": "highlight", "page": 1, "rect": [45, 40, 200, 60],
             "quote": "Tantalum highlighted note"},
            {"key": "typed", "kind": "text", "page": 1, "rect": [45, 70, 200, 90],
             "comment": "Typed observation"}])
        document_id = self.store.documents()[0]["id"]
        save_labels(self.store, document_id, {"tag": "Chosen"})
        self.app.refresh()
        settle_library(self.app, self.root)
        self.wait(lambda: len(self.app.entries) == 2)
        return document_id

    def test_folder_paper_and_collection_are_equal_width_on_one_row(self):
        app = self.app
        for width in (940, 1250):
            with self.subTest(width=width):
                self.show(width)
                choices = (app.reader_folder, app.reader_paper, app.label_picker)
                self.assertEqual({choice.grid_info()["row"] for choice in choices}, {0})
                self.assertEqual(len({choice.winfo_rooty() for choice in choices}), 1)
                self.assertLessEqual(max(choice.winfo_width() for choice in choices) -
                                     min(choice.winfo_width() for choice in choices), 1)
                labels = [widget for widget in app.reader_folder.master.winfo_children()
                          if isinstance(widget, ttk.Label)]
                self.assertEqual([label.cget("text") for label in labels], ["Folder", "Paper", "Collection or tag"])
                self.assertEqual({widget.grid_info()["row"] for widget in labels}, {0})
                self.assertLess(app.reader_folder.winfo_rootx(), app.reader_paper.winfo_rootx())
                self.assertLess(app.reader_paper.winfo_rootx(), app.label_picker.winfo_rootx())
                self.assertGreater(app.search_entry.winfo_width(), 50)

    def test_page_heading_reserves_both_sort_arrows_at_display_scales(self):
        original = self.root.tk.call("tk", "scaling")
        try:
            for scale in (1, 1.5):
                with self.subTest(scale=scale):
                    self.root.tk.call("tk", "scaling", (96 / 72) * scale)
                    # Column sizing is computed when a table is built, as at
                    # application startup on a monitor with this display scale.
                    frame = ttk.Frame(self.root)
                    tree = self.app.tree(frame, [("page", "Page", 55), ("text", "Match", 210)])
                    face = self.app.style.lookup("Treeview.Heading", "font")
                    measure = font.Font(root=tree, font=face).measure
                    required = max(measure("Page ▲"), measure("Page ▼")) + 28
                    self.assertGreaterEqual(tree.column("page", "width"), required)
                    self.assertGreaterEqual(tree.column("page", "minwidth"), required)
                    frame.destroy()
        finally:
            self.root.tk.call("tk", "scaling", original)

    def test_clear_and_escape_keep_scope_filters_and_keyboard_focus(self):
        self.paper()
        self.show()
        app = self.app
        app.search_scope.set("All")
        app.label_filter.set("tag: Chosen")
        app.search_fields = ["quote"]
        app.search_mode = "Exact phrase"
        app.note_type = "Highlights and markup"
        app.update_search_options_summary()
        expected = (app.search_scope.get(), app.label_filter.get(), list(app.search_fields),
                    app.search_mode, app.note_type, app.reader_folder.get(), app.reader_paper.get())
        for escape in (False, True):
            with self.subTest(escape=escape):
                app.search.set("no matching phrase")
                self.wait(lambda: not app.entries and app.search_after is None)
                self.assertFalse(app.clear_search_button.instate(["disabled"]))
                app.search_entry.focus_force()
                self.root.update()
                if escape:
                    app.search_entry.event_generate("<Escape>")
                else:
                    app.clear_search_button.invoke()
                self.wait(lambda: app.search.get() == "" and len(app.entries) == 2)
                actual = (app.search_scope.get(), app.label_filter.get(), list(app.search_fields),
                          app.search_mode, app.note_type, app.reader_folder.get(), app.reader_paper.get())
                self.assertEqual(actual, expected)
                self.assertEqual(self.root.focus_get(), app.search_entry)
                self.assertTrue(app.clear_search_button.instate(["disabled"]))

    def test_search_filters_name_and_icon_survive_active_options(self):
        app = self.app
        self.assertEqual(app.search_options_button.cget("text"), "Search filters…")
        self.assertEqual(app.search_options_button.icon_name, "list-filter")
        app.search_mode = "Exact phrase"
        app.update_search_options_summary()
        self.assertEqual(app.search_options_button.cget("text"), "Search filters… •")
        self.assertEqual(app.search_options_button.icon_name, "list-filter")
        app.search_options()
        windows = [widget for widget in self.root.winfo_children() if widget.winfo_toplevel() == widget and widget != self.root]
        dialog = next(window for window in windows if window.title() == "Search filters")
        dialog.destroy()

    def test_every_pdf_occurrence_is_accessible_and_navigation_wraps(self):
        self.paper()
        self.show(1250)
        app = self.app
        with patch.object(app.pdf_reader, "select_match") as selected_match:
            app.search_scope.set("PDFs")
            app.search.set("tantalum")
            self.wait(lambda: len(app.entries) == 1 and len(getattr(app, "preview_match_ranges", [])) == 5)
            entry = app.entries[0]
            self.assertEqual(entry["match_count"], 5)
            self.assertEqual(len(entry["match_excerpts"]), 5)
            self.assertEqual(app.match_count.get(), "Main search · Match 1 of 5")
            self.assertEqual(len(app.preview_match_ranges), 5)
            self.assertTrue(all(app.preview_match_ranges))
            self.assertFalse(app.previous_match_button.instate(["disabled"]))
            self.assertFalse(app.next_match_button.instate(["disabled"]))
            for index, (start, end, excerpt_index) in enumerate(app.preview_match_ranges):
                self.assertEqual(app.preview_text.get(start, end).casefold(), "tantalum")
                self.assertEqual(excerpt_index, index)
                self.assertEqual(bool(int(app.preview_text.tag_cget(app.match_excerpt_tags[index], "elide"))), index >= 3)
            for index in (1, 2, 3, 4, 0):
                app.next_match_button.invoke()
                self.assertEqual(app.current_match_index, index)
                self.assertEqual(app.match_count.get(), f"Main search · Match {index + 1} of 5")
                self.assertEqual(selected_match.call_args.args[0]["index"], index)
                selected = app.preview_text.tag_ranges("current_search_match")
                self.assertEqual(app.preview_text.get(*selected).casefold(), "tantalum")
                self.assertFalse(bool(int(app.preview_text.tag_cget(app.match_excerpt_tags[index], "elide"))))
            app.previous_match_button.invoke()
            self.assertEqual(app.current_match_index, 4)
            app.expand_matches_button.invoke()
            self.assertTrue(app.match_excerpts_expanded)
            self.assertTrue(all(not int(app.preview_text.tag_cget(tag, "elide")) for tag in app.match_excerpt_tags))
            app.expand_matches_button.invoke()
            self.assertFalse(app.match_excerpts_expanded)
            self.assertEqual(app.current_match_index, 4)
            self.assertFalse(int(app.preview_text.tag_cget(app.match_excerpt_tags[4], "elide")))
            self.assertTrue(int(app.preview_text.tag_cget(app.match_excerpt_tags[3], "elide")))

    def test_typed_note_keeps_details_and_selects_its_pdf_without_automatic_raster_preview(self):
        self.paper()
        app = self.app
        with patch.object(app, "load_pdf_search_preview") as rendered, \
                patch.object(app.context_executor, "submit") as context:
            row = next(row for row in app.notes.get_children() if app.entries[int(row)]["kind"] == "text")
            app.notes.selection_set(row)
            app.preview()
            self.root.update()
            self.assertIn("Typed observation", app.preview_text.get("1.0", "end"))
            self.assertEqual(app.pdf_reader.entry["key"], "typed")
            self.assertEqual(app.pdf_reader.entry["page"], 1)
            self.assertTrue(app.pdf_reader.awaiting_entry)
            self.assertIsNone(app.image)
            self.assertFalse(app.match_toolbar.winfo_ismapped())
            rendered.assert_not_called()
            context.assert_not_called()


if __name__ == "__main__":
    unittest.main()
