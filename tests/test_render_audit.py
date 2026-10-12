"""Synthetic checks for incomplete scenes and invisible tablet annotations."""
from dataclasses import replace
from io import BytesIO
import unittest

import fitz
from rmscene import read_blocks, write_blocks
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_items import GlyphRange, Pen, PenColor, Point, Rectangle
from rmscene.scene_stream import (RootTextBlock, SceneGlyphItemBlock, SceneInfo,
                                 SceneLineItemBlock, SceneTextItemBlock,
                                 SceneTombstoneItemBlock)
from rmscene.tagged_block_common import CrdtId

from note_organizer.remarkable_pdf import annotated_pdf, color, COLORS, page_map, UnsupportedAnnotations
from tests.test_remarkable import fixture


def changed_scene(change):
    """Modify only a synthetic tablet layer, keeping a representative PDF."""
    item, bundle = fixture(paper_size=(1620, 2160))
    name = next(name for name in bundle if name.endswith(".rm"))
    blocks = list(read_blocks(BytesIO(bundle[name])))
    change(blocks)
    output = BytesIO()
    write_blocks(output, blocks, options={"version": "3.1"})
    bundle[name] = output.getvalue()
    return item, bundle


class RendererAuditTests(unittest.TestCase):
    def test_indexed_highlight_black_rgba_placeholder_uses_its_palette(self):
        for palette_color in (PenColor.YELLOW, PenColor.PINK):
            with self.subTest(palette_color=palette_color):
                mark = GlyphRange(None, 0, "", palette_color, [], color_rgba=(0, 0, 0, 255))
                self.assertEqual(color(mark), COLORS[int(palette_color)])
        custom = GlyphRange(None, 0, "", PenColor.HIGHLIGHT, [], color_rgba=(255, 195, 140, 255))
        self.assertEqual(color(custom), (1, 195 / 255, 140 / 255))
        custom.color_rgba = (0, 0, 0, 255)
        self.assertEqual(color(custom), (0, 0, 0))

    def test_highlight_rasters_keep_underlying_print_visible(self):
        for kind in ("indexed yellow", "custom black", "freehand yellow"):
            with self.subTest(kind=kind):
                item, bundle = fixture()
                name = next(name for name in bundle if name.endswith(".rm"))
                blocks = list(read_blocks(BytesIO(bundle[name])))
                # Remove the unrelated typed note and pen mark from this visual check.
                blocks[:] = [b for b in blocks if not isinstance(b, RootTextBlock)]
                if kind == "freehand yellow":
                    blocks[:] = [b for b in blocks if not isinstance(b, SceneGlyphItemBlock)]
                    line = next(b for b in blocks if isinstance(b, SceneLineItemBlock)).item.value
                    line.tool, line.color, line.color_rgba = Pen.HIGHLIGHTER_2, PenColor.YELLOW, None
                    for point, x in zip(line.points, (-750, -200)):
                        point.x, point.y, point.width = x, 299, 40
                else:
                    blocks[:] = [b for b in blocks if not isinstance(b, SceneLineItemBlock)]
                    glyph = next(b for b in blocks if isinstance(b, SceneGlyphItemBlock)).item.value
                    glyph.color = PenColor.YELLOW if kind == "indexed yellow" else PenColor.HIGHLIGHT
                    glyph.color_rgba = (0, 0, 0, 255)
                    glyph.rectangles = [Rectangle(-755, 260, 630, 80)]
                stream = BytesIO()
                write_blocks(stream, blocks, options={"version": "3.1"})
                bundle[name] = stream.getvalue()
                region = fitz.Rect(70, 90, 200, 100)
                with fitz.open(stream=bundle[item.id + ".pdf"], filetype="pdf") as source, \
                        fitz.open(stream=annotated_pdf(item, bundle), filetype="pdf") as imported:
                    page = imported[0]
                    plain = source[0].get_pixmap(clip=region)
                    highlighted = page.get_pixmap(clip=region)
                    dark = white = 0
                    for index in range(0, len(plain.samples), 3):
                        before = plain.samples[index:index + 3]
                        after = highlighted.samples[index:index + 3]
                        if max(before) <= 24:
                            dark += 1
                            self.assertLessEqual(max(after), 30)
                        elif min(before) >= 250:
                            white += 1
                            self.assertGreaterEqual(min(after), 140)
                            self.assertLess(min(after), 240)
                            if kind != "custom black":
                                self.assertGreater(after[0], after[2])
                    self.assertGreater(dark, 20)
                    self.assertGreater(white, 20)
                    self.assertAlmostEqual(next(page.annots()).opacity, .35, places=5)

    def test_supported_paper_pro_scene_retains_all_three_annotation_types(self):
        item, bundle = fixture(paper_size=(1620, 2160))
        with fitz.open(stream=annotated_pdf(item, bundle), filetype="pdf") as document:
            page = document[0]
            annotations = list(page.annots())
            self.assertEqual({a.type[1] for a in annotations}, {"Highlight", "Ink", "Text"})
            highlight = next(a for a in annotations if a.type[1] == "Highlight")
            self.assertEqual(document.xref_get_key(highlight.xref, "RMQuote"), ("string", "selected scientific"))

    def test_selected_quote_is_private_metadata_and_typed_notes_remain_comments(self):
        item, bundle = fixture()
        name = next(name for name in bundle if name.endswith(".rm"))
        blocks = list(read_blocks(BytesIO(bundle[name])))
        glyph = next(b for b in blocks if isinstance(b, SceneGlyphItemBlock))
        glyph.item.value.text = 'A Unicode quote: α, β and "quoted" text'
        stream = BytesIO()
        write_blocks(stream, blocks, options={"version": "3.1"})
        bundle[name] = stream.getvalue()
        with fitz.open(stream=annotated_pdf(item, bundle), filetype="pdf") as document:
            page = document[0]
            annotations = list(page.annots())
            highlight = next(a for a in annotations if a.type[1] == "Highlight")
            self.assertEqual(highlight.info["content"], "")
            self.assertEqual(document.xref_get_key(highlight.xref, "Contents"), ("null", "null"))
            self.assertEqual(document.xref_get_key(highlight.xref, "Popup"), ("null", "null"))
            self.assertEqual(highlight.popup_xref, 0)
            self.assertEqual(document.xref_get_key(highlight.xref, "RMQuote"),
                             ("string", glyph.item.value.text))
            typed_note = next(a for a in annotations if a.type[1] == "Text")
            self.assertEqual(typed_note.info["content"], "Typed margin note")
            self.assertGreater(typed_note.popup_xref, 0)

    def test_unknown_top_level_and_item_fields_require_review(self):
        for field in ("extra_data", "extra_value_data"):
            with self.subTest(field=field):
                def change(blocks):
                    glyph = next(b for b in blocks if isinstance(b, SceneGlyphItemBlock))
                    setattr(glyph, field, b"unsupported newer field")
                item, bundle = changed_scene(change)
                with self.assertRaisesRegex(UnsupportedAnnotations, "newer annotation fields"):
                    annotated_pdf(item, bundle)

    def test_scene_metadata_extensions_do_not_drop_supported_annotations(self):
        def change(blocks):
            metadata = next(b for b in blocks if isinstance(b, SceneInfo))
            metadata.extra_data = b"newer scene metadata"
        item, bundle = changed_scene(change)
        with fitz.open(stream=annotated_pdf(item, bundle), filetype="pdf") as document:
            page = document[0]
            self.assertEqual(len(list(page.annots())), 3)

    def test_recognized_items_skipped_by_rmscene_require_review(self):
        for block_type in (SceneTextItemBlock, SceneTombstoneItemBlock):
            with self.subTest(block_type=block_type.__name__):
                def change(blocks):
                    blocks.append(block_type(CrdtId(0, 11), CrdtSequenceItem(
                        CrdtId(1, 120), CrdtId(1, 101), CrdtId(0, 0), 0, None)))
                item, bundle = changed_scene(change)
                with self.assertRaisesRegex(UnsupportedAnnotations, "annotation items"):
                    annotated_pdf(item, bundle)

    def test_absurd_off_page_highlight_ink_and_text_require_review(self):
        for block_type in (SceneGlyphItemBlock, SceneLineItemBlock, RootTextBlock):
            with self.subTest(block_type=block_type.__name__):
                def change(blocks):
                    block = next(b for b in blocks if isinstance(b, block_type))
                    if isinstance(block, SceneGlyphItemBlock):
                        for rect in block.item.value.rectangles:
                            rect.x = rect.y = 100000
                    elif isinstance(block, SceneLineItemBlock):
                        for point in block.item.value.points:
                            point.x = point.y = 100000
                    else:
                        block.value.pos_x = block.value.pos_y = 100000
                item, bundle = changed_scene(change)
                with self.assertRaisesRegex(UnsupportedAnnotations, "outside the supported PDF margin area"):
                    annotated_pdf(item, bundle)

    def test_partially_visible_margin_strokes_and_highlights_are_preserved(self):
        def change(blocks):
            # On the synthetic 600-point PDF, scene x=-955 is near the left edge.
            glyph = next(b for b in blocks if isinstance(b, SceneGlyphItemBlock))
            glyph.item.value.rectangles[0].x = -1000
            line = next(b for b in blocks if isinstance(b, SceneLineItemBlock))
            line.item.value.points[0].x = -1000
        item, bundle = changed_scene(change)
        with fitz.open(stream=annotated_pdf(item, bundle), filetype="pdf") as document:
            page = document[0]
            annotations = list(page.annots())
            self.assertEqual(len(annotations), 3)
            self.assertTrue(all(a.rect.intersects(page.rect) for a in annotations))
            self.assertGreater(page.rect.width, 600)

    def test_canvas_preserves_original_content_and_left_right_bottom_margin_ink(self):
        item, bundle = fixture()
        pdf_name = item.id + ".pdf"
        with fitz.open(stream=bundle[pdf_name], filetype="pdf") as source:
            page = source[0]
            note = page.add_text_annot((400, 120), "Existing source PDF note")
            note.update()
            bundle[pdf_name] = source.tobytes()
        original_pdf = bundle[pdf_name]
        name = next(name for name in bundle if name.endswith(".rm"))
        blocks = list(read_blocks(BytesIO(bundle[name])))
        template = next(b for b in blocks if isinstance(b, SceneLineItemBlock))
        for number, points in enumerate((
                [Point(-1050, 420, 0, 0, 16, 90), Point(-1000, 460, 0, 0, 16, 90)],
                [Point(1000, 420, 0, 0, 16, 90), Point(1050, 460, 0, 0, 16, 90)],
                [Point(-100, 2600, 0, 0, 16, 90), Point(100, 2650, 0, 0, 16, 90)])):
            line = replace(template.item.value, points=points)
            node = CrdtSequenceItem(CrdtId(1, 200 + number), CrdtId(1, 101), CrdtId(0, 0), 0, line)
            blocks.append(SceneLineItemBlock(template.parent_id, node))
        stream = BytesIO()
        write_blocks(stream, blocks, options={"version": "3.1"})
        bundle[name] = stream.getvalue()
        converted = annotated_pdf(item, bundle)
        self.assertEqual(bundle[pdf_name], original_pdf)
        with fitz.open(stream=original_pdf, filetype="pdf") as source, \
                fitz.open(stream=converted, filetype="pdf") as output:
            page, original_page = output[0], source[0]
            original_word = original_page.get_text("words")[0]
            imported_word = page.get_text("words")[0]
            left = imported_word[0] - original_word[0]
            top = imported_word[1] - original_word[1]
            self.assertGreater(left, 0)
            self.assertEqual(top, 0)
            self.assertGreater(page.rect.width, original_page.rect.width)
            self.assertGreater(page.rect.height, original_page.rect.height)
            for before_word, after_word in zip(original_page.get_text("words"), page.get_text("words")):
                for before, after, shift in zip(before_word[:4], after_word[:4], (left, top, left, top)):
                    self.assertAlmostEqual(after, before + shift, places=3)
            annotations = list(page.annots())
            self.assertEqual(sum(a.type[1] == "Ink" for a in annotations), 4)
            self.assertTrue(all(page.rect.contains(a.rect) for a in annotations))
            # Original printed pixels remain exactly where the gutter offset puts them.
            source_region = fitz.Rect(20, 20, 50, 60)
            shifted = source_region + (left, top, left, top)
            self.assertEqual(original_page.get_pixmap(clip=source_region).samples,
                             page.get_pixmap(clip=shifted).samples)
            printed = fitz.Rect(60, 87, 215, 104)
            shifted_printed = printed + (left, top, left, top)
            before = original_page.get_pixmap(clip=printed, annots=False).samples
            after = page.get_pixmap(clip=shifted_printed, annots=False).samples
            # Font antialiasing can vary slightly after changing the media box.
            self.assertLessEqual(max(abs(a - b) for a, b in zip(before, after)), 3)
            self.assertTrue(any(a.info.get("content") == "Existing source PDF note" for a in annotations))

    def test_rotated_or_cropped_pages_with_margin_ink_require_review(self):
        for geometry in ("rotated", "cropped"):
            with self.subTest(geometry=geometry):
                item, bundle = fixture()
                with fitz.open(stream=bundle[item.id + ".pdf"], filetype="pdf") as source:
                    if geometry == "rotated":
                        source[0].set_rotation(90)
                    else:
                        source[0].set_cropbox(fitz.Rect(20, 20, 580, 780))
                    bundle[item.id + ".pdf"] = source.tobytes()
                name = next(name for name in bundle if name.endswith(".rm"))
                blocks = list(read_blocks(BytesIO(bundle[name])))
                line = next(b for b in blocks if isinstance(b, SceneLineItemBlock)).item.value
                for point in line.points:
                    point.y = -100
                stream = BytesIO()
                write_blocks(stream, blocks, options={"version": "3.1"})
                bundle[name] = stream.getvalue()
                with self.assertRaisesRegex(UnsupportedAnnotations, "rotated or cropped"):
                    annotated_pdf(item, bundle)

    def test_incomplete_or_duplicate_cpages_ordering_requires_review(self):
        for second in ({"id": "b"}, {"id": "b", "idx": {"value": "ba"}},
                       {"id": "b", "idx": {"value": None}}):
            with self.subTest(second=second):
                content = {"cPages": {"pages": [{"id": "a", "idx": {"value": "ba"}}, second]}}
                with self.assertRaisesRegex(UnsupportedAnnotations, "page ordering"):
                    page_map(content, 2)

    def test_boolean_redirect_is_not_a_pdf_page_number(self):
        for redirected in (True, False):
            with self.subTest(redirected=redirected):
                with self.assertRaisesRegex(UnsupportedAnnotations, "page reference"):
                    page_map({"pages": ["a"], "redirectionPageMap": [redirected]}, 2)

    def test_unordered_legacy_cpages_records_remain_supported(self):
        self.assertEqual(page_map({"cPages": {"pages": [
            {"id": "a", "redir": {"value": 0}}, {"id": "b"}]}}, 1), [("a", 0), ("b", -1)])


if __name__ == "__main__":
    unittest.main()
