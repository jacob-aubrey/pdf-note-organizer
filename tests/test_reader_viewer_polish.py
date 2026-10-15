"""Compact Reader presentation and conservative, read-only popup detection."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf as fitz

from note_organizer.pdf_worker import _reader_location
from tests import test_reader_navigation_ui


class ReaderViewerPolishTests(unittest.TestCase):
    setUp = test_reader_navigation_ui.ReaderNavigationUITests.setUp
    tearDown = test_reader_navigation_ui.ReaderNavigationUITests.tearDown
    rows = test_reader_navigation_ui.ReaderNavigationUITests.rows
    replace = test_reader_navigation_ui.ReaderNavigationUITests.replace
    show = test_reader_navigation_ui.ReaderNavigationUITests.show

    def test_one_header_keeps_tabs_actions_navigation_and_counter_visible(self):
        app = self.replace(self.rows())
        self.show()
        controls = (app.note_view_button, app.pdf_view_button, app.source_button,
                    app.reader_expand_button, app.previous_match_button, app.next_match_button, app.match_count_label)
        for width in (1250, 940, 1500):
            self.root.geometry(f"{width}x760+0+0")
            self.root.update()
            left, right = app.reader_header.winfo_rootx(), app.reader_header.winfo_rootx() + app.reader_header.winfo_width()
            self.assertLess(app.reader_header.winfo_height(), 52)
            for widget in controls:
                self.assertTrue(widget.winfo_ismapped(), widget)
                self.assertGreaterEqual(widget.winfo_rootx(), left)
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right)
            self.assertLessEqual(app.previous_match_button.winfo_rootx() + app.previous_match_button.winfo_width(), app.next_match_button.winfo_rootx())
            self.assertLessEqual(app.next_match_button.winfo_rootx() + app.next_match_button.winfo_width(), app.match_count_label.winfo_rootx())
        self.assertEqual(app.source_button.cget("text"), "Open externally")

    def test_highlight_displays_once_with_inline_navigable_matches_and_no_image_row(self):
        app = self.replace(self.rows()[:1])
        self.show()
        app.note_view_button.invoke()
        self.root.update()
        body = app.preview_text.get("1.0", "end")
        self.assertEqual(body.count("Gold and more gold."), 1)
        self.assertNotIn("Main search matches", body)
        self.assertFalse(app.preview_actions.winfo_ismapped())
        self.assertEqual(len(app.preview_match_ranges), 2)
        for start, end, group in app.preview_match_ranges:
            self.assertEqual(app.preview_text.get(start, end).casefold(), "gold")
            self.assertIsNone(group)
        app.navigate_match(1)
        self.assertEqual(app.current_match_index, 1)
        self.assertTrue(app.pdf_reader.pending_match["fitWidth"])
        self.root.update()
        self.assertTrue(app.pdf_reader.pending_match["fitWidth"])

    def test_repeated_quote_and_comment_share_one_passage_and_both_fields_navigate(self):
        row = self.rows()[0]
        row["comment"] = row["quote"]
        app = self.replace([row])
        self.assertEqual(app.preview_text.get("1.0", "end").count(row["quote"]), 1)
        self.assertEqual(len(app.preview_match_ranges), 2)
        self.assertEqual(app.entries[0]["search_hits"][0]["fields"], ["quote", "comment"])
        self.assertTrue(all(app.preview_match_ranges))

    def test_general_conversion_advisory_moves_to_document_details(self):
        row = self.rows()[0]
        row["metadata"]["warnings"] = ["reMarkable pen placement uses calibrated coordinates; check a representative page against the tablet.", "Page 2: highlighted text unavailable."]
        app = self.replace([row])
        body = app.preview_text.get("1.0", "end")
        self.assertNotIn("calibrated coordinates", body)
        self.assertIn("highlighted text unavailable", body)
        details = app.reader_document_details()
        try:
            from note_organizer.widgets import ReadOnlyText
            frame = next(child for child in details.winfo_children())
            text = next(child for child in frame.winfo_children() if isinstance(child, ReadOnlyText)).text.get("1.0", "end")
            self.assertIn("general conversion advisory", text)
            self.assertIn(row["path"], text)
        finally:
            details.destroy()

    def test_view_buttons_and_reading_mode_follow_selection_and_change_icon(self):
        app = self.replace(self.rows())
        self.show()
        identity = app.pdf_reader.identity
        app.note_view_button.invoke()
        self.root.update()
        self.assertEqual(app.reader_view.get(), "note")
        self.assertEqual(app.reader_views.select(), str(app.note_details))
        self.assertEqual(app.reader_expand_button.icon_name, "maximize")
        app.toggle_reader_expanded()
        self.root.update()
        self.assertEqual(app.reader_expand_button.icon_name, "minimize")
        self.assertTrue(app.pdf_reader.expanded)
        app.toggle_reader_expanded()
        self.root.update()
        self.assertEqual(app.reader_expand_button.icon_name, "maximize")
        self.assertFalse(app.pdf_reader.expanded)
        self.assertEqual(app.reader_view.get(), "note")
        self.assertEqual(app.pdf_reader.identity, identity)

    def test_empty_results_remove_previous_additional_excerpt_actions(self):
        from note_organizer.research_search import hit_excerpts, _group_excerpts
        text = ("Gold passage. " + "ordinary context " * 30) * 5
        hits = hit_excerpts(text, "gold")
        row = self.rows()[0]
        row.update(kind="pdf", context=text, search_hits=hits, match_excerpts=_group_excerpts(hits))
        app = self.replace([row])
        self.show()
        app.reader_views.select(app.note_details)
        self.root.update()
        self.assertTrue(app.preview_actions.winfo_ismapped())
        self.replace([])
        self.root.update()
        self.assertFalse(app.preview_actions.winfo_ismapped())
        self.assertEqual(app.match_extra_groups, [])


class LegacyPopupDetectionTests(unittest.TestCase):
    def test_only_quote_only_legacy_import_is_suppressed_and_pdf_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "annotations.pdf"
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((40, 50), "current")
                region = page.search_for("current")
                ids = []
                for subject, content, author, modern in (
                        ("reMarkable highlight", "current", "", False),
                        ("reMarkable highlight", "An actual comment", "", False),
                        ("reMarkable highlight", "current", "A person", False),
                        ("PC highlight", "current", "", False),
                        ("reMarkable highlight", "current", "", True)):
                    annot = page.add_highlight_annot(region)
                    annot.set_info(subject=subject, content=content, title=author)
                    if modern:
                        document.xref_set_key(annot.xref, "RMQuote", fitz.get_pdf_str("current"))
                    annot.update()
                    ids.append(f"{annot.xref}R")
                document.save(path)
            before = path.read_bytes()
            first = _reader_location(path, 1)
            second = _reader_location(path, 1)
            self.assertEqual(first["suppressedPopupIds"], {"1": [ids[0]]})
            self.assertEqual(second, first)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
