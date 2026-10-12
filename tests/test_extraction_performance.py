"""Synthetic dense annotations preserve content while avoiding repeated parsing."""
from io import BytesIO
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import fitz
from PIL import Image

from note_organizer.extraction import extract, group_graphics, grouping_rect, highlighted_words
from note_organizer.storage import DEFAULT_SETTINGS


def reference_words(page, annotation):
    """Original quad order and overlap rule, independent of the word cache."""
    vertices = annotation.vertices or []
    rects = [fitz.Quad(vertices[i:i+4]).rect for i in range(0, len(vertices)-3, 4)] or [annotation.rect]
    words = page.get_text("words")
    selected, seen = [], set()
    for rect in rects:
        for word in sorted(words, key=lambda word: (word[5], word[6], word[7])):
            box = fitz.Rect(word[:4])
            if box.get_area() and (box & rect).get_area() / box.get_area() >= .35:
                key = tuple(word[:8])
                if key not in seen:
                    selected.append(word)
                    seen.add(key)
    return selected


def reference_groups(annotations, mode, gap):
    """Original all-pairs grouping, used to check the sweep on tricky layouts."""
    if mode == "Whole page":
        return [annotations] if annotations else []
    rectangles = [grouping_rect(annotation) for annotation in annotations]
    parents = list(range(len(rectangles)))

    def root(index):
        while parents[index] != index:
            index = parents[index]
        return index

    vertical_gap = gap if mode == "Nearby blocks" else min(5, gap / 3)
    for index, rect in enumerate(rectangles):
        for previous in range(index):
            other = rectangles[previous]
            dx = max(0, rect.x0 - other.x1, other.x0 - rect.x1)
            dy = max(0, rect.y0 - other.y1, other.y0 - rect.y1)
            if dx <= gap and dy <= vertical_gap:
                parents[root(index)] = root(previous)
    groups = {}
    for index, annotation in enumerate(annotations):
        groups.setdefault(root(index), []).append(annotation)
    return sorted(groups.values(), key=lambda group: (min(a.rect.y0 for a in group), min(a.rect.x0 for a in group)))


class ExtractionPerformanceTests(unittest.TestCase):
    def test_numeric_word_overlap_keeps_threshold_and_empty_bounds(self):
        page = SimpleNamespace(get_text=lambda option: [(0, 0, 100, 100, "word", 0, 0, 0),
                                                       (20, 20, 20, 100, "empty", 0, 0, 1)])
        for bounds in ((0, 0, 35, 100), (0, 0, 34, 100), (-5, -5, 105, 105),
                       (100, 0, 120, 100), (20, 20, 10, 10), (10, 10, 10, 10)):
            with self.subTest(bounds=bounds):
                annotation = SimpleNamespace(rect=fitz.Rect(bounds), vertices=None)
                self.assertEqual(highlighted_words(page, annotation), reference_words(page, annotation))

    def test_dense_highlights_share_words_and_identical_context(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / "dense.pdf"
            embedded = BytesIO()
            Image.new("RGB", (500, 500), "white").save(embedded, format="PNG")
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((40, 50), "A highlighted research passage")
                page.insert_image(fitz.Rect(40, 200, 300, 460), stream=embedded.getvalue())
                for _ in range(60):
                    page.add_highlight_annot(page.search_for("highlighted research passage"))
                document.save(pdf)
            original = fitz.Page.get_text
            calls, image_blocks = [], []

            def tracked(page, option="text", *args, **kwargs):
                calls.append((option, kwargs.get("clip")))
                result = original(page, option, *args, **kwargs)
                if option == "dict":
                    image_blocks.extend(block for block in result["blocks"] if block.get("type") == 1)
                return result

            with patch.object(fitz.Page, "get_text", new=tracked):
                _, _, _, entries = extract(pdf, DEFAULT_SETTINGS)
            self.assertEqual(len(entries), 60)
            self.assertEqual({entry["quote"] for entry in entries}, {"highlighted research passage"})
            self.assertEqual(sum(option == "words" for option, _ in calls), 1)
            self.assertEqual(sum(option == "dict" for option, _ in calls), 1)
            self.assertEqual(sum(option == "text" and crop is not None for option, crop in calls), 1)
            self.assertEqual(image_blocks, [])
            self.assertTrue(all(entry["image"] == "" for entry in entries))

    def test_cached_words_and_context_preserve_rotation_columns_and_crop(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), tempfile.TemporaryDirectory() as folder:
                pdf = Path(folder) / "columns.pdf"
                with fitz.open() as document:
                    page = document.new_page(width=700, height=900)
                    page.set_cropbox(fitz.Rect(20, 20, 680, 880))
                    for column in (50, 350):
                        for line in range(4):
                            page.insert_text((column, 80 + line*24), f"Column needle text line {line}")
                    rectangles = page.search_for("needle")
                    # Multiple quads and duplicate coverage must retain one copy
                    # of each selected word in the original quad order.
                    page.add_highlight_annot([rectangles[0], rectangles[1], rectangles[0]])
                    page.add_underline_annot(rectangles[3:])
                    page.add_text_annot((230, 90), "A typed note")
                    page.add_ink_annot([[(70, 200), (80, 185), (90, 200)]])
                    page.set_rotation(rotation)
                    document.save(pdf)
                _, _, _, entries = extract(pdf, DEFAULT_SETTINGS)
                with fitz.open(pdf) as document:
                    page = document[0]
                    words = sorted(page.get_text("words"), key=lambda word: (word[5], word[6], word[7]))
                    for annotation in page.annots():
                        if annotation.type[1].lower() in {"highlight", "underline"}:
                            expected = reference_words(page, annotation)
                            self.assertEqual(highlighted_words(page, annotation, words), expected)
                            entry = next(e for e in entries if e["key"].endswith(annotation.info["id"]))
                            self.assertEqual(entry["quote"], " ".join(word[4] for word in expected))
                    for entry in entries:
                        self.assertEqual(entry["context"], page.get_text("text", clip=fitz.Rect(entry["crop"]), sort=True).strip())

    def test_group_sweep_preserves_all_pairs_clusters(self):
        generator = random.Random(137)
        for case in range(8):
            annotations = []
            for _ in range(120):
                x, y = generator.uniform(-20, 700), generator.uniform(-20, 900)
                rect = fitz.Rect(x, y, x + generator.uniform(1, 80), y + generator.uniform(1, 25))
                annotations.append(SimpleNamespace(rect=rect, type=(4, "square"), vertices=None))
            # Long arrows, repeated bounds, and exact gap boundaries exercise
            # the cases an expanding cluster box would incorrectly merge.
            for rect in (fitz.Rect(10, 10, 650, 15), fitz.Rect(10, 10, 650, 15),
                         fitz.Rect(5, 450, 15, 455), fitz.Rect(39, 450, 49, 455)):
                annotations.append(SimpleNamespace(rect=rect, type=(3, "line"), vertices=None))
            for mode in ("Nearby blocks", "Nearby lines", "Whole page"):
                for gap in (0, 4, 24, 100):
                    with self.subTest(case=case, mode=mode, gap=gap):
                        expected = reference_groups(annotations, mode, gap)
                        actual = group_graphics(annotations, mode, gap)
                        self.assertEqual([[id(a) for a in group] for group in actual],
                                         [[id(a) for a in group] for group in expected])


if __name__ == "__main__":
    unittest.main()
