"""Combined reading PDFs preserve sources and fail closed for mismatched pages."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

import fitz

from note_organizer.combined_pdf import (export_combined, materialize_combined,
                                         prune_reading_cache, render_combined_pdf)
from note_organizer import combined_pdf
from note_organizer.paper_registry import Registry
from note_organizer.remarkable_cloud import CloudError
from note_organizer.remarkable_pdf import annotated_pdf
from note_organizer.remarkable_sources import save_source_bundle, source_bundle
from note_organizer.storage import Store, digest_file
from tests.test_deferred_scene_margins import margin_fixture
from tests.test_remarkable import fixture


class CombinedPdfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.item, self.bundle = fixture()
        self.pc = self.root / "Paper.pdf"
        self.pc.write_bytes(self.bundle[self.item.id + ".pdf"])

    def tearDown(self):
        self.temp.cleanup()

    def link(self, pc=True):
        save_source_bundle(self.store, self.item, self.bundle)
        registry = Registry(self.store)
        if pc:
            paper = registry.register_local(self.pc)["paper_id"]
            registry.link_cloud(paper, self.item.id, hashlib.sha256(self.bundle[self.item.id + ".pdf"]).hexdigest())
        else:
            paper = registry.register_cloud(self.item.id, hashlib.sha256(self.bundle[self.item.id + ".pdf"]).hexdigest())["paper_id"]
        return paper

    def add_pc_note(self, text="Independent PC note"):
        with fitz.open(self.pc) as pdf:
            note = pdf[0].add_text_annot((80, 140), text)
            note.update()
            data = pdf.tobytes()
        self.pc.write_bytes(data)

    def add_pc_margin_ink(self, *, left=False, reach=675):
        with fitz.open(self.pc) as pdf:
            page = pdf[0]
            strokes = [[(580, 350), (650, 365)], [(630, 400), (reach, 415)]]
            if left:
                strokes.append([(-80, 450), (-25, 465)])
            for points in strokes:
                note = page.add_ink_annot([points])
                note.set_border(width=2)
                note.update()
            data = pdf.tobytes()
        self.pc.write_bytes(data)

    def assert_complete_margin_canvas(self, path, *, expected_notes):
        with fitz.open(path) as pdf:
            page = pdf[0]
            self.assertGreater(page.rect.width, 675)
            notes = list(page.annots())
            self.assertEqual(len(notes), expected_notes)
            bounds = page.rect * page.derotation_matrix
            self.assertTrue(all(bounds.contains(note.rect) for note in notes))
            self.assertIn("A selected scientific result", page.get_text())
            spans = [span for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]]
            self.assertTrue(any(abs(span["size"] - 11) < .01 for span in spans))

    @staticmethod
    def notes(path):
        with fitz.open(path) as pdf:
            return [annot.info for page in pdf for annot in page.annots() or ()]

    def test_current_pc_notes_and_tablet_marks_combine_once_without_changing_either_source(self):
        self.add_pc_note()
        paper = self.link()
        pc_before, tablet_before = self.pc.read_bytes(), dict(self.bundle)
        combined = materialize_combined(self.store, paper)
        notes = self.notes(combined)
        self.assertEqual(len(notes), 4)
        self.assertEqual(sum(note["content"] == "Independent PC note" for note in notes), 1)
        self.assertEqual(sum(note["content"] == "Typed margin note" for note in notes), 1)
        self.assertEqual(self.pc.read_bytes(), pc_before)
        self.assertEqual(source_bundle(self.store, self.item.id), tablet_before)
        self.assertEqual(combined.parent, self.store.path.parent / "remarkable" / "reading-cache")

    def test_native_pc_marks_inherited_in_tablet_baseline_are_not_repeated(self):
        self.add_pc_note()
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        paper = self.link()
        notes = self.notes(materialize_combined(self.store, paper))
        self.assertEqual(len(notes), 4)
        self.assertEqual(sum(note["content"] == "Independent PC note" for note in notes), 1)

    def test_native_baseline_note_missing_from_pc_requires_review_and_preserves_sources(self):
        plain_pc = self.pc.read_bytes()
        self.add_pc_note("A note already present when imported to tablet")
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        self.pc.write_bytes(plain_pc)
        paper = self.link()
        before = dict(self.bundle)
        with self.assertRaisesRegex(CloudError, "notes that are missing or different"):
            materialize_combined(self.store, paper)
        with self.assertRaisesRegex(CloudError, "notes that are missing or different"):
            render_combined_pdf(self.pc, self.item, self.bundle)
        self.assertEqual(self.pc.read_bytes(), plain_pc)
        self.assertEqual(source_bundle(self.store, self.item.id), before)

    def test_changed_native_baseline_note_requires_review_and_preserves_sources(self):
        self.add_pc_note("Original imported note")
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        with fitz.open(self.pc) as pdf:
            page = pdf[0]
            note = next(page.annots())
            note.set_info(content="Independent PC edit of imported note")
            note.update()
            changed = pdf.tobytes()
        self.pc.write_bytes(changed)
        paper = self.link()
        before = dict(self.bundle)
        with self.assertRaisesRegex(CloudError, "notes that are missing or different"):
            materialize_combined(self.store, paper)
        self.assertEqual(self.pc.read_bytes(), changed)
        self.assertEqual(source_bundle(self.store, self.item.id), before)

    def test_baseline_note_and_additional_pc_note_combine_with_tablet_marks_once(self):
        self.add_pc_note("Preserved imported note")
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        self.add_pc_note("Additional current PC note")
        paper = self.link()
        before = self.pc.read_bytes()
        notes = self.notes(materialize_combined(self.store, paper))
        self.assertEqual(len(notes), 5)
        self.assertEqual(sum(note["content"] == "Preserved imported note" for note in notes), 1)
        self.assertEqual(sum(note["content"] == "Additional current PC note" for note in notes), 1)
        self.assertEqual(sum(note["content"] == "Typed margin note" for note in notes), 1)
        self.assertEqual(self.pc.read_bytes(), before)

    def test_identical_baseline_notes_require_matching_multiplicity_per_page(self):
        self.add_pc_note("Same text at the same location")
        one_note = self.pc.read_bytes()
        self.add_pc_note("Same text at the same location")
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        self.pc.write_bytes(one_note)
        paper = self.link()
        with self.assertRaisesRegex(CloudError, "notes that are missing or different"):
            materialize_combined(self.store, paper)

    def test_changed_native_annotation_appearance_requires_review(self):
        self.add_pc_note("The note text stays identical")
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        with fitz.open(self.pc) as pdf:
            page = pdf[0]
            note = next(page.annots())
            pdf.xref_set_key(note.xref, "Name", "/Help")
            changed = pdf.tobytes()
        self.pc.write_bytes(changed)
        paper = self.link()
        with self.assertRaisesRegex(CloudError, "notes that are missing or different"):
            materialize_combined(self.store, paper)
        self.assertEqual(self.pc.read_bytes(), changed)

    def test_cloud_only_materializes_offline_without_any_visible_extra_pdf(self):
        paper = self.link(pc=False)
        self.pc.unlink()
        combined = materialize_combined(self.store, paper)
        self.assertEqual(len(self.notes(combined)), 3)
        self.assertEqual(list(self.root.glob("*.pdf")), [])

    def test_latest_conversion_or_local_conflict_review_cannot_be_hidden_by_older_cached_notes(self):
        paper = self.link()
        materialize_combined(self.store, paper)
        for state in ("review", "cloud unavailable"):
            for reason in ("conversion", "local_conflict"):
                with self.subTest(state=state, reason=reason):
                    self.store.save_remarkable_item(self.item.id, {"state": state, "reason_kind": reason})
                    with self.assertRaisesRegex(CloudError, "waiting for review"):
                        materialize_combined(self.store, paper)

    def test_source_inspection_and_rendering_use_one_immutable_revision(self):
        paper = self.link()
        changed = {name: data for name, data in self.bundle.items() if not name.endswith(".rm")}
        newer = replace(self.item, hash=hashlib.sha256(b"".join(changed.values())).hexdigest())
        real_info = combined_pdf.source_info
        advanced = False

        def advance_after_inspection(*args, **kwargs):
            nonlocal advanced
            result = real_info(*args, **kwargs)
            if not advanced:
                save_source_bundle(self.store, newer, changed)
                advanced = True
            return result

        with patch.object(combined_pdf, "source_info", side_effect=advance_after_inspection):
            old_view = materialize_combined(self.store, paper)
        self.assertEqual(len(self.notes(old_view)), 3)
        # A fresh unaccepted lookup sees the new blank tablet revision.
        self.assertEqual(materialize_combined(self.store, paper), self.pc)

    def test_retained_but_not_adopted_cloud_revision_does_not_replace_accepted_notes(self):
        paper = self.link()
        self.store.save_remarkable_item(self.item.id, {"storage_version": 2, "notes_migrated": True,
            "state": "synced", "hash": self.item.hash})
        changed = {name: data for name, data in self.bundle.items() if not name.endswith(".rm")}
        newer = replace(self.item, hash=hashlib.sha256(b"".join(changed.values())).hexdigest())
        save_source_bundle(self.store, newer, changed)
        combined = materialize_combined(self.store, paper)
        self.assertEqual(len(self.notes(combined)), 3)
        self.store.save_remarkable_item(self.item.id, {"storage_version": 2, "notes_migrated": True,
            "state": "synced", "hash": newer.hash})
        self.assertEqual(materialize_combined(self.store, paper), self.pc)

    def test_same_tablet_note_edited_independently_on_pc_requires_review_and_keeps_both_sources(self):
        self.pc.write_bytes(annotated_pdf(self.item, self.bundle))
        with fitz.open(self.pc) as pdf:
            for note in pdf[0].annots():
                if note.info["content"] == "Typed margin note":
                    note.set_info(content="This copy of the tablet note was edited on PC")
                    note.update()
            data = pdf.tobytes()
        self.pc.write_bytes(data)
        paper = self.link()
        with self.assertRaisesRegex(CloudError, "also edited on the PC"):
            materialize_combined(self.store, paper)
        self.assertEqual(self.pc.read_bytes(), data)
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)

    def test_same_tablet_note_with_pc_appearance_or_richtext_edit_requires_review(self):
        exported = annotated_pdf(self.item, self.bundle)
        paper = self.link()
        for key, value in (("Name", "/Help"), ("RC", "(<body><p>A PC-only rich text edit</p></body>)")):
            with self.subTest(key=key):
                with fitz.open(stream=exported, filetype="pdf") as pdf:
                    page = pdf[0]
                    note = next(note for note in page.annots() if note.info["content"] == "Typed margin note")
                    self.assertTrue(note.info["id"].startswith("remarkable-"))
                    pdf.xref_set_key(note.xref, key, value)
                    changed = pdf.tobytes(garbage=4, deflate=True)
                self.pc.write_bytes(changed)
                with self.assertRaisesRegex(CloudError, "also edited on the PC"):
                    materialize_combined(self.store, paper)
                self.assertEqual(self.pc.read_bytes(), changed)
                self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)

    def test_old_reading_cache_revision_is_rebuilt_and_still_disposable(self):
        paper = self.link()
        old = []
        for revision in (1, 2):
            with patch.object(combined_pdf, "COMBINED_REVISION", revision):
                old.append(materialize_combined(self.store, paper))
        current = materialize_combined(self.store, paper)
        self.assertTrue(all(path != current for path in old))
        self.assertEqual(len(self.notes(current)), 3)
        self.assertEqual(prune_reading_cache(self.store, limit_bytes=current.stat().st_size, keep=[current]), 2)
        self.assertTrue(all(not path.exists() for path in old))
        self.assertTrue(current.exists())

    def test_identical_stable_tablet_marks_already_present_on_pc_are_not_repeated(self):
        # Simulates a previously exported annotated PDF used as the PC copy.
        self.pc.write_bytes(annotated_pdf(self.item, self.bundle))
        paper = self.link()
        output = materialize_combined(self.store, paper)
        self.assertEqual(output.resolve(), self.pc.resolve())
        self.assertEqual(len(self.notes(output)), 3)

    def test_pc_annotation_edit_invalidates_cache_and_all_cloud_notes_remain(self):
        paper = self.link()
        first = materialize_combined(self.store, paper)
        self.add_pc_note("Added after first view")
        second = materialize_combined(self.store, paper)
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.notes(second)), 4)

    def test_blank_tablet_keeps_single_main_pdf_after_version_and_page_validation(self):
        self.bundle = {name: data for name, data in self.bundle.items() if not name.endswith(".rm")}
        paper = self.link()
        self.assertEqual(materialize_combined(self.store, paper).resolve(), self.pc.resolve())
        self.assertFalse((self.store.path.parent / "remarkable" / "reading-cache").exists())

    def test_unregistered_native_margin_notes_receive_complete_cached_canvas(self):
        self.add_pc_margin_ink(left=True)
        before = self.pc.read_bytes()
        reading = materialize_combined(self.store, self.pc)
        self.assertNotEqual(reading, self.pc)
        self.assertEqual(reading.parent, self.store.path.parent / "remarkable" / "reading-cache")
        self.assert_complete_margin_canvas(reading, expected_notes=3)
        self.assertEqual(self.pc.read_bytes(), before)
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_registry'").fetchone())

    def test_registered_pc_only_paper_receives_complete_margin_canvas(self):
        self.add_pc_margin_ink()
        paper = Registry(self.store).register_local(self.pc)["paper_id"]
        before = self.pc.read_bytes()
        self.assert_complete_margin_canvas(materialize_combined(self.store, paper), expected_notes=2)
        self.assertEqual(self.pc.read_bytes(), before)

    def test_blank_tablet_does_not_bypass_native_margin_canvas(self):
        self.bundle = {name: data for name, data in self.bundle.items() if not name.endswith(".rm")}
        self.add_pc_margin_ink()
        paper = self.link()
        before = self.pc.read_bytes()
        self.assert_complete_margin_canvas(materialize_combined(self.store, paper), expected_notes=2)
        self.assertEqual(self.pc.read_bytes(), before)
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)

    def test_already_inherited_tablet_marks_do_not_bypass_native_margin_canvas(self):
        self.pc.write_bytes(annotated_pdf(self.item, self.bundle))
        self.add_pc_margin_ink(left=True)
        paper = self.link()
        before = self.pc.read_bytes()
        self.assert_complete_margin_canvas(materialize_combined(self.store, paper), expected_notes=6)
        self.assertEqual(self.pc.read_bytes(), before)
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)

    def test_combined_renderer_expands_native_margins_after_tablet_merge(self):
        self.add_pc_margin_ink(left=True)
        before = self.pc.read_bytes()
        data = render_combined_pdf(self.pc, self.item, self.bundle)
        output = self.root / "combined-margins.pdf"
        output.write_bytes(data)
        self.assert_complete_margin_canvas(output, expected_notes=6)
        self.assertEqual(self.pc.read_bytes(), before)

    def test_deferred_tablet_margin_marks_deduplicate_before_rotated_cropped_canvas_expansion(self):
        for rotation in (0, 90, 180, 270):
            for cropped in (False, True):
                with self.subTest(rotation=rotation, cropped=cropped):
                    item, bundle, _ = margin_fixture(rotation=rotation, cropped=cropped)
                    self.pc.write_bytes(annotated_pdf(item, bundle, expand_margins=False))
                    before, source_before = self.pc.read_bytes(), dict(bundle)
                    data = render_combined_pdf(self.pc, item, bundle)
                    with fitz.open(stream=data, filetype="pdf") as output:
                        page = output[0]
                        notes = list(page.annots())
                        self.assertEqual(len(notes), 7)
                        self.assertEqual(len({note.info["id"] for note in notes}), 7)
                        self.assertEqual(page.rotation, rotation)
                        bounds = page.rect * page.derotation_matrix
                        self.assertTrue(all(bounds.contains(note.rect) for note in notes))
                        self.assertIn("A selected scientific result", page.get_text())
                    self.assertEqual(self.pc.read_bytes(), before)
                    self.assertEqual(bundle, source_before)

    def test_unsafe_native_margin_requires_review_without_publishing_or_changing_source(self):
        self.add_pc_margin_ink(reach=2000)
        before = self.pc.read_bytes()
        with self.assertRaisesRegex(CloudError, "beyond the supported PDF margin area"):
            materialize_combined(self.store, self.pc)
        self.assertEqual(self.pc.read_bytes(), before)
        self.assertFalse((self.store.path.parent / "remarkable" / "reading-cache").exists())

    def test_cloud_only_blank_tablet_with_native_margin_notes_gets_complete_canvas(self):
        self.add_pc_margin_ink()
        self.bundle[self.item.id + ".pdf"] = self.pc.read_bytes()
        self.bundle = {name: data for name, data in self.bundle.items() if not name.endswith(".rm")}
        paper = self.link(pc=False)
        self.pc.unlink()
        self.assert_complete_margin_canvas(materialize_combined(self.store, paper), expected_notes=2)
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)

    def test_native_margin_export_matches_reading_canvas_and_protects_unregistered_original(self):
        self.add_pc_margin_ink()
        before = self.pc.read_bytes()
        reading = materialize_combined(self.store, self.pc)
        output = self.root / "Complete margin export.pdf"
        export_combined(self.store, self.pc, output)
        self.assertEqual(output.read_bytes(), reading.read_bytes())
        self.assert_complete_margin_canvas(output, expected_notes=2)
        with self.assertRaisesRegex(CloudError, "original PDF stays intact"):
            export_combined(self.store, self.pc, self.pc, require_absent=False)
        self.assertEqual(self.pc.read_bytes(), before)
        prune_reading_cache(self.store, limit_bytes=0)
        self.assertTrue(output.is_file())

    def test_native_margin_cache_reuses_verified_output_and_invalidates_after_source_edit(self):
        self.add_pc_margin_ink()
        first = materialize_combined(self.store, self.pc)
        with patch.object(combined_pdf, "expand_annotation_margins", side_effect=AssertionError("Cache hit should not normalize again")):
            self.assertEqual(materialize_combined(self.store, self.pc), first)
        self.add_pc_note("New PC note after margin view")
        second = materialize_combined(self.store, self.pc, cache_limit_bytes=1)
        self.assertNotEqual(first, second)
        self.assertFalse(first.exists())
        self.assert_complete_margin_canvas(second, expected_notes=3)

    def test_cancel_during_native_margin_expansion_publishes_nothing(self):
        self.add_pc_margin_ink()
        before = self.pc.read_bytes()
        stopped = threading.Event()
        real_expand = combined_pdf.expand_annotation_margins
        def stop_after_expand(document, cancelled=None):
            result = real_expand(document, cancelled)
            stopped.set()
            return result
        with patch.object(combined_pdf, "expand_annotation_margins", side_effect=stop_after_expand):
            with self.assertRaises(InterruptedError):
                materialize_combined(self.store, self.pc, cancelled=stopped)
        self.assertFalse((self.store.path.parent / "remarkable" / "reading-cache").exists())
        self.assertEqual(self.pc.read_bytes(), before)

    def test_modified_printed_text_or_flattened_marks_need_review(self):
        paper = self.link()
        with fitz.open(self.pc) as pdf:
            pdf[0].insert_text((60, 170), "A different edition or flattened note")
            changed = pdf.tobytes()
        self.pc.write_bytes(changed)
        with self.assertRaisesRegex(CloudError, "different printed pages"):
            materialize_combined(self.store, paper)
        self.assertEqual(self.pc.read_bytes(), changed)

    def test_corrupt_pc_pdf_is_reviewed_and_preserved(self):
        paper = self.link()
        self.pc.write_bytes(b"This PC PDF was edited into an invalid file")
        with self.assertRaises(CloudError):
            materialize_combined(self.store, paper)
        with self.assertRaises(CloudError):
            render_combined_pdf(self.pc, self.item, self.bundle)
        self.assertEqual(self.pc.read_bytes(), b"This PC PDF was edited into an invalid file")

    def test_changed_visibility_of_printed_pdf_layer_requires_review(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=200, height=200)
            layer = pdf.add_ocg("Printed scientific diagram")
            page.draw_rect(fitz.Rect(20, 20, 100, 100), color=(1, 0, 0), fill=(1, 0, 0), oc=layer)
            self.bundle[self.item.id + ".pdf"] = pdf.tobytes()
        self.pc.write_bytes(self.bundle[self.item.id + ".pdf"])
        paper = self.link()
        with fitz.open(self.pc) as pdf:
            pdf.set_layer(-1, on=[], off=[layer])
            changed = pdf.tobytes()
        self.pc.write_bytes(changed)
        with self.assertRaisesRegex(CloudError, "different printed pages"):
            materialize_combined(self.store, paper)
        self.assertEqual(self.pc.read_bytes(), changed)

    def test_inherited_drawing_resources_are_part_of_printed_version_proof(self):
        with fitz.open() as pdf:
            page = pdf.new_page(width=200, height=200)
            page.insert_image(fitz.Rect(20, 20, 100, 100),
                              pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1), False))
            kind, resources = pdf.xref_get_key(page.xref, "Resources")
            self.assertEqual(kind, "xref")
            parent = int(pdf.xref_get_key(page.xref, "Parent")[1].split()[0])
            pdf.xref_set_key(parent, "Resources", resources)
            pdf.xref_set_key(page.xref, "Resources", "null")
            original = pdf.tobytes()
        with fitz.open(stream=original, filetype="pdf") as pdf:
            image = pdf[0].get_images()[0][0]
            pdf.update_stream(image, bytes((255, 0, 0)))
            changed = pdf.tobytes()
        with fitz.open(stream=original, filetype="pdf") as baseline, fitz.open(stream=changed, filetype="pdf") as pc:
            self.assertFalse(combined_pdf._same_printed_pages(pc, baseline, None))

    def test_reordered_or_added_pages_need_review_even_without_tablet_marks(self):
        for redirects in ([1, 0], [0, 1, -1]):
            with self.subTest(redirects=redirects):
                with fitz.open() as pdf:
                    pdf.new_page().insert_text((30, 60), "First printed page")
                    pdf.new_page().insert_text((30, 60), "Second printed page")
                    data = pdf.tobytes()
                self.pc.write_bytes(data)
                bundle = {self.item.id + ".pdf": data,
                          self.item.id + ".content": json.dumps({"fileType": "pdf", "pages": [str(i) for i in range(len(redirects))],
                                                                  "redirectionPageMap": redirects}).encode()}
                with self.assertRaisesRegex(CloudError, "added, removed or reordered"):
                    render_combined_pdf(self.pc, self.item, bundle)

    def test_virtual_tablet_source_path_resolves_to_combined_paper(self):
        paper = self.link()
        virtual = self.store.path.parent / "remarkable" / "documents" / (self.item.id + ".pdf")
        Registry(self.store).link_local(paper, virtual, digest="a" * 64,
                                       metadata={"role": "tablet_render", "cloud_id": self.item.id})
        self.assertFalse(virtual.exists())
        self.assertEqual(len(self.notes(materialize_combined(self.store, virtual))), 3)

    def test_missing_cache_rebuilds_offline_and_cache_hit_does_not_render_again(self):
        paper = self.link()
        first = materialize_combined(self.store, paper)
        with patch("note_organizer.combined_pdf.annotated_pdf", side_effect=AssertionError("Cache hit should not render")):
            self.assertEqual(materialize_combined(self.store, paper), first)
        first.unlink()
        replacement = materialize_combined(self.store, paper)
        self.assertTrue(replacement.is_file())
        self.assertEqual(len(self.notes(replacement)), 3)

    def test_simultaneous_readers_publish_one_complete_cached_pdf(self):
        paper = self.link()
        with ThreadPoolExecutor(max_workers=3) as pool:
            paths = list(pool.map(lambda _: materialize_combined(self.store, paper), range(3)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(len(self.notes(paths[0])), 3)
        self.assertEqual(len(list(paths[0].parent.glob("*.pdf"))), 1)

    def test_edited_cache_is_preserved_and_ignored_when_rebuilding_or_pruning(self):
        paper = self.link()
        original = materialize_combined(self.store, paper)
        original.write_bytes(b"User-edited cached output must be retained")
        replacement = materialize_combined(self.store, paper)
        self.assertNotEqual(original, replacement)
        self.assertEqual(len(self.notes(replacement)), 3)
        prune_reading_cache(self.store, limit_bytes=0)
        self.assertTrue(original.exists())
        self.assertEqual(original.read_bytes(), b"User-edited cached output must be retained")
        self.assertFalse(replacement.exists())

    def test_cache_budget_evicts_older_verified_output_but_preserves_sources_and_active_pdf(self):
        paper = self.link()
        first = materialize_combined(self.store, paper)
        os.utime(first, (1, 1))
        self.add_pc_note()
        second = materialize_combined(self.store, paper, cache_limit_bytes=1)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(self.pc.exists())
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)

    def test_edit_between_cache_inventory_and_deletion_is_preserved(self):
        paper = self.link()
        cached = materialize_combined(self.store, paper)
        guarded = combined_pdf._guarded_file
        def edit_before_guard(path, digest, action, **kwargs):
            if Path(path) == cached:
                cached.write_bytes(b"Edited immediately before guarded cache eviction")
            return guarded(path, digest, action, **kwargs)
        with patch("note_organizer.combined_pdf._guarded_file", side_effect=edit_before_guard) as checked:
            self.assertEqual(prune_reading_cache(self.store, limit_bytes=0), 0)
        checked.assert_called_once()
        self.assertEqual(cached.read_bytes(), b"Edited immediately before guarded cache eviction")

    def test_separate_cloud_documents_and_pc_versions_require_review(self):
        paper = self.link()
        other_id = str(uuid.uuid4())
        other_bundle = {name.replace(self.item.id, other_id): data for name, data in self.bundle.items()}
        save_source_bundle(self.store, replace(self.item, id=other_id), other_bundle)
        Registry(self.store).link_cloud(paper, other_id, digest_file(self.pc))
        with self.assertRaisesRegex(CloudError, "multiple tablet documents"):
            materialize_combined(self.store, paper)
        separate = self.root / "Independent copy.pdf"
        separate.write_bytes(self.pc.read_bytes())
        with fitz.open(separate) as pdf:
            pdf[0].add_text_annot((100, 150), "Separate notes")
            data = pdf.tobytes()
        separate.write_bytes(data)
        Registry(self.store).link_local(paper, separate)
        with self.assertRaisesRegex(CloudError, "multiple PC PDF versions"):
            materialize_combined(self.store, paper)

    def test_explicit_export_is_durable_and_cannot_overwrite_sources_or_private_cache(self):
        paper = self.link()
        exported = self.root / "Reading copy.pdf"
        export_combined(self.store, paper, exported)
        self.assertEqual(len(self.notes(exported)), 3)
        prune_reading_cache(self.store, limit_bytes=0)
        self.assertTrue(exported.is_file())
        with self.assertRaises(CloudError):
            export_combined(self.store, paper, exported)
        digest = digest_file(exported)
        self.add_pc_note()
        export_combined(self.store, paper, exported, expected_digest=digest, require_absent=False)
        self.assertEqual(len(self.notes(exported)), 4)
        with self.assertRaisesRegex(CloudError, "note source"):
            export_combined(self.store, paper, self.pc, require_absent=False)
        with self.assertRaisesRegex(CloudError, "private"):
            export_combined(self.store, paper, self.store.path.parent / "remarkable" / "bad.pdf")

    def test_cancel_does_not_publish_partial_output_and_unregistered_reads_do_not_create_registry(self):
        self.assertEqual(materialize_combined(self.store, self.pc), self.pc)
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='paper_registry'").fetchone())
        paper = self.link()
        stopped = threading.Event()
        stopped.set()
        with self.assertRaises(InterruptedError):
            materialize_combined(self.store, paper, cancelled=stopped)
        self.assertFalse((self.store.path.parent / "remarkable" / "reading-cache").exists())


if __name__ == "__main__":
    unittest.main()
