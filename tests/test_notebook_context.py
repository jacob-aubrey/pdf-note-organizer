"""Drawing close-ups retain a direct link to their full physical PDF page."""
import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
import zipfile

from docx import Document
from PIL import Image

from note_organizer.exporting import EXPORT_FORMAT_REVISION, build_notebook, export_notebook
from note_organizer.storage import digest_file


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def drawing(path, page=3, color="red", **overrides):
    image = BytesIO()
    Image.new("RGB", (160, 80), color).save(image, format="PNG")
    return {"path": str(path), "page": page, "page_count": 12,
            "pdf_label": "2457", "journal_page": "2457", "journal_page_verified": True,
            "rect": [0, 0, 80, 40], "key": "mark", "kind": "drawing",
            "quote": "", "comment": "Synthetic handwriting", "ocr": "", "metadata": {},
            "image": base64.b64encode(image.getvalue()).decode(), **overrides}


def document_xml(document):
    output = BytesIO()
    document.save(output)
    with zipfile.ZipFile(output) as archive:
        xml = ET.fromstring(archive.read("word/document.xml"))
        relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
    return xml, {item.get("Id"): item for item in relationships}, media


class NotebookContextTests(unittest.TestCase):
    def test_each_close_up_links_to_its_source_and_physical_page_in_both_layouts(self):
        with tempfile.TemporaryDirectory() as folder:
            # The expanded converted PDF is the source, including its tablet margins.
            source = Path(folder) / "Paper #1 (reMarkable).pdf"
            entries = [drawing(source), drawing(source, page=4, color="blue")]
            original = deepcopy(entries)
            for layout in ("Reading", "Detailed"):
                with self.subTest(layout=layout):
                    doc = build_notebook("Notes", entries, layout=layout)
                    xml, relationships, media = document_xml(doc)
                    paragraphs = xml.findall("w:body/w:p", NS)
                    links = []
                    for index, paragraph in enumerate(paragraphs):
                        for link in paragraph.findall("w:hyperlink", NS):
                            label = "".join(link.itertext())
                            if not label.startswith("Full page context"):
                                continue
                            links.append(label)
                            page = int(label.rsplit(" ", 1)[1])
                            relationship = relationships[link.get(f"{{{NS['r']}}}id")]
                            self.assertEqual(relationship.get("Target"), source.as_uri() + f"#page={page}")
                            self.assertEqual(relationship.get("TargetMode"), "External")
                            self.assertIsNotNone(paragraphs[index - 1].find(".//w:drawing", NS))
                            self.assertIsNotNone(paragraphs[index - 1].find("w:pPr/w:keepNext", NS))
                            self.assertEqual(paragraph.find("w:pPr/w:pStyle", NS).get(f"{{{NS['w']}}}val"), "Caption")
                    self.assertEqual(links, ["Full page context — PDF page 3", "Full page context — PDF page 4"])
                    self.assertEqual(len(doc.inline_shapes), 2)
                    self.assertEqual(len(media), 2)
                    self.assertNotIn("Original page with annotations", ET.tostring(xml, encoding="unicode"))
            self.assertEqual(entries, original)

    def test_context_links_follow_only_retained_drawing_previews(self):
        source = Path("article.pdf").resolve()
        first = drawing(source)
        entries = [first, {**first, "key": "duplicate", "rect": [0, 50, 80, 90]},
                   drawing(source, kind="highlight", image="unused invalid image"),
                   drawing(source, kind="text", image="unused invalid image"),
                   drawing(source, image=None)]
        # Identical pixels at different or unknown crop locations must not
        # suppress a separate annotation's visual context.
        for layout, expected in (("Reading", 2), ("Detailed", 2)):
            with self.subTest(layout=layout):
                doc = build_notebook("Notes", entries, layout=layout)
                xml, _, _ = document_xml(doc)
                labels = ["".join(link.itertext()) for link in xml.findall(".//w:hyperlink", NS)]
                self.assertEqual(labels.count("Full page context — PDF page 3"), expected)
                self.assertEqual(len(doc.inline_shapes), expected)

    def test_exports_stamp_format_revision_even_when_empty(self):
        for layout in ("Reading", "Detailed"):
            with self.subTest(layout=layout):
                self.assertEqual(build_notebook("Notes", [], layout=layout).core_properties.version,
                                 str(EXPORT_FORMAT_REVISION))

    def test_existing_unedited_notebook_can_refresh_links_without_a_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Notes.docx"
            previous = Document()
            previous.core_properties.version = "1"
            previous.save(output)
            old_hash = digest_file(output)
            new_hash, backup = export_notebook(output, "Notes", [drawing(Path(folder) / "article.pdf")],
                                              expected_hash=old_hash)
            refreshed = Document(output)
            xml, _, _ = document_xml(refreshed)
            self.assertEqual(refreshed.core_properties.version, str(EXPORT_FORMAT_REVISION))
            self.assertIn("Full page context — PDF page 3", "".join(xml.itertext()))
            self.assertEqual(new_hash, digest_file(output))
            self.assertNotEqual(new_hash, old_hash)
            self.assertEqual(backup, "")
            self.assertFalse((output.parent / "Notebook backups").exists())


if __name__ == "__main__":
    unittest.main()
