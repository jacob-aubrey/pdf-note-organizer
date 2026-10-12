"""Native PDF margins retain page geometry, pixels, annotations and navigation."""
import threading
import unittest

import fitz
from PIL import Image, ImageChops

from note_organizer.pdf_margins import expand_annotation_margins


def image(page, annots=False):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False, annots=annots)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def pdf_crop(page):
    media, crop = page.mediabox, page.cropbox
    return fitz.Rect(crop.x0, media.y1 - crop.y1, crop.x1, media.y1 - crop.y0)


def effective_rotation(page, crop):
    # MuPDF's convenience rotation_matrix may use the declared crop's size,
    # while rasterization uses the actual MediaBox/CropBox intersection.
    return {0: fitz.Matrix(1, 0, 0, 1, 0, 0),
            90: fitz.Matrix(0, 1, -1, 0, crop.height, 0),
            180: fitz.Matrix(-1, 0, 0, -1, crop.width, crop.height),
            270: fitz.Matrix(0, -1, 1, 0, 0, crop.width)}[page.rotation]


def make_document(rotation=0, cropped=False, origin=False):
    document = fitz.open()
    page = document.new_page(width=400, height=600)
    if origin:
        document.xref_set_key(page.xref, "MediaBox", "[20 30 420 630]")
        page = document.reload_page(page)
    page.insert_text((90, 180), "Searchable article text", fontsize=12)
    page.draw_rect(fitz.Rect(110, 210, 200, 280), color=(0, 0, 1), fill=(0, .8, 1))
    if cropped:
        # Printed content beyond the original crop must stay hidden after growth.
        page.draw_rect(fitz.Rect(0, 0, 400, 30), color=(1, 0, 0), fill=(1, 0, 0))
        page.draw_rect(fitz.Rect(0, 570, 400, 600), color=(1, 0, 0), fill=(1, 0, 0))
        page.draw_rect(fitz.Rect(0, 0, 25, 600), color=(1, 0, 0), fill=(1, 0, 0))
        page.draw_rect(fitz.Rect(375, 0, 400, 600), color=(1, 0, 0), fill=(1, 0, 0))
        media = page.mediabox
        document.xref_set_key(page.xref, "CropBox", f"[{media.x0 + 30} {media.y0 + 50} {media.x1 - 30} {media.y1 - 50}]")
        page = document.reload_page(page)
    page.set_rotation(rotation)
    return document


def add_edge_notes(document, page):
    bounds = page.rect * page.derotation_matrix
    w, h = bounds.width, bounds.height
    for edge, points in (
        ("left", [(-40, 100), (-10, 120)]),
        ("right", [(w + 10, 140), (w + 45, 180)]),
        ("top", [(50, -40), (70, -10)]),
        ("bottom", [(100, h + 10), (150, h + 45)]),
    ):
        annot = page.add_ink_annot([points])
        annot.set_colors(stroke=(0, 0, 0))
        annot.set_border(width=3)
        annot.set_info(content=edge)
        annot.update()
    highlight = page.add_highlight_annot(fitz.Rect(w + 10, 70, w + 60, 84))
    highlight.set_info(content="outside highlight")
    highlight.update()
    text = page.add_text_annot((-30, h + 15), "Outside comment")
    text.update()


