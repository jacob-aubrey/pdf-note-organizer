"""Notebook image consolidation preserves independent saved annotation data."""
import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
from PIL import Image

from note_organizer.extraction import snapshot
from note_organizer.exporting import build_notebook, consolidate_drawing_previews
from note_organizer.storage import Store, digest_file
from tests.test_notebook_context import drawing, document_xml


class NotebookConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.pdf = self.folder / "Annotated paper.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page(width=400, height=500)
            for y in range(55, 220, 20):
                page.insert_text((35, y), f"Printed context on line {y}")
            for y, color in ((85, (1, 0, 0)), (180, (0, 0, 1))):
                ink = page.add_ink_annot([[(55, y), (65, y + 12), (80, y)]])
                ink.set_colors(stroke=color)
                ink.update()
            pdf.save(self.pdf)

    def tearDown(self):
        self.temp.cleanup()

    def entry(self, crop, index, rotation=0, **overrides):
        with fitz.open(self.pdf) as pdf:
            pdf[0].set_rotation(rotation)
            image = snapshot(pdf[0], fitz.Rect(crop))
        return drawing(self.pdf, page=1, key=f"mark-{index}", crop=crop,
                       rect=[50, 80 + index * 50, 85, 95 + index * 50],
                       comment=f"Separate observation {index}", ocr=f"Transcription {index}",
                       image=image, source_digest=digest_file(self.pdf), **overrides)

    def test_overlapping_windows_share_one_union_and_link_in_both_layouts(self):
        entries = [self.entry([20, 40, 220, 150], 0), self.entry([20, 100, 220, 210], 1)]
        original = deepcopy(entries)
        with fitz.open(self.pdf) as pdf:
            expected = snapshot(pdf[0], fitz.Rect(20, 40, 220, 210))
        for layout in ("Reading", "Detailed"):
            with self.subTest(layout=layout):
                document = build_notebook("Consolidated reading notes", entries, layout)
                self.assertEqual(len(document.inline_shapes), 1)
                xml, _, _ = document_xml(document)
                self.assertEqual("".join(xml.itertext()).count("Full page context — PDF page 1"), 1)
                text = "\n".join(p.text for p in document.paragraphs)
                for entry in entries:
                    self.assertIn(entry["comment"], text)
                    self.assertIn(entry["ocr"], text)
                image = document.inline_shapes[0]._inline.graphic.graphicData.pic.blipFill.blip
                raw = document.part.related_parts[image.embed].blob
                self.assertEqual(raw, base64.b64decode(expected))
        self.assertEqual(entries, original)

    def test_covering_saved_crop_is_reused_even_when_source_is_unavailable(self):
        entries = [self.entry([20, 40, 220, 150], 0), self.entry([10, 20, 240, 220], 1)]
        original = deepcopy(entries)
        self.pdf.unlink()
        with patch("note_organizer.exporting.snapshot", side_effect=AssertionError("No source needed")):
            result = consolidate_drawing_previews(entries)
        self.assertEqual([e["image"] for e in result], ["", entries[1]["image"]])
        self.assertEqual(entries, original)

    def test_distinct_windows_padding_slivers_pages_sources_and_revisions_stay_separate(self):
        first = self.entry([20, 40, 220, 150], 0)
        for second in (self.entry([20, 148, 220, 240], 1),
                       self.entry([240, 260, 380, 420], 1),
                       {**self.entry([20, 100, 220, 210], 1), "page": 2},
                       {**self.entry([20, 100, 220, 210], 1), "path": str(self.folder / "Other.pdf")},
                       {**self.entry([20, 100, 220, 210], 1), "source_digest": "another revision"}):
            with self.subTest(crop=second["crop"], page=second["page"], path=second["path"]):
                result = consolidate_drawing_previews([first, second])
                self.assertEqual([e["image"] for e in result], [first["image"], second["image"]])

    def test_expanding_union_does_not_absorb_a_note_in_its_empty_corner(self):
        # A and B overlap, but C only lies inside their union's blank corner.
        entries = [self.entry([10, 20, 150, 210], 0),
                   self.entry([50, 150, 230, 250], 1),
                   self.entry([170, 30, 220, 90], 2)]
        result = consolidate_drawing_previews(entries)
        self.assertFalse(result[0]["image"])
        self.assertTrue(result[1]["image"])
        self.assertEqual(result[2]["image"], entries[2]["image"])

    def test_missing_changed_unverified_or_failed_source_retains_both_saved_previews(self):
        entries = [self.entry([20, 40, 220, 150], 0), self.entry([20, 100, 220, 210], 1)]
        with patch("note_organizer.exporting.snapshot", side_effect=RuntimeError("render unavailable")):
            self.assertEqual(consolidate_drawing_previews(entries), entries)
        with patch("note_organizer.exporting.digest_file", side_effect=[entries[0]["source_digest"], "changed while rendering"]):
            self.assertEqual(consolidate_drawing_previews(entries), entries)
        unverified = [{key: value for key, value in e.items() if key != "source_digest"} for e in entries]
        self.assertEqual(consolidate_drawing_previews(unverified), unverified)
        self.pdf.write_bytes(b"Different source revision")
        self.assertEqual(consolidate_drawing_previews(entries), entries)
        self.pdf.unlink()
        self.assertEqual(consolidate_drawing_previews(entries), entries)

    def test_rotated_and_cropped_source_renders_union_in_its_actual_orientation(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                with fitz.open(self.pdf) as pdf:
                    pdf[0].set_cropbox(fitz.Rect(10, 10, 390, 490))
                    pdf[0].set_rotation(rotation)
                    pdf.save(self.folder / "Rotated.pdf")
                source = self.folder / "Rotated.pdf"
                entries = [self.entry([20, 40, 220, 150], 0), self.entry([20, 100, 220, 210], 1)]
                entries = [{**e, "path": str(source), "source_digest": digest_file(source)} for e in entries]
                result = consolidate_drawing_previews(entries)
                with fitz.open(source) as pdf:
                    expected = snapshot(pdf[0], fitz.Rect(20, 40, 220, 210))
                self.assertEqual(result[1]["image"], expected)
                with Image.open(BytesIO(base64.b64decode(expected))) as image:
                    self.assertEqual(image.size, (340, 400) if rotation % 180 else (400, 340))
                source.unlink()

    def test_export_uses_saved_digest_without_reextracting_or_modifying_entries(self):
        store = Store(self.folder / "library.sqlite3")
        project = store.add_project(self.folder)
        entries = [self.entry([20, 40, 220, 150], 0), self.entry([20, 100, 220, 210], 1)]
        entries = [{key: value for key, value in e.items() if key not in {"source_digest", "path"}} for e in entries]
        store.save_scan(project, self.pdf, digest_file(self.pdf), "signature", "settings", {}, entries)
        saved = store.entries()
        self.assertEqual(len(build_notebook("Saved notes", saved).inline_shapes), 1)
        self.assertEqual(store.entries(), saved)
        self.assertEqual(len(store.entries(query="Separate observation")), 2)


if __name__ == "__main__":
    unittest.main()
