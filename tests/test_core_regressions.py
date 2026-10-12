"""Synthetic PDF cases found in the full application audit."""
from pathlib import Path
import tempfile
import unittest
from io import BytesIO
import json
from unittest.mock import patch
import zipfile

import fitz

from note_organizer.extraction import extract, scan_fingerprint, snapshot
from note_organizer.exporting import build_notebook, paper_title
from note_organizer.storage import DEFAULT_SETTINGS, digest_file


class AnnotationBoundsTests(unittest.TestCase):
    def test_off_page_ink_does_not_discard_valid_highlights(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), tempfile.TemporaryDirectory() as tmp:
                pdf = Path(tmp) / "paper.pdf"
                with fitz.open() as doc:
                    page = doc.new_page(width=612, height=792)
                    page.insert_text((40, 50), "A valid highlighted passage")
                    page.add_highlight_annot(page.search_for("valid highlighted passage"))
                    page.add_ink_annot([[(700, 900), (710, 910), (720, 900)]])
                    page.set_rotation(rotation)
                    doc.save(pdf)
                original = digest_file(pdf)
                _, _, metadata, entries = extract(pdf, DEFAULT_SETTINGS)
                self.assertEqual([e["quote"] for e in entries], ["valid highlighted passage"])
                self.assertFalse(entries[0]["image"])
                self.assertIn("outside the visible page", " ".join(metadata["warnings"]))
                self.assertEqual(digest_file(pdf), original)

    def test_partially_visible_ink_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=612, height=792)
                page.add_ink_annot([[(600, 760), (620, 780), (630, 800)]])
                doc.save(pdf)
            _, _, metadata, entries = extract(pdf, DEFAULT_SETTINGS)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["kind"], "drawing")
            self.assertTrue(entries[0]["image"])
            self.assertFalse(metadata["warnings"])


class DrawingPreviewPolicyTests(unittest.TestCase):
    def test_only_drawing_previews_render_and_full_text_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            with fitz.open() as doc:
                page = doc.new_page()
                page.insert_text((40, 50), "An annotated journal passage")
                highlight = page.add_highlight_annot(page.search_for("annotated journal passage"))
                highlight.set_info(content="Check this highlighted claim")
                highlight.update()
                page.add_text_annot((40, 100), "A complete typed observation")
                page.add_ink_annot([[(80, 160), (90, 175), (100, 160)]])
                doc.save(pdf)
            with patch("note_organizer.extraction.snapshot", wraps=snapshot) as renderer:
                _, _, metadata, entries = extract(pdf, DEFAULT_SETTINGS)
            self.assertEqual(renderer.call_count, 1)
            self.assertEqual({e["kind"] for e in entries if e["image"]}, {"drawing"})
            self.assertEqual(next(e["quote"] for e in entries if e["kind"] == "highlight"),
                             "annotated journal passage")
            self.assertEqual(next(e["comment"] for e in entries if e["kind"] == "text"),
                             "A complete typed observation")
            for entry in entries:
                entry.update(path=str(pdf), metadata=metadata)
            notebook = build_notebook("Research notes", entries)
            text = "\n".join(p.text for p in notebook.paragraphs)
            self.assertIn("annotated journal passage", text)
            self.assertIn("Check this highlighted claim", text)
            self.assertIn("A complete typed observation", text)
            self.assertEqual(len(notebook.inline_shapes), 1)
            output = BytesIO()
            notebook.save(output)
            with zipfile.ZipFile(output) as archive:
                relationships = archive.read("word/_rels/document.xml.rels").decode()
            self.assertIn(pdf.resolve().as_uri() + "#page=1", relationships)

    def test_fingerprint_refreshes_previous_policy_once(self):
        fingerprint = scan_fingerprint(DEFAULT_SETTINGS)
        self.assertEqual(json.loads(fingerprint)["preview_policy"], "drawings")
        self.assertEqual(fingerprint, scan_fingerprint({**DEFAULT_SETTINGS, "notebook_style": "Detailed"}))
        self.assertEqual(fingerprint, scan_fingerprint({**DEFAULT_SETTINGS, "preview_policy": "all"}))

    def test_export_ignores_legacy_images_for_highlights_and_typed_notes(self):
        entries = [{"path": "paper.pdf", "page": 1, "label": "1", "rect": [0, 0, 10, 10],
                    "key": kind, "kind": kind, "quote": "", "comment": "A complete note",
                    "ocr": "", "image": "invalid legacy image", "metadata": {}}
                   for kind in ("highlight", "text", "freetext")]
        for layout in ("Reading", "Detailed"):
            with self.subTest(layout=layout):
                notebook = build_notebook("Notes", entries, layout=layout)
                self.assertEqual(len(notebook.inline_shapes), 0)
                self.assertIn("A complete note", "\n".join(p.text for p in notebook.paragraphs))

    def test_numeric_html_entities_are_readable_in_both_notebook_titles(self):
        title = "Dual&#x2010;energy CT &amp; imaging"
        expected = "Dual‐energy CT & imaging"
        self.assertEqual(paper_title("paper.pdf", {"title": title}), expected)
        entry = {"path": "paper.pdf", "page": 1, "label": "1", "rect": [0, 0, 10, 10],
                 "key": "note", "kind": "text", "quote": "", "comment": "A note", "ocr": "",
                 "metadata": {"title": title}}
        for layout in ("Reading", "Detailed"):
            with self.subTest(layout=layout):
                notebook = build_notebook("Notes", [entry], layout=layout)
                self.assertEqual([p.text for p in notebook.paragraphs if p.style.name == "Heading 1"], [expected])


class RemarkableQuoteTests(unittest.TestCase):
    def test_separate_tablet_quote_preserves_genuine_contents_and_replies(self):
        tablet_quote = "Full tablet-selected quote: CT ‐ imaging"
        for comment in ("My interpretation of this passage", tablet_quote):
            with self.subTest(comment=comment), tempfile.TemporaryDirectory() as tmp:
                pdf = Path(tmp) / "paper.pdf"
                with fitz.open() as doc:
                    page = doc.new_page()
                    page.insert_text((40, 50), "Printed passage")
                    highlight = page.add_highlight_annot(page.search_for("Printed passage"))
                    highlight.set_info(subject="reMarkable highlight", content=comment)
                    highlight.update()
                    doc.xref_set_key(highlight.xref, "RMQuote", fitz.get_pdf_str(tablet_quote))
                    reply = page.add_text_annot((80, 100), "Further discussion")
                    reply.set_irt_xref(highlight.xref)
                    reply.update()
                    doc.save(pdf)
                _, _, _, entries = extract(pdf, DEFAULT_SETTINGS)
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["quote"], tablet_quote)
                self.assertEqual(entries[0]["comment"], comment + "\nFurther discussion")
                self.assertFalse(entries[0]["image"])

    def test_legacy_copied_contents_is_quote_without_duplicate_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            with fitz.open() as doc:
                page = doc.new_page()
                page.insert_text((40, 50), "Printed passage")
                highlight = page.add_highlight_annot(page.search_for("Printed passage"))
                highlight.set_info(subject="reMarkable highlight", content="Legacy tablet-selected quotation")
                highlight.update()
                reply = page.add_text_annot((80, 100), "A genuine reply")
                reply.set_irt_xref(highlight.xref)
                reply.update()
                doc.save(pdf)
            _, _, _, entries = extract(pdf, DEFAULT_SETTINGS)
            self.assertEqual(entries[0]["quote"], "Legacy tablet-selected quotation")
            self.assertEqual(entries[0]["comment"], "A genuine reply")


if __name__ == "__main__":
    unittest.main()