class PdfMarginsTests(unittest.TestCase):
    def test_all_edges_and_rotations_preserve_printed_pixels_and_annotation_objects(self):
        for rotation in (0, 90, 180, 270):
            for cropped, origin in ((False, False), (True, False), (False, True), (True, True)):
                with self.subTest(rotation=rotation, cropped=cropped, origin=origin):
                    with make_document(rotation, cropped, origin) as document:
                        page = document[0]
                        add_edge_notes(document, page)
                        # Include visible marks and an arrow crossing the page
                        # edge, proving that the expansion keeps their pixels
                        # aligned with the searchable article underneath.
                        bounds = page.rect * page.derotation_matrix
                        page.add_ink_annot([[(80, 210), (160, 270)]])
                        page.add_ink_annot([[(bounds.width - 20, 220), (bounds.width + 20, 220)]])
                        page.add_highlight_annot(fitz.Rect(60, 120, 180, 140))
                        before_images = {annots: image(page, annots) for annots in (False, True)}
                        before_rotation = page.rotation_matrix
                        old_crop = pdf_crop(page)
                        objects = {a.xref: document.xref_object(a.xref) for a in page.annots()}
                        streams = {xref: document.xref_stream(xref) for xref in page.get_contents()}
                        self.assertTrue(expand_annotation_margins(document))
                        page = document[0]
                        new_crop = pdf_crop(page)
                        shifted = fitz.Point(old_crop.x0 - new_crop.x0, new_crop.y1 - old_crop.y1)
                        delta = shifted * page.rotation_matrix - fitz.Point(0, 0) * before_rotation
                        x, y = round(delta.x * 2), round(delta.y * 2)
                        for annots, before_image in before_images.items():
                            after_image = image(page, annots)
                            retained_image = after_image.crop(
                                (x, y, x + before_image.width, y + before_image.height))
                            if annots:
                                # MuPDF changes a few stroke edge antialiasing
                                # values when a rotated canvas grows. The
                                # native AP/InkList below must stay byte exact;
                                # tolerate only sparse, faint raster changes.
                                diff = ImageChops.difference(before_image, retained_image)
                                self.assertLessEqual(max(high for low, high in diff.getextrema()), 16)
                                changed = sum(a != b for a, b in zip(before_image.getdata(), retained_image.getdata()))
                                self.assertLessEqual(changed, before_image.width * before_image.height * .001)
                            else:
                                self.assertTrue(before_image.tobytes() == retained_image.tobytes())
                        self.assertEqual(page.rotation, rotation)
                        self.assertIn("Searchable article text", page.get_text())
                        self.assertEqual(len(list(page.annots())), len(objects))
                        for xref, value in objects.items():
                            self.assertEqual(document.xref_object(xref), value)
                        for xref, value in streams.items():
                            self.assertEqual(document.xref_stream(xref), value)
                        # Every note, including detached letters and upright
                        # comment icons, is now inside the visible page.
                        visible = page.rect * page.derotation_matrix
                        for annot in page.annots():
                            self.assertTrue(visible.contains(annot.rect), (visible, annot.rect, annot.type))

    def test_new_whitespace_does_not_reveal_cropped_printed_content(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), make_document(rotation, cropped=True, origin=True) as document:
                page = document[0]
                add_edge_notes(document, page)
                self.assertTrue(expand_annotation_margins(document))
                pixels = image(document[0])
                self.assertNotIn((255, 0, 0), pixels.getdata())
                self.assertEqual(pixels.getpixel((0, 0)), (255, 255, 255))

    def test_crop_beyond_media_uses_actual_visible_intersection_for_growth_and_clipping(self):
        for rotation in (0, 90, 180, 270):
            for crop_value in ("[0 0 500 700]", "[-50 -20 350 500]", "[50 100 500 700]"):
                with self.subTest(rotation=rotation, crop=crop_value), make_document(rotation) as document:
                    page = document[0]
                    document.xref_set_key(page.xref, "CropBox", crop_value)
                    old_crop = pdf_crop(page) & page.mediabox
                    # This red article content is outside the effective page,
                    # but the new margin would reveal it without clipping.
                    page.set_rotation(0)
                    page.draw_rect(fitz.Rect(old_crop.width + 10, 90, old_crop.width + 35, 150),
                                   color=(1, 0, 0), fill=(1, 0, 0))
                    page.set_rotation(rotation)
                    annot = page.add_ink_annot([[(old_crop.width + 10, 100), (old_crop.width + 30, 120)]])
                    before_annot = document.xref_object(annot.xref)
                    before_image, before_rotation = image(page), effective_rotation(page, old_crop)
                    self.assertNotIn((255, 0, 0), before_image.getdata())
                    original_data = document.tobytes()
                    self.assertTrue(expand_annotation_margins(document))
                    page = document[0]
                    self.assertTrue((page.rect * page.derotation_matrix).contains(page.load_annot(annot.xref).rect))
                    self.assertEqual(document.xref_object(annot.xref), before_annot)
                    new_crop = pdf_crop(page)
                    delta = fitz.Point(old_crop.x0 - new_crop.x0, new_crop.y1 - old_crop.y1) * page.rotation_matrix
                    delta -= fitz.Point(0, 0) * before_rotation
                    x, y = round(delta.x * 2), round(delta.y * 2)
                    after_image = image(page)
                    retained = after_image.crop((x, y, x + before_image.width, y + before_image.height))
                    self.assertTrue(before_image.tobytes() == retained.tobytes())
                    self.assertNotIn((255, 0, 0), after_image.getdata())
                    # Real callers open files fresh; confirm this result does
                    # not depend on a live page object's geometry cache.
                    with fitz.open(stream=original_data, filetype="pdf") as reopened:
                        self.assertTrue(expand_annotation_margins(reopened))
                        self.assertTrue(image(reopened[0]).tobytes() == after_image.tobytes())

    def test_crop_beyond_media_contained_native_notes_remain_exact_no_op(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), make_document() as document:
                page = document[0]
                document.xref_set_key(page.xref, "CropBox", "[0 0 500 700]")
                page.add_ink_annot([[(40, 100), (70, 120)]])
                page.set_rotation(rotation)
                data = document.tobytes()
                with fitz.open(stream=data, filetype="pdf") as reopened:
                    before = {x: (reopened.xref_object(x), reopened.xref_stream(x))
                              for x in range(1, reopened.xref_length())}
                    self.assertFalse(expand_annotation_margins(reopened))
                    for xref, value in before.items():
                        self.assertEqual((reopened.xref_object(xref), reopened.xref_stream(xref)), value)

    def test_no_op_keeps_existing_page_and_content_objects_exactly(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), make_document(rotation, True, True) as document:
                page = document[0]
                page.add_text_annot((80, 80), "Visible")
                before = {xref: (document.xref_object(xref), document.xref_stream(xref))
                          for xref in range(1, document.xref_length())}
                self.assertFalse(expand_annotation_margins(document))
                self.assertEqual(document.xref_length(), len(before) + 1)
                for xref, value in before.items():
                    self.assertEqual((document.xref_object(xref), document.xref_stream(xref)), value)

    def test_already_revealed_margins_are_idempotent(self):
        with make_document(270, True, True) as document:
            add_edge_notes(document, document[0])
            self.assertTrue(expand_annotation_margins(document))
            boxes = (document[0].mediabox, document[0].cropbox)
            before = document.xref_length()
            self.assertFalse(expand_annotation_margins(document))
            self.assertEqual(document.xref_length(), before)
            self.assertEqual((document[0].mediabox, document[0].cropbox), boxes)

    def test_hidden_invisible_and_no_view_notes_do_not_expand_pages(self):
        for flag in (fitz.PDF_ANNOT_IS_HIDDEN, fitz.PDF_ANNOT_IS_INVISIBLE, fitz.PDF_ANNOT_IS_NO_VIEW):
            with self.subTest(flag=flag), make_document() as document:
                page = document[0]
                annot = page.add_ink_annot([[(-100, -100), (-90, -90)]])
                annot.set_flags(flag)
                annot.update()
                self.assertFalse(expand_annotation_margins(document))
                self.assertEqual(page.rect, fitz.Rect(0, 0, 400, 600))

    def test_extreme_detached_annotation_requires_review_without_any_page_changes(self):
        with make_document() as document:
            document[0].add_ink_annot([[(-30, 100), (20, 100)]])
            page = document.new_page(width=400, height=600)
            page.add_ink_annot([[(20_000, 100), (20_100, 120)]])
            before = [document.xref_object(p.xref) for p in document]
            with self.assertRaisesRegex(ValueError, "supported PDF margin"):
                expand_annotation_margins(document)
            self.assertEqual([document.xref_object(p.xref) for p in document], before)

    def test_invalid_annotation_rectangle_requires_review(self):
        with make_document() as document:
            annot = document[0].add_text_annot((20, 20), "bad bounds")
            document.xref_set_key(annot.xref, "Rect", "[0 0 0 0]")
            with self.assertRaisesRegex(ValueError, "invalid coordinates"):
                expand_annotation_margins(document)

    def test_indirect_annotation_rectangle_supports_no_op_and_off_page_notes(self):
        for outside in (False, True):
            with self.subTest(outside=outside), make_document() as document:
                page = document[0]
                points = [(-30, 100), (-10, 120)] if outside else [(40, 100), (70, 120)]
                annot = page.add_ink_annot([points])
                rect_value = document.xref_get_key(annot.xref, "Rect")[1]
                rect_xref = document.get_new_xref()
                document.update_object(rect_xref, rect_value)
                document.xref_set_key(annot.xref, "Rect", f"{rect_xref} 0 R")
                before_annot = document.xref_object(annot.xref)
                before_rect = document.xref_object(rect_xref)
                self.assertEqual(expand_annotation_margins(document), outside)
                self.assertEqual(document.xref_object(annot.xref), before_annot)
                self.assertEqual(document.xref_object(rect_xref), before_rect)
                visible = page.rect * page.derotation_matrix
                self.assertTrue(visible.contains(page.load_annot(annot.xref).rect))

    def test_invalid_indirect_annotation_rectangle_requires_review(self):
        with make_document() as document:
            annot = document[0].add_text_annot((40, 40), "Invalid referenced rectangle")
            rect_xref = document.get_new_xref()
            document.update_object(rect_xref, "<< /Invalid true >>")
            document.xref_set_key(annot.xref, "Rect", f"{rect_xref} 0 R")
            before = document.xref_object(document[0].xref)
            with self.assertRaisesRegex(ValueError, "no usable PDF rectangle"):
                expand_annotation_margins(document)
            self.assertEqual(document.xref_object(document[0].xref), before)

    def test_nonstandard_direct_and_parent_units_require_review_only_for_margin_growth(self):
        for rotation in (0, 90, 180, 270):
            for placement in ("page", "parent"):
                for outside in (False, True):
                    with self.subTest(rotation=rotation, placement=placement, outside=outside):
                        with make_document(rotation, cropped=True, origin=True) as document:
                            page = document[0]
                            page.add_text_annot((80, 80), "Contained comment")
                            if outside:
                                page.add_ink_annot([[(-30, 100), (-10, 120)]])
                            else:
                                page.add_ink_annot([[(40, 100), (70, 120)]])
                            xref = page.xref if placement == "page" else int(
                                document.xref_get_key(page.xref, "Parent")[1].split()[0])
                            document.xref_set_key(xref, "UserUnit", "2")
                            before = {x: (document.xref_object(x), document.xref_stream(x))
                                      for x in range(1, document.xref_length())}
                            if outside:
                                with self.assertRaisesRegex(ValueError, "UserUnit scaling need review"):
                                    expand_annotation_margins(document)
                            else:
                                self.assertFalse(expand_annotation_margins(document))
                            self.assertEqual(document.xref_length(), len(before) + 1)
                            for xref, value in before.items():
                                self.assertEqual((document.xref_object(xref), document.xref_stream(xref)), value)

    def test_explicit_default_units_override_nonstandard_parent_for_margin_growth(self):
        with make_document() as document:
            page = document[0]
            page.add_ink_annot([[(-30, 100), (-10, 120)]])
            parent = int(document.xref_get_key(page.xref, "Parent")[1].split()[0])
            document.xref_set_key(parent, "UserUnit", "2")
            document.xref_set_key(page.xref, "UserUnit", "1")
            self.assertTrue(expand_annotation_margins(document))

    def test_callable_and_event_cancellation(self):
        with make_document() as document:
            with self.assertRaises(InterruptedError):
                expand_annotation_margins(document, lambda: True)
            event = threading.Event()
            event.set()
            with self.assertRaises(InterruptedError):
                expand_annotation_margins(document, event)

    def test_cancellation_is_checked_while_inspecting_annotations(self):
        with make_document() as document:
            add_edge_notes(document, document[0])
            before = document.xref_object(document[0].xref)
            calls = []

            def cancelled():
                calls.append(1)
                return len(calls) > 3

            with self.assertRaises(InterruptedError):
                expand_annotation_margins(document, cancelled)
            self.assertEqual(document.xref_object(document[0].xref), before)

    def test_page_count_order_labels_metadata_outline_and_native_links_survive(self):
        with make_document(90, True, True) as document:
            first = document[0]
            second = document.new_page(width=200, height=300)
            second.insert_text((20, 30), "Second physical page")
            first = document[0]
            add_edge_notes(document, first)
            first.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(40, 40, 80, 60),
                               "page": 1, "to": fitz.Point(20, 30), "zoom": 1.25})
            document[1].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(20, 40, 80, 60),
                                     "page": 0, "to": fitz.Point(90, 130), "zoom": 1.5})
            document.set_metadata({"title": "Retained article", "author": "Example Author"})
            document.set_page_labels([{"startpage": 0, "prefix": "A-", "style": "D", "firstpagenum": 7}])
            document.set_toc([[1, "First", 1], [1, "Second", 2]])
            # Reopen to load link objects, then preserve their native /Dest or /A
            # coordinates instead of the crop-local values returned by get_links.
            data = document.tobytes()
        with fitz.open(stream=data, filetype="pdf") as document:
            links = {link["xref"]: document.xref_object(link["xref"])
                     for page in document for link in page.get_links()}
            before_metadata, labels, toc = document.metadata, document.get_page_labels(), document.get_toc()
            xrefs = [p.xref for p in document]
            self.assertTrue(expand_annotation_margins(document))
            self.assertEqual([p.xref for p in document], xrefs)
            self.assertEqual(document.page_count, 2)
            self.assertEqual(document.metadata, before_metadata)
            self.assertEqual(document.get_page_labels(), labels)
            self.assertEqual(document.get_toc(), toc)
            for xref, value in links.items():
                self.assertEqual(document.xref_object(xref), value)
            self.assertIn("Second physical page", document[1].get_text())
            self.assertEqual([p.get_label() for p in document], ["A-7", "A-8"])
            with fitz.open(stream=document.tobytes(), filetype="pdf") as reopened:
                self.assertEqual(sum(len(p.get_links()) for p in reopened), 2)
                self.assertEqual(reopened.page_count, 2)
                self.assertIn("Searchable article text", reopened[0].get_text())
                self.assertEqual(len(list(reopened[0].annots())), 6)


if __name__ == "__main__":
    unittest.main()
