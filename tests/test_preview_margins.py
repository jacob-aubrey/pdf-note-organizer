"""Read-only recovery of complete ink that crosses legacy PDF page edges."""
import base64
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import fitz
from PIL import Image

from note_organizer.extraction import extract
from note_organizer.pdf_worker import _full_page, MAX_PREVIEW_PIXELS, MAX_PREVIEW_SIDE
from note_organizer.storage import DEFAULT_SETTINGS, digest_file


class PreviewMarginTests(unittest.TestCase):
    def test_closeups_and_full_page_keep_edge_strokes_for_all_rotations_and_cropboxes(self):
        for rotation in (0, 90, 180, 270):
            for cropped in (False, True):
                with self.subTest(rotation=rotation, cropped=cropped), tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "Margin handwriting.pdf"
                    with fitz.open() as document:
                        page = document.new_page(width=200, height=240)
                        if cropped:
                            page.set_cropbox(fitz.Rect(10, 10, 190, 230))
                        width, height = page.rect.width, page.rect.height
                        page.insert_text((50, 45), "Printed reference", fontsize=9)
                        ink = page.add_ink_annot([[(-35, 80), (25, 100)]])
                        ink.set_colors(stroke=(1, 0, 0))
                        ink.set_border(width=2)
                        ink.update()
                        ink = page.add_ink_annot([[(width - 25, 120), (width + 40, 135)]])
                        ink.set_colors(stroke=(0, 0, 1))
                        ink.set_border(width=2)
                        ink.update()
                        ink = page.add_ink_annot([[(80, height - 15), (95, height + 35)]])
                        ink.set_colors(stroke=(0, 1, 0))
                        ink.set_border(width=2)
                        ink.update()
                        page.set_rotation(rotation)
                        document.save(path)
                    before = digest_file(path)
                    _, _, _, entries = extract(path, DEFAULT_SETTINGS)
                    self.assertEqual(len(entries), 3)
                    for entry in entries:
                        self.assertTrue(fitz.Rect(entry["crop"]).contains(fitz.Rect(entry["rect"])))
                        with Image.open(BytesIO(base64.b64decode(entry["image"]))) as image:
                            pixels = list(image.convert("RGB").getdata())
                            # More than half of each colored stroke lies outside
                            # the old page edge. It must still appear in full.
                            color = entry["color"]
                            channel = {"Red": 0, "Blue": 2, "Green": 1}[color]
                            colored = sum(p[channel] > 180 and all(p[c] < 70 for c in range(3) if c != channel)
                                          for p in pixels)
                            self.assertGreater(colored, 300)
                    with Image.open(BytesIO(_full_page(path, 1))) as image:
                        self.assertGreater(image.width, 2 * (height if rotation % 180 else width))
                        self.assertGreater(image.height, 2 * (width if rotation % 180 else height))
                        self.assertLessEqual(image.width * image.height, MAX_PREVIEW_PIXELS)
                        self.assertLessEqual(max(image.size), MAX_PREVIEW_SIDE)
                    self.assertEqual(digest_file(path), before)

    def test_incidental_drawing_at_crop_edge_is_shown_complete_without_merging_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Nearby handwriting.pdf"
            with fitz.open() as document:
                page = document.new_page(width=400, height=400)
                for points in ([[(50, 80), (70, 90)]], [[(105, 100), (200, 110)]]):
                    ink = page.add_ink_annot(points)
                    ink.update()
                document.save(path)
            _, _, _, entries = extract(path, DEFAULT_SETTINGS)
            self.assertEqual(len(entries), 2)
            first = min(entries, key=lambda e: e["rect"][0])
            second = max(entries, key=lambda e: e["rect"][0])
            self.assertTrue(fitz.Rect(first["crop"]).contains(fitz.Rect(second["rect"])))
            self.assertNotEqual(first["key"], second["key"])

    def test_absurd_invisible_mark_does_not_expand_canvas(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Outlier.pdf"
            with fitz.open() as document:
                page = document.new_page(width=200, height=240)
                page.add_ink_annot([[(50, 60), (80, 90)]])
                page.add_ink_annot([[(10000, 10000), (11000, 11000)]])
                document.save(path)
            _, _, metadata, entries = extract(path, DEFAULT_SETTINGS)
            self.assertEqual(len(entries), 1)
            self.assertIn("outside the visible page", " ".join(metadata["warnings"]))
            with Image.open(BytesIO(_full_page(path, 1))) as image:
                self.assertEqual(image.size, (400, 480))


if __name__ == "__main__":
    unittest.main()
