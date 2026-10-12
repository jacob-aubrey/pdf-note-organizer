"""Physical PDF positions never inherit publisher labels or inferred journal pages."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import fitz

from note_organizer.extraction import extract
from note_organizer.exporting import build_notebook
from note_organizer.pages import page_description, page_tooltip, page_search_text
from note_organizer.storage import DEFAULT_SETTINGS, Store, matches_search


class PageNumberTests(unittest.TestCase):
    def test_extraction_tracks_physical_page_and_embedded_label_separately(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), tempfile.TemporaryDirectory() as folder:
                pdf = Path(folder) / "article.pdf"
                with fitz.open() as doc:
                    for index in range(2):
                        page = doc.new_page(width=612, height=792)
                        page.insert_text((50, 70), "A highlighted journal passage")
                        page.add_highlight_annot(page.search_for("highlighted journal passage"))
                        page.set_rotation(rotation)
                    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 233}])
                    doc.save(pdf)
                _, _, metadata, entries = extract(pdf, DEFAULT_SETTINGS)
                self.assertEqual([e["page"] for e in entries], [1, 2])
                self.assertEqual([e["pdf_label"] for e in entries], ["233", "234"])
                self.assertEqual([e["page_count"] for e in entries], [2, 2])
                self.assertEqual(page_description(entries[0]), "PDF page 1 of 2 · PDF label 233")
                self.assertNotIn("Journal", page_description(entries[0]))
                self.assertIn("not a verified journal", page_tooltip(entries[0]))
                self.assertEqual(metadata["pages"], 2)

    def test_no_embedded_label_is_not_reported_as_journal_number(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / "article.pdf"
            with fitz.open() as doc:
                page = doc.new_page()
                page.add_text_annot((50, 70), "Read this")
                doc.save(pdf)
            _, _, _, entries = extract(pdf, DEFAULT_SETTINGS)
            self.assertEqual(entries[0]["pdf_label"], "")
            self.assertEqual(entries[0]["label"], "1")
            self.assertEqual(page_description(entries[0]), "PDF page 1 of 1")

    def test_legacy_scans_show_physical_page_first_without_inference(self):
        legacy = {"page": 3, "label": "2457", "metadata": {"pages": 12}}
        self.assertEqual(page_description(legacy), "PDF page 3 of 12 · PDF label 2457")
        self.assertEqual(page_description({"page": 3, "label": "3"}), "PDF page 3")
        self.assertEqual(page_description({"page": 3, "pdf_label": "", "label": "2457"}), "PDF page 3")

    def test_journal_page_requires_explicit_verification(self):
        entry = {"page": 3, "page_count": 12, "pdf_label": "iii", "journal_page": "2457"}
        self.assertEqual(page_description(entry), "PDF page 3 of 12 · PDF label iii")
        self.assertNotIn("2457", page_search_text(entry))
        for unverified in (False, None, "true", 1):
            self.assertNotIn("Journal", page_description({**entry, "journal_page_verified": unverified}))
        verified = {**entry, "journal_page_verified": True}
        self.assertEqual(page_description(verified), "PDF page 3 of 12 · Journal p. 2457")
        self.assertIn("2457", page_search_text(verified))

    def test_search_distinguishes_physical_label_and_verified_journal(self):
        entry = {"path": "article.pdf", "kind": "highlight", "page": 3, "pdf_label": "iii",
                 "journal_page": "2457", "journal_page_verified": True}
        for query in ("3", "iii", "2457"):
            self.assertTrue(matches_search(entry, query, ["page"], "Exact phrase", "All notes"))
        self.assertFalse(matches_search({**entry, "journal_page_verified": False}, "2457", ["page"], "Exact phrase", "All notes"))

    def test_both_exports_share_page_description_and_physical_link(self):
        entry = {"path": "article.pdf", "page": 3, "page_count": 12, "label": "2457",
                 "pdf_label": "2457", "rect": [0, 0, 10, 10], "key": "mark",
                 "kind": "highlight", "quote": "A passage", "comment": "", "ocr": "",
                 "metadata": {}, "journal_page": "2457", "journal_page_verified": True}
        for layout in ("Reading", "Detailed"):
            with self.subTest(layout=layout):
                notebook = build_notebook("Notes", [entry], layout=layout)
                headings = [p for p in notebook.paragraphs if p.style.name == "Heading 2"]
                # Word hyperlink text lives outside python-docx's Paragraph.text.
                self.assertIn("PDF page 3 of 12 · Journal p. 2457", headings[0]._p.xml)
                output = BytesIO()
                notebook.save(output)
                with zipfile.ZipFile(output) as archive:
                    relationships = archive.read("word/_rels/document.xml.rels").decode()
                self.assertIn("#page=3", relationships)
                self.assertNotIn("#page=2457", relationships)
                self.assertEqual(entry["page"], 3)

    def test_invalid_page_totals_do_not_create_misleading_descriptions(self):
        for total in (0, -1, "abc", True, 2, "2.5"):
            self.assertEqual(page_description({"page": 3, "page_count": total}), "PDF page 3")


class ProcessingDefaultTests(unittest.TestCase):
    def test_new_folders_use_defaults_and_existing_folders_keep_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "library.sqlite3")
            old_id = store.add_project(Path(folder) / "old")
            defaults = {**DEFAULT_SETTINGS, "grouping": "Whole page", "ocr": True, "gap": 12}
            store.set_preference("default_settings", defaults)
            new_id = store.add_project(Path(folder) / "new")
            self.assertEqual(store.default_settings(), defaults)
            self.assertEqual(json.loads(store.project(new_id)["settings"]), defaults)
            self.assertEqual(json.loads(store.project(old_id)["settings"]), DEFAULT_SETTINGS)
            store.add_project(Path(folder) / "old")
            self.assertEqual(json.loads(store.project(old_id)["settings"]), DEFAULT_SETTINGS)

    def test_invalid_saved_default_container_uses_builtins(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "library.sqlite3")
            store.set_preference("default_settings", "invalid")
            self.assertEqual(store.default_settings(), DEFAULT_SETTINGS)


if __name__ == "__main__":
    unittest.main()
