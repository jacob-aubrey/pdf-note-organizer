"""Search authority, progress, and useful space in the Inbox review form."""
from concurrent.futures import Future
import unittest
from unittest.mock import patch

from note_organizer.research_search import enrich_note_matches
from tests import test_reader_navigation_ui


class ReaderUserUpdatesTests(unittest.TestCase):
    setUp = test_reader_navigation_ui.ReaderNavigationUITests.setUp
    tearDown = test_reader_navigation_ui.ReaderNavigationUITests.tearDown
    rows = test_reader_navigation_ui.ReaderNavigationUITests.rows
    replace = test_reader_navigation_ui.ReaderNavigationUITests.replace
    show = test_reader_navigation_ui.ReaderNavigationUITests.show

    def test_only_enabled_source_field_occurrences_receive_blue_marks(self):
        row = self.rows()[0]
        row.update(quote="Gold in an excluded quote.", comment="Gold in the enabled comment.")
        row["metadata"]["title"] = "Gold in an excluded title"
        row = enrich_note_matches(row, "gold", ["comment"])
        app = self.replace([row])
        self.show()
        app.note_view_button.invoke()
        self.root.update()
        ranges = app.preview_text.tag_ranges("search_match")
        self.assertEqual(len(ranges), 2)
        quote_start = app.preview_field_ranges["quote"][0]
        self.assertNotIn("search_match", app.preview_text.tag_names(quote_start))
        self.assertIn("search_match", app.preview_text.tag_names(app.preview_field_ranges["comment"][0]))
        self.assertEqual(app.preview_text.tag_cget("search_match", "background"), "#B9D1FF")
        self.assertEqual(app.preview_text.tag_cget("current_search_match", "background"), "#4169E1")
        self.assertEqual(app.pdf_reader.pending_match["mainHits"], row["search_hits"])

    def test_search_progress_stays_visible_until_current_query_finishes(self):
        app = self.replace(self.rows())
        self.show()
        app.search.set("another word")
        pending = Future()
        with patch.object(app.query_executor, "submit", return_value=pending):
            app.refresh_notes()
        self.root.update()
        self.assertTrue(app.reader_search_busy)
        self.assertTrue(app.search_progress.winfo_ismapped())
        self.assertIn("Searching notes", app.note_count.get())
        self.assertFalse(app.search_entry.instate(["disabled"]))
        stale = Future()
        stale.set_result([])
        app.finish_query(app.query_generation - 1, None, stale)
        self.assertTrue(app.reader_search_busy)
        pending.set_result([])
        app.finish_query(app.query_generation, None, pending)
        self.root.update()
        self.assertFalse(app.reader_search_busy)
        self.assertFalse(app.search_progress.winfo_ismapped())
        self.assertEqual(app.note_count.get(), "0 notes")

    def test_failed_search_stops_progress_and_keeps_input_editable(self):
        app = self.replace(self.rows())
        app.set_reader_search_busy(True)
        failure = Future()
        failure.set_exception(RuntimeError("Synthetic search failure"))
        app.finish_query(app.query_generation, None, failure)
        self.assertFalse(app.reader_search_busy)
        self.assertEqual(app.note_count.get(), "Could not load notes")
        self.assertFalse(app.search_entry.instate(["disabled"]))

    def test_clear_search_uses_the_larger_scaled_icon(self):
        app = self.app
        image = str(app.clear_search_button.cget("image")[0])
        expected = max(20, round(20 * float(self.root.tk.call("tk", "scaling")) / (96 / 72)))
        self.assertEqual(int(self.root.tk.call("image", "width", image)), expected)

    def test_inbox_details_expand_into_available_height(self):
        app = self.app
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        app.tabs.select(app.inbox_tab)
        view = app.inbox_view
        heights = []
        for height in (620, 950):
            self.root.geometry(f"1250x{height}+0+0")
            self.root.update()
            heights.append(view.details_display.winfo_height())
            canvas = view.editor_form.canvas
            bottom = view.details_display.winfo_rooty() + view.details_display.winfo_height()
            self.assertGreaterEqual(bottom, canvas.winfo_rooty() + canvas.winfo_height() - 5)
        self.assertGreater(heights[1], heights[0])
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main()
