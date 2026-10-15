"""Accessible snapshots retain mixed-reader identity and displayed ordering."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from note_organizer.accessible_reader import open_reader, render


class AccessibleReaderTests(unittest.TestCase):
    def entry(self, **changes):
        return {"document_id": "paper-id", "key": "pdf-document", "kind": "pdf",
                "pdf_document": True, "path": str(Path.cwd() / "paper.pdf"),
                "page": 1, "page_count": None, "metadata": {"title": "Paper title", "pages": 8},
                "quote": "", "context": "", "missing": False, **changes}

    def test_document_rows_identify_files_without_claiming_a_page_match(self):
        page = render([self.entry()])
        self.assertIn('<p class="location">PDF document</p>', page)
        self.assertIn("File: paper.pdf", page)
        self.assertIn(">Open source PDF</a>", page)
        self.assertNotIn("PDF page 1", page)
        self.assertNotIn("#page=", page)
        self.assertIn("items shown", page)

    def test_missing_document_preserves_identity_and_has_no_dead_source_link(self):
        page = render([self.entry(missing=True)])
        self.assertIn("Paper title", page)
        self.assertIn("File: paper.pdf", page)
        self.assertIn("Source PDF is unavailable", page)
        self.assertNotIn("<a href=", page)
        self.assertNotIn("PDF page 1", page)

    def test_matching_pages_keep_page_numbers_excerpts_and_source_links(self):
        entry = self.entry(key="pdf-page:3", pdf_document=False, page=3, page_count=8,
                           pdf_label="iii", quote="A gold match", context="Gold in a larger context")
        page = render([entry])
        self.assertIn("PDF page 3 of 8 · PDF label iii · pdf", page)
        self.assertIn("A gold match", page)
        self.assertIn("Gold in a larger context", page)
        self.assertIn("#page=3", page)
        self.assertIn(">Open source PDF at page 3</a>", page)

    def test_note_text_is_escaped_and_drawing_images_still_load(self):
        loader = Mock(return_value="encoded-image")
        entry = self.entry(key="drawing", kind="drawing", pdf_document=False,
                           comment='<script>alert("unsafe")</script>', ocr="Drawing transcription")
        page = render([entry], loader)
        loader.assert_called_once_with(entry)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('<script>alert("unsafe")</script>', page)
        self.assertIn("Drawing transcription", page)
        self.assertIn("data:image/png;base64,encoded-image", page)

    def test_snapshot_uses_visible_rows_in_their_current_sort_order(self):
        with tempfile.TemporaryDirectory() as folder:
            entries = [self.entry(metadata={"title": "First backend result"}),
                       self.entry(document_id="second", metadata={"title": "First displayed result"}),
                       self.entry(document_id="hidden", metadata={"title": "Not displayed"})]
            app = SimpleNamespace(entries=entries, notes=Mock(), notify=Mock(), store=Mock(), data_dir=Path(folder))
            app.notes.get_children.return_value = ("1", "0")
            saved = []
            with patch("note_organizer.accessible_reader.background",
                       side_effect=lambda _app, prepare, *_: saved.append(prepare())):
                open_reader(app)
            page = saved[0].read_text(encoding="utf-8")
            self.assertLess(page.index("First displayed result"), page.index("First backend result"))
            self.assertNotIn("Not displayed", page)
            app.store.entry_image.assert_not_called()


if __name__ == "__main__":
    unittest.main()
