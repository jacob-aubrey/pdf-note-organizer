"""Document identity stays visible without duplicating page or note content."""
import unittest

from note_organizer.research_search import enrich_note_matches
from tests import test_reader_navigation_ui


class ReaderDocumentTitleTests(unittest.TestCase):
    setUp = test_reader_navigation_ui.ReaderNavigationUITests.setUp
    tearDown = test_reader_navigation_ui.ReaderNavigationUITests.tearDown
    rows = test_reader_navigation_ui.ReaderNavigationUITests.rows
    replace = test_reader_navigation_ui.ReaderNavigationUITests.replace
    show = test_reader_navigation_ui.ReaderNavigationUITests.show

    def test_heading_is_separate_from_scrolling_note_and_page_metadata(self):
        row = self.rows()[0]
        row["metadata"]["title"] = "Advances in Ultrasmall Inorganic Nanoparticles"
        row["quote"] = "Gold note text.\n" * 160
        app = self.replace([row])
        self.show()
        app.note_view_button.invoke()
        self.root.update()
        heading = app.note_document_title
        body = app.preview_text.get("1.0", "end")
        self.assertEqual(heading.title, row["metadata"]["title"])
        self.assertEqual(heading.tooltip.text(), heading.title)
        self.assertTrue(heading.winfo_ismapped())
        self.assertNotIn(heading.title, body)
        self.assertNotIn("PDF page", body)
        position = heading.winfo_rooty()
        app.preview_text.yview_moveto(1)
        self.root.update()
        self.assertEqual(heading.winfo_rooty(), position)
        self.assertTrue(heading.winfo_ismapped())
        self.assertGreater(float(app.preview_text.yview()[0]), 0)

    def test_long_title_bounds_height_and_recovers_on_resize(self):
        title = ("Advances in Ultrasmall Inorganic Nanoparticles for Nanomedicine: From Diagnosis to Therapeutics. "
                 "New Directions in Biomedical Imaging and Targeted Nanoparticle Therapy")
        row = self.rows()[0]
        row["metadata"]["title"] = title
        app = self.replace([row])
        self.show()
        app.note_view_button.invoke()
        heading = app.note_document_title
        for width in (940, 1500, 940):
            self.root.geometry(f"{width}x760+0+0")
            self.root.update()
            text = heading.cget("text")
            self.assertLessEqual(len(text.splitlines()), 2)
            for line in text.splitlines():
                self.assertLessEqual(heading.title_font.measure(line), heading.winfo_width() - 24)
            self.assertEqual(heading.tooltip.text(), title)
            self.assertLessEqual(heading.winfo_height(), heading.title_font.metrics("linespace") * 2 + 12)
        self.assertTrue(heading.cget("text").endswith("…"))
        app.toggle_reader_expanded()
        app.note_view_button.invoke()
        self.root.geometry("1900x900+0+0")
        self.root.update()
        self.assertEqual(" ".join(heading.cget("text").split()), title)
        app.toggle_reader_expanded()
        self.root.update()
        self.assertEqual(heading.title, title)
        self.assertFalse(self.errors)

    def test_heading_tracks_paper_navigation_and_clears_when_results_empty(self):
        app = self.replace(self.rows())
        self.show()
        app.note_view_button.invoke()
        self.root.update()
        self.assertEqual(app.note_document_title.title, "Alpha")
        app.navigate_match(-1)
        self.root.update()
        self.assertEqual(app.note_document_title.title, "Beta")
        self.replace([])
        self.assertEqual(app.note_document_title.title, "")
        self.assertEqual(app.note_document_title.cget("text"), "")
        self.assertFalse(app.note_document_title.winfo_ismapped())
        self.replace(self.rows())
        self.assertTrue(app.note_document_title.winfo_ismapped())

    def test_removed_title_note_field_does_not_create_navigation_occurrences(self):
        row = self.rows()[0]
        row["metadata"]["title"] = "Gold nanoparticles and gold contrast agents " + "for diagnosis " * 25
        row["quote"] = "An unrelated highlighted sentence."
        row = enrich_note_matches(row, "gold", ["title"])
        app = self.replace([row])
        app.search_fields = ["title"]
        self.show()
        app.note_view_button.invoke()
        self.root.update()
        self.assertEqual(len(app.preview_match_ranges), 0)
        self.assertNotIn("title", app.preview_field_ranges)
        self.assertNotIn("paper title", app.preview_text.get("1.0", "end").casefold())
        self.assertEqual(app.note_document_title.title, row["metadata"]["title"].strip())

    def test_reading_mode_keeps_note_heading_and_reader_position(self):
        app = self.replace(self.rows())
        self.show()
        app.note_view_button.invoke()
        self.root.update()
        app.pdf_reader.state = {"page": 7, "scale": 1.9, "scrollTop": 840}
        generation, identity = app.pdf_reader.generation, app.pdf_reader.identity
        app.toggle_reader_expanded()
        app.note_view_button.invoke()
        self.root.update()
        self.assertTrue(app.note_document_title.winfo_ismapped())
        self.assertEqual(app.note_document_title.title, "Alpha")
        app.toggle_reader_expanded()
        self.root.update()
        self.assertEqual(app.pdf_reader.generation, generation)
        self.assertEqual(app.pdf_reader.identity, identity)
        self.assertEqual(app.pdf_reader.state["scrollTop"], 840)
        self.assertTrue(app.note_document_title.winfo_ismapped())

    def test_title_metadata_refresh_updates_heading_for_same_result(self):
        app = self.replace(self.rows()[:1])
        app.entries[0]["logical_paper_title"] = "Updated citation title"
        app.preview()
        self.assertEqual(app.note_document_title.title, "Updated citation title")


if __name__ == "__main__":
    unittest.main()
