"""Type ordering follows displayed annotation labels and keeps source identities."""
import copy
import unittest

import fitz

from note_organizer.reader_results import ordered_rows, result_type
from note_organizer.storage import digest_file
from tests import test_review_controls
from tests.ui_helpers import settle_library


def entry(kind, title="Alpha study", page=1, key=None):
    return {"path": f"{title}.pdf", "kind": kind, "metadata": {"title": title},
            "page": page, "key": key or f"{kind}-{title}-{page}", "rect": [1, 2, 3, 4]}


class ReaderTypeSortTests(unittest.TestCase):
    def test_displayed_types_include_notes_and_unknown_kinds(self):
        self.assertEqual([result_type(entry(kind)) for kind in ("drawing", "highlight", "text", "pdf", "stamp")],
                         ["Drawing", "Highlight", "Note", "PDF", "Stamp"])

    def test_type_order_then_paper_then_numeric_page_in_both_directions(self):
        entries = [entry("highlight", "Zulu study", 2), entry("highlight", page=10),
                   entry("pdf", page=1), entry("drawing", page=10), entry("text", page=1),
                   entry("highlight", page=2), entry("drawing", page=2)]
        rows = [str(index) for index in range(len(entries))]
        original = copy.deepcopy(entries)
        self.assertEqual(ordered_rows(entries, rows, "kind"), ["6", "3", "5", "1", "0", "4", "2"])
        self.assertEqual(ordered_rows(entries, rows, "kind", True), ["2", "4", "5", "1", "0", "6", "3"])
        self.assertEqual(entries, original)
        self.assertEqual(rows, [str(index) for index in range(len(entries))])

    def test_paper_grouping_keeps_all_note_types_before_pdfs(self):
        entries = [entry("pdf", page=1), entry("drawing", page=10), entry("highlight", page=2),
                   entry("text", page=1), entry("highlight", "Zulu study", 1)]
        self.assertEqual(ordered_rows(entries, ["0", "1", "2", "3", "4"]), ["3", "2", "1", "0", "4"])

    def test_type_order_accepts_filtered_rows_and_keeps_layout_order_on_same_page(self):
        entries = [entry("highlight", key="bottom"), entry("highlight", key="top"), entry("drawing"), entry("text")]
        entries[0]["rect"] = [1, 100, 3, 104]
        self.assertEqual(ordered_rows(entries, ["0", "2", "1"], "kind"), ["2", "1", "0"])


class ReaderTypeSortUITests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait

    def test_header_sorts_drawings_highlights_and_notes_preserving_selection(self):
        project = self.store.add_project(self.pc)
        path = self.pc / "types.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((50, 75), "Annotation sorting example")
            document.save(path)
        self.store.save_scan(project, path, digest_file(path), "sig", "settings", {"title": "Types", "pages": 1}, [
            {"key": kind, "kind": kind, "page": 1, "rect": [1, index * 5, 3, index * 5 + 4],
             "comment": f"{kind} annotation"}
            for index, kind in enumerate(("text", "highlight", "drawing"))])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.wait(lambda: len(self.app.entries) == 3 and len(self.app.notes.get_children()) == 3)
        app = self.app
        row = next(row for row in app.notes.get_children() if app.entries[int(row)]["kind"] == "highlight")
        app.notes.selection_set(row)
        selected = app.selected_entry()["document_id"], app.selected_entry()["key"]

        def displayed():
            return [app.notes.set(row, "kind") for row in app.notes.get_children()]

        self.root.tk.call(app.notes.heading("kind", "command"))
        self.assertEqual(displayed(), ["Drawing", "Highlight", "Note"])
        self.assertEqual(app.notes.selection(), (row,))
        self.assertEqual((app.selected_entry()["document_id"], app.selected_entry()["key"]), selected)
        self.root.tk.call(app.notes.heading("kind", "command"))
        self.assertEqual(displayed(), ["Note", "Highlight", "Drawing"])
        self.assertEqual(app.notes.selection(), (row,))
        self.assertEqual((app.selected_entry()["document_id"], app.selected_entry()["key"]), selected)


if __name__ == "__main__":
    unittest.main()
