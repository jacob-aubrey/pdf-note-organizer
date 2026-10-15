"""Reader selection preserves physical pages, verified sources and PDF geometry."""
from copy import deepcopy
from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pymupdf as fitz

from note_organizer import pdf_worker
from note_organizer.pdf_margins import expand_annotation_margins
from note_organizer.ui import App


def native_annotation_rect(document, annotation):
    kind, value = document.xref_get_key(annotation.xref, "Rect")
    assert kind == "array"
    return [float(number) for number in re.findall(r"[+-]?(?:\d+\.?\d*|\.\d+)", value)]


class ReaderLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def paper(self, name="source.pdf", *, rotation=0, cropped=False, pages=1):
        path = self.folder / name
        with fitz.open() as document:
            for _ in range(pages):
                document.new_page(width=600, height=800)
            page = document[-1]
            if cropped:
                page.set_cropbox(fitz.Rect(40, 60, 550, 740))
            page.set_rotation(rotation)
            note = page.add_rect_annot(fitz.Rect(20, 30, 100, 90))
            note.set_info(content="Saved selection")
            rectangle = list(note.rect)
            native = native_annotation_rect(document, note)
            document.save(path)
        return path, rectangle, native

    def assertRectAlmostEqual(self, actual, expected):
        self.assertIsNotNone(actual)
        self.assertEqual(len(actual), 4)
        for left, right in zip(actual, expected):
            self.assertAlmostEqual(left, right, places=4)

    def test_saved_rectangles_convert_to_native_pdf_coordinates_for_crops_and_rotations(self):
        for cropped in (False, True):
            for rotation in (0, 90, 180, 270):
                with self.subTest(cropped=cropped, rotation=rotation):
                    source, rect, native = self.paper(f"source-{cropped}-{rotation}.pdf",
                                                      rotation=rotation, cropped=cropped)
                    before = source.read_bytes()
                    result = pdf_worker._reader_location(source, 1, source, 1, rect)
                    self.assertEqual(result["pages"], 1)
                    self.assertRectAlmostEqual(result["rect"], native)
                    self.assertEqual(source.read_bytes(), before)

    def test_different_target_margins_do_not_shift_the_saved_note_native_rectangle(self):
        source, rect, native = self.paper(cropped=True)
        target = self.folder / "combined.pdf"
        with fitz.open(source) as document:
            document[0].add_rect_annot(fitz.Rect(-70, 150, -20, 220))
            self.assertTrue(expand_annotation_margins(document))
            document.save(target)
        source_before, target_before = source.read_bytes(), target.read_bytes()
        result = pdf_worker._reader_location(target, 1, source, 1, rect)
        self.assertRectAlmostEqual(result["rect"], native)
        self.assertEqual(source.read_bytes(), source_before)
        self.assertEqual(target.read_bytes(), target_before)

    def test_saved_extraction_margin_coordinates_map_to_another_expanded_target(self):
        original, _, _ = self.paper()
        source, target = self.folder / "extraction.pdf", self.folder / "reading.pdf"
        with fitz.open(original) as document:
            selected = document[0].add_rect_annot(fitz.Rect(-45, 90, -10, 130))
            self.assertTrue(expand_annotation_margins(document))
            document.save(source)
        with fitz.open(source) as document:
            # Stored extraction rectangles are measured after margin expansion.
            page = document[0]
            selected = list(page.annots())[-1]
            rect = list(selected.rect)
            native = native_annotation_rect(document, selected)
            page.add_rect_annot(fitz.Rect(-70, 210, -20, 250))
            self.assertTrue(expand_annotation_margins(document))
            document.save(target)
        before = {path: hashlib.sha256(path.read_bytes()).digest() for path in (source, target)}
        result = pdf_worker._reader_location(target, 1, source, 1, rect)
        self.assertRectAlmostEqual(result["rect"], native)
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)

    def test_target_physical_page_is_distinct_from_source_annotation_page(self):
        source, rect, native = self.paper(pages=2, cropped=True)
        target = self.folder / "inserted-target-page.pdf"
        with fitz.open() as document, fitz.open(source) as input_pdf:
            document.new_page(width=600, height=800)
            document.new_page(width=600, height=800)
            document.insert_pdf(input_pdf, from_page=1, to_page=1)
            document.save(target)
        result = pdf_worker._reader_location(target, 3, source, 2, rect)
        self.assertEqual(result["pages"], 3)
        self.assertRectAlmostEqual(result["rect"], native)

    def test_invalid_and_missing_target_pages_fail_instead_of_silently_clamping(self):
        source, _, _ = self.paper()
        for page in (0, -1, True, 1.5, "1", None):
            with self.subTest(page=page), self.assertRaisesRegex(ValueError, "physical PDF page"):
                pdf_worker._reader_location(source, page)
        with self.assertRaisesRegex(ValueError, "has 1 pages"):
            pdf_worker._reader_location(source, 2)
        with self.assertRaises(OSError):
            pdf_worker._reader_location(self.folder / "missing.pdf", 1)

    def test_password_target_is_rejected_but_missing_historic_source_keeps_page_only_reading(self):
        source, rect, _ = self.paper()
        locked = self.folder / "locked.pdf"
        with fitz.open(source) as document:
            document.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="reader", owner_pw="owner")
        with self.assertRaisesRegex(ValueError, "password"):
            pdf_worker._reader_location(locked, 1)
        for historic, page in ((self.folder / "missing.pdf", 1), (locked, 1), (source, 2)):
            with self.subTest(historic=historic, page=page):
                result = pdf_worker._reader_location(source, 1, historic, page, rect)
                self.assertEqual(result, {"pages": 1, "rect": None})

    def test_invalid_saved_rectangles_degrade_to_page_only(self):
        source, _, _ = self.paper()
        for rect in ([], [1, 2, 3], [1, 2, 3, 4, 5], [1, 2, float("nan"), 4],
                     [1, 2, float("inf"), 4], [3, 2, 1, 4], [1, 1, 1, 1]):
            with self.subTest(rect=rect):
                self.assertIsNone(pdf_worker._reader_location(source, 1, source, 1, rect)["rect"])

    def test_cancellation_and_target_file_change_do_not_return_a_stale_location(self):
        source, _, _ = self.paper()
        before = source.read_bytes()
        with patch.object(pdf_worker, "_check_cancelled", side_effect=InterruptedError("cancelled")):
            with self.assertRaises(InterruptedError):
                pdf_worker._reader_location(source, 1)
        with patch.object(pdf_worker, "_check_cancelled", side_effect=[None, InterruptedError("cancelled")]):
            with self.assertRaises(InterruptedError):
                pdf_worker._reader_location(source, 1)
        with patch.object(pdf_worker, "_file_version", side_effect=[("old",), ("new",)]):
            with self.assertRaisesRegex(OSError, "changed while loading"):
                pdf_worker._reader_location(source, 1)
        self.assertEqual(source.read_bytes(), before)


class ReaderDocumentTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / "selected-original.pdf"
        self.resolved = self.folder / "verified-reading.pdf"
        self.app = App.__new__(App)
        self.app.store = SimpleNamespace(path=self.folder / "library.sqlite3")
        self.app.pdf_worker = Mock(spec=["materialize_cancellable", "materialize_source", "reader_location"])
        self.app.pdf_worker.materialize_cancellable.return_value = str(self.resolved)
        self.app.pdf_worker.materialize_source.return_value = str(self.source)
        self.app.pdf_worker.reader_location.return_value = {"pages": 9, "rect": [10, 20, 30, 40]}
        self.cancelled = Mock(return_value=False)

    def tearDown(self):
        self.temp.cleanup()

    def entry(self, **changes):
        return {"document_id": "doc", "key": "selected", "path": str(self.source),
                "page": 2, "kind": "highlight", "rect": [1, 2, 3, 4],
                "metadata": {"title": "Selected original paper"}, **changes}

    def test_nonmanaged_pdf_uses_exact_selected_file_without_materializing_linked_versions(self):
        for catalog in (False, True):
            with self.subTest(catalog=catalog):
                self.app.pdf_worker.reset_mock()
                entry = self.entry(kind="pdf", pdf_document=catalog, combined_view_path="different-edition.pdf")
                before = deepcopy(entry)
                result = self.app.load_reader_document(entry, self.cancelled)
                self.app.pdf_worker.materialize_cancellable.assert_not_called()
                self.app.pdf_worker.materialize_source.assert_called_once_with(
                    self.app.store.path, str(self.source), self.cancelled)
                self.app.pdf_worker.reader_location.assert_called_once_with(
                    self.source, 2, str(self.source), 2, None, self.cancelled)
                self.assertEqual(result["path"], str(self.source.resolve()))
                self.assertEqual(result["page"], 2)
                self.assertEqual(entry, before)

    def test_annotations_and_logical_pdf_documents_require_verified_cancellable_materialization(self):
        for entry in (self.entry(), self.entry(logical_paper_id="paper-identity", combined_view_page=4),
                      self.entry(kind="pdf", logical_paper_id="paper-identity", combined_view_page=4)):
            with self.subTest(entry=entry):
                self.app.pdf_worker.reset_mock()
                result = self.app.load_reader_document(entry, self.cancelled)
                reference, page = App.entry_pdf_target(entry)
                self.app.pdf_worker.materialize_cancellable.assert_called_once_with(
                    self.app.store.path, reference, self.cancelled)
                self.app.pdf_worker.materialize_source.assert_not_called()
                self.app.pdf_worker.reader_location.assert_called_once_with(
                    self.resolved, page, str(self.source), 2,
                    entry["rect"] if entry["kind"] != "pdf" else None, self.cancelled)
                self.assertEqual(result["path"], str(self.resolved.resolve()))
                self.assertEqual(result["page"], page)

    def test_ambiguous_or_missing_sources_fail_before_preparation(self):
        with self.assertRaisesRegex(ValueError, "No verified page mapping"):
            self.app.load_reader_document(self.entry(combined_view_unavailable="No verified page mapping"), self.cancelled)
        with self.assertRaisesRegex(FileNotFoundError, "unavailable"):
            self.app.load_reader_document(self.entry(missing=True), self.cancelled)
        self.app.pdf_worker.materialize_cancellable.assert_not_called()
        self.app.pdf_worker.materialize_source.assert_not_called()
        self.app.pdf_worker.reader_location.assert_not_called()

    def test_managed_tablet_notes_keep_page_only_navigation_without_trusted_extraction_geometry(self):
        for metadata in ({"managed_cloud_id": "tablet-id"}, {"tablet_layers_only": True}):
            with self.subTest(metadata=metadata):
                self.app.pdf_worker.reset_mock()
                entry = self.entry(logical_paper_id="paper-identity", combined_view_page=4,
                                   source_path="nonexistent-private-extraction.pdf", metadata=metadata)
                result = self.app.load_reader_document(entry, self.cancelled)
                self.app.pdf_worker.reader_location.assert_called_once_with(
                    self.resolved, 4, str(self.source), 2, None, self.cancelled)
                self.assertEqual(result["page"], 4)

    def test_cancelled_selection_does_not_start_or_complete_the_wrong_document(self):
        self.cancelled.return_value = True
        with self.assertRaises(InterruptedError):
            self.app.load_reader_document(self.entry(), self.cancelled)
        self.app.pdf_worker.materialize_cancellable.assert_not_called()
        self.cancelled.side_effect = [False, True]
        with self.assertRaises(InterruptedError):
            self.app.load_reader_document(self.entry(), self.cancelled)
        self.app.pdf_worker.materialize_cancellable.assert_called_once()
        self.app.pdf_worker.reader_location.assert_not_called()

    def test_materialization_failure_never_falls_back_to_an_unverified_source(self):
        self.app.pdf_worker.materialize_cancellable.side_effect = ValueError("Page versions need review")
        with self.assertRaisesRegex(ValueError, "Page versions need review"):
            self.app.load_reader_document(self.entry(logical_paper_id="paper-identity"), self.cancelled)
        self.app.pdf_worker.reader_location.assert_not_called()

    def test_open_externally_uses_original_file_and_system_viewer_preference(self):
        entry = self.entry(logical_paper_id="paper-identity", combined_view_path=str(self.resolved), combined_view_page=7)
        self.app.selected_entry = Mock(return_value=entry)
        self.app.notify = Mock()
        self.app.root = object()
        self.app.viewer_preference = {"viewer": "custom", "path": "other-viewer.exe"}
        with patch("note_organizer.ui.open_pdf_page", return_value=("Opened default PDF viewer", True)) as opened:
            self.app.open_source_external()
        opened.assert_called_once_with(str(self.source), 2, {"viewer": "system"})
        self.app.pdf_worker.materialize_cancellable.assert_not_called()
        self.app.notify.assert_called_once_with("Opened default PDF viewer", "notes")


class ReaderExactSourceWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.library = self.folder / "existing.sqlite3"
        # A valid SQLite file without the app's schema must remain untouched.
        with closing(sqlite3.connect(self.library)) as db:
            db.execute("CREATE TABLE preserved(value TEXT)")
            db.execute("INSERT INTO preserved VALUES('unchanged')")
            db.commit()
        self.database_before = self.library.read_bytes()
        self.worker = pdf_worker.PDFWorker()

    def tearDown(self):
        self.worker.shutdown()
        self.temp.cleanup()

    def test_exact_source_margin_ink_gets_complete_private_reading_copy_without_mutating_original(self):
        source = self.folder / "exact-version.pdf"
        with fitz.open() as document:
            page = document.new_page(width=600, height=800)
            page.insert_text((50, 80), "Exact selected PDF edition")
            ink = page.add_ink_annot([[(20, 100), (-35, 130), (-20, 170)]])
            native = native_annotation_rect(document, ink)
            document.save(source)
        before = source.read_bytes()
        reading = Path(self.worker.materialize_source(self.library, source))
        self.assertNotEqual(reading, source)
        self.assertTrue(reading.is_relative_to(self.folder / "remarkable" / "reading-cache"))
        with fitz.open(reading) as document:
            page = document[0]
            self.assertGreater(page.rect.width, 600)
            self.assertIn("Exact selected PDF edition", page.get_text())
            ink = next(page.annots())
            self.assertTrue((page.rect * page.derotation_matrix).contains(ink.rect))
            self.assertEqual(native_annotation_rect(document, ink), native)
        # Native parsing and margin preparation run outside Tk's process.
        self.assertTrue(self.worker._pool._processes)
        self.assertNotEqual(next(iter(self.worker._pool._processes.values())).pid, os.getpid())
        version = reading.stat().st_mtime_ns
        self.assertEqual(Path(self.worker.materialize_source(self.library, source)), reading)
        self.assertEqual(reading.stat().st_mtime_ns, version)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(self.library.read_bytes(), self.database_before)

    def test_plain_exact_source_returns_original_and_never_initializes_or_writes_database_schema(self):
        source = self.folder / "plain-source.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((50, 80), "Plain selected edition")
            document.save(source)
        before = source.read_bytes()
        self.assertEqual(Path(self.worker.materialize_source(self.library, source)), source)
        self.assertEqual(self.library.read_bytes(), self.database_before)
        with closing(sqlite3.connect(self.library)) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("preserved",)])
        absent_library = self.folder / "absent" / "never-created.sqlite3"
        self.assertEqual(Path(self.worker.materialize_source(absent_library, source)), source)
        self.assertFalse(absent_library.exists())
        self.assertFalse(absent_library.parent.exists())
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
