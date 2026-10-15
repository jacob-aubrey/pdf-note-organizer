"""Isolated PDF jobs, bounded page previews, and responsive caller regressions."""
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from io import BytesIO
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import fitz
from PIL import Image

from note_organizer.extraction import extract
from note_organizer.pdf_worker import PDFWorker, _ReadOnlyPDFStore, _full_page, MAX_PREVIEW_PIXELS, MAX_PREVIEW_SIDE
from note_organizer.paper_registry import Registry
from note_organizer.remarkable_cloud import CloudError
from note_organizer.remarkable_pdf import annotated_pdf
from note_organizer.remarkable_sources import save_source_bundle
from note_organizer.storage import DEFAULT_SETTINGS, Store, digest_file
from tests.test_remarkable import fixture


def crash_process(marker):
    """Simulate a native PDF crash only inside a disposable spawned process."""
    with open(marker, "a", encoding="utf-8") as stream:
        stream.write("started once\n")
    os._exit(23)


class PDFWorkerTests(unittest.TestCase):
    def test_search_page_highlights_matches_without_changing_original(self):
        with fitz.open() as document:
            page = document.new_page(width=300, height=220)
            page.insert_text((30, 50), "Gold imaging and iodine")
            page.insert_text((30, 100), "Spectral")
            page.insert_text((30, 115), "CT experiment")
            page.set_rotation(90)
            document.save(self.path)
        original = self.path.read_bytes()
        plain = _full_page(self.path, 1)
        marked = self.worker.search_page(self.path, 1, ["gold", "spectral ct"])
        self.assertNotEqual(plain, marked)
        self.assertNotEqual(self.worker.search_page(self.path, 1, ["gold"]), marked)
        with Image.open(BytesIO(marked)) as image:
            self.assertLess(image.width, image.height)
            pixels = list(image.convert("RGB").get_flattened_data())
            self.assertTrue(any(b > 245 and 180 < r < 235 and r < g < 245 for r, g, b in pixels))
        self.assertEqual(self.path.read_bytes(), original)
        with fitz.open(self.path) as document:
            self.assertEqual(list(document[0].annots() or ()), [])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "article.pdf"
        with fitz.open() as document:
            page = document.new_page(width=600, height=800)
            page.insert_text((50, 80), "A highlighted research result")
            page.add_highlight_annot(page.search_for("highlighted research result"))
            document.save(self.path)
        self.worker = PDFWorker()

    def tearDown(self):
        self.worker.shutdown()
        self.folder.cleanup()

    def test_lazy_process_extraction_matches_direct_results(self):
        self.assertIsNone(self.worker._pool)
        expected = extract(self.path, DEFAULT_SETTINGS)
        self.assertEqual(self.worker.extract(self.path, DEFAULT_SETTINGS), expected)
        # Verify native work really ran outside the caller's interpreter.
        processes = list(self.worker._pool._processes.values())
        self.assertEqual(len(processes), 1)
        self.assertNotEqual(processes[0].pid, os.getpid())
        self.assertEqual(self.worker._context.get_start_method(), "spawn")

    def test_cloud_render_preserves_direct_pdf_content(self):
        item, bundle = fixture()
        before = dict(bundle)
        expected = annotated_pdf(item, bundle)
        actual = self.worker.render(item, bundle)
        with fitz.open(stream=expected, filetype="pdf") as direct, fitz.open(stream=actual, filetype="pdf") as isolated:
            self.assertEqual(len(isolated), len(direct))
            self.assertEqual(isolated.metadata, direct.metadata)
            for index in range(len(direct)):
                direct_page, isolated_page = direct[index], isolated[index]
                self.assertEqual(isolated_page.get_text(), direct_page.get_text())
                properties = lambda page: [(annotation.type, annotation.info, annotation.colors, annotation.vertices)
                                           for annotation in page.annots() or []]
                self.assertEqual(properties(isolated_page), properties(direct_page))
        self.assertEqual(bundle, before)

    def test_combined_view_preview_and_durable_export_share_one_read_only_process(self):
        item, bundle = fixture()
        self.path.write_bytes(bundle[item.id + ".pdf"])
        with fitz.open(self.path) as document:
            page = document[0]
            page.add_text_annot((80, 140), "Independent PC note")
            data = document.tobytes()
        self.path.write_bytes(data)
        store = Store(Path(self.folder.name) / "data" / "notes.sqlite3")
        save_source_bundle(store, item, bundle)
        registry = Registry(store)
        paper = registry.register_local(self.path)["paper_id"]
        import hashlib
        registry.link_cloud(paper, item.id, hashlib.sha256(bundle[item.id + ".pdf"]).hexdigest())
        before = store.path.read_bytes()
        original = self.path.read_bytes()
        combined = Path(self.worker.materialize(store.path, paper))
        process = next(iter(self.worker._pool._processes.values()))
        self.assertNotEqual(process.pid, os.getpid())
        with fitz.open(combined) as document:
            notes = [note.info["content"] for page in document for note in page.annots() or ()]
            self.assertEqual(len(notes), 4)
            self.assertEqual(notes.count("Independent PC note"), 1)
            self.assertEqual(notes.count("Typed margin note"), 1)
        self.assertTrue(self.worker.full_page(combined, 1).startswith(b"\x89PNG"))
        destination = Path(self.folder.name) / "Explicit annotated export.pdf"
        self.assertEqual(Path(self.worker.export_combined(store.path, paper, destination)), destination)
        self.assertEqual(destination.read_bytes(), combined.read_bytes())
        expected = digest_file(destination)
        self.worker.export_combined(store.path, paper, destination, expected_digest=expected, require_absent=False)
        with self.assertRaises(CloudError):
            self.worker.export_combined(store.path, paper, destination, expected_digest="changed", require_absent=False)
        self.assertEqual(digest_file(destination), expected)
        self.assertEqual(next(iter(self.worker._pool._processes.values())).pid, process.pid)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(store.path.read_bytes(), before)

    def test_combined_render_and_tablet_only_extraction_inputs_preserve_separate_sources(self):
        item, bundle = fixture()
        self.path.write_bytes(bundle[item.id + ".pdf"])
        with fitz.open(self.path) as document:
            page = document[0]
            page.add_text_annot((80, 140), "PC note inherited by upload")
            data = document.tobytes()
        self.path.write_bytes(data)
        bundle[item.id + ".pdf"] = data
        before = dict(bundle)
        combined = self.worker.render_combined(self.path, item, bundle)
        process = next(iter(self.worker._pool._processes.values()))
        tablet = self.worker.tablet_only(item, bundle)
        with fitz.open(stream=combined, filetype="pdf") as document:
            notes = [note.info["content"] for page in document for note in page.annots() or ()]
            self.assertEqual(len(notes), 4)
            self.assertEqual(notes.count("PC note inherited by upload"), 1)
        with fitz.open(stream=tablet, filetype="pdf") as document:
            notes = [note.info["content"] for page in document for note in page.annots() or ()]
            self.assertEqual(len(notes), 3)
            self.assertIn("Typed margin note", notes)
            self.assertNotIn("PC note inherited by upload", notes)
        self.assertEqual(next(iter(self.worker._pool._processes.values())).pid, process.pid)
        self.assertEqual(bundle, before)
        self.assertEqual(self.path.read_bytes(), data)

    def test_reading_adapter_cannot_create_or_mutate_a_library(self):
        missing = Path(self.folder.name) / "does not exist.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            self.worker.materialize(missing, self.path)
        self.assertFalse(missing.exists())
        store = Store(Path(self.folder.name) / "notes.sqlite3")
        reader = _ReadOnlyPDFStore(store.path)
        with reader.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("CREATE TABLE viewing_must_not_write(value TEXT)")
        with store.connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='viewing_must_not_write'").fetchone())

    def test_full_page_uses_physical_number_and_shows_annotations(self):
        with fitz.open() as document:
            for index in range(2):
                page = document.new_page(width=600, height=800)
                page.insert_text((50, 80), f"Physical page {index+1}")
                annotation = page.add_rect_annot(fitz.Rect(60, 120, 200, 260))
                color = (1, 0, 0) if index == 0 else (0, 0, 1)
                annotation.set_colors(stroke=color, fill=color)
                annotation.update()
            document.set_page_labels([{"startpage": 0, "style": "D", "firstpagenum": 233}])
            document.save(self.path)
        with Image.open(BytesIO(self.worker.full_page(self.path, 2))) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
            colors = image.getdata()
            self.assertGreater(sum(blue > 200 and red < 50 for red, green, blue in colors), 100)
            self.assertEqual(sum(red > 200 and blue < 50 for red, green, blue in image.getdata()), 0)
        for page_number in (0, -1, True, "2", 233, 3):
            with self.subTest(page=page_number), self.assertRaises(ValueError):
                self.worker.full_page(self.path, page_number)

    def test_preview_bounds_honor_rotation_crop_and_large_square(self):
        for size, rotation, crop in (((600, 800), 90, fitz.Rect(50, 50, 550, 700)),
                                     ((4000, 4000), 0, None), ((1200, 3000), 270, None)):
            with self.subTest(size=size, rotation=rotation):
                with fitz.open() as document:
                    page = document.new_page(width=size[0], height=size[1])
                    if crop is not None:
                        page.set_cropbox(crop)
                    page.set_rotation(rotation)
                    ratio = page.rect.width/page.rect.height
                    document.save(self.path)
                with Image.open(BytesIO(self.worker.full_page(self.path, 1))) as image:
                    self.assertLessEqual(max(image.size), MAX_PREVIEW_SIDE)
                    self.assertLessEqual(image.width*image.height, MAX_PREVIEW_PIXELS)
                    self.assertAlmostEqual(image.width/image.height, ratio, delta=.004)

    def test_changing_source_rejects_preview(self):
        original = fitz.Page.get_pixmap

        def changing(page, *args, **kwargs):
            result = original(page, *args, **kwargs)
            info = self.path.stat()
            os.utime(self.path, ns=(info.st_atime_ns, info.st_mtime_ns+1_000_000))
            return result

        with patch.object(fitz.Page, "get_pixmap", new=changing), self.assertRaisesRegex(OSError, "changed"):
            _full_page(self.path, 1)

    def test_cancel_before_start_and_shutdown_are_idempotent(self):
        self.worker.cancel()
        with self.assertRaises(InterruptedError):
            self.worker.extract(self.path, DEFAULT_SETTINGS)
        self.assertIsNone(self.worker._pool)
        self.worker.shutdown(wait=False)
        self.worker.shutdown(wait=True)
        self.worker.shutdown(wait=True)
        with self.assertRaises(InterruptedError):
            self.worker.full_page(self.path, 1)

    def test_native_crash_fails_once_then_next_job_starts_a_new_process(self):
        self.worker.full_page(self.path, 1)
        previous = next(iter(self.worker._pool._processes.values()))
        marker = Path(self.folder.name) / "crash attempts.txt"
        with self.assertRaises(BrokenProcessPool):
            self.worker._call(crash_process, str(marker))
        self.assertIsNone(self.worker._pool)
        self.assertFalse(previous.is_alive())
        self.assertEqual(marker.read_text(encoding="utf-8"), "started once\n")
        self.assertTrue(self.worker.full_page(self.path, 1).startswith(b"\x89PNG"))
        current = next(iter(self.worker._pool._processes.values()))
        self.assertNotEqual(current.pid, previous.pid)
        self.assertEqual(marker.read_text(encoding="utf-8"), "started once\n")

    def test_already_broken_pool_at_submission_is_retired_for_next_request(self):
        failed = Mock()
        failed.submit.side_effect = BrokenProcessPool("Synthetic failed PDF process")
        self.worker._pool = failed
        with self.assertRaises(BrokenProcessPool):
            self.worker.full_page(self.path, 1)
        failed.shutdown.assert_called_once_with(wait=True, cancel_futures=True)
        self.assertIsNone(self.worker._pool)
        self.assertFalse(self.worker._retiring)
        self.assertTrue(self.worker.full_page(self.path, 1).startswith(b"\x89PNG"))

    def test_nonblocking_close_still_waits_for_concurrent_failed_pool_cleanup(self):
        failed = Mock()
        failed.submit.side_effect = BrokenProcessPool("Synthetic failed PDF process")
        entered, release = threading.Event(), threading.Event()

        def cleanup(**kwargs):
            entered.set()
            release.wait(timeout=5)

        failed.shutdown.side_effect = cleanup
        self.worker._pool = failed
        with ThreadPoolExecutor(max_workers=1) as caller:
            result = caller.submit(self.worker.full_page, self.path, 1)
            try:
                self.assertTrue(entered.wait(timeout=2))
                started = time.perf_counter()
                self.worker.shutdown(wait=False)
                self.assertLess(time.perf_counter()-started, .5)
                self.assertFalse(self.worker._shutdown_done.is_set())
            finally:
                release.set()
            with self.assertRaises(BrokenProcessPool):
                result.result(timeout=2)
        self.worker.shutdown(wait=True)
        self.assertTrue(self.worker._shutdown_done.is_set())
        failed.shutdown.assert_called_once_with(wait=True, cancel_futures=True)

    def test_concurrent_background_callers_keep_heartbeat_running(self):
        with fitz.open() as document:
            page = document.new_page(width=600, height=3600)
            for index in range(100):
                text = f"Line {index:03}: A highlighted research result with context."
                page.insert_text((40, 50+30*index), text)
                page.add_highlight_annot(page.search_for(text))
            document.save(self.path)
        self.worker.full_page(self.path, 1)  # Warm process startup independently.
        with ThreadPoolExecutor(max_workers=2) as callers:
            extraction = callers.submit(self.worker.extract, self.path, DEFAULT_SETTINGS)
            preview = callers.submit(self.worker.full_page, self.path, 1)
            ticks, last_tick, largest_gap = 0, time.perf_counter(), 0
            deadline = last_tick+30
            while not extraction.done() or not preview.done():
                time.sleep(.005)
                now = time.perf_counter()
                largest_gap = max(largest_gap, now-last_tick)
                last_tick, ticks = now, ticks+1
                if now > deadline:
                    self.fail("Synthetic PDF work exceeded the test deadline")
            self.assertEqual(len(extraction.result()[3]), 100)
            self.assertTrue(preview.result().startswith(b"\x89PNG"))
            self.assertGreater(ticks, 5)
            self.assertLess(largest_gap, .5)

    def test_cancel_inflight_stops_at_extraction_boundary(self):
        with fitz.open() as document:
            page = document.new_page(width=600, height=3600)
            for index in range(100):
                text = f"Line {index:03}: A highlighted research result with context."
                page.insert_text((40, 50+30*index), text)
                page.add_highlight_annot(page.search_for(text))
            document.save(self.path)
        self.worker.full_page(self.path, 1)
        process = next(iter(self.worker._pool._processes.values()))
        with ThreadPoolExecutor(max_workers=1) as caller:
            result = caller.submit(self.worker.extract, self.path, DEFAULT_SETTINGS)
            time.sleep(.03)
            self.assertFalse(result.done())
            self.worker.cancel()
            with self.assertRaises(InterruptedError):
                result.result(timeout=10)
        self.worker.shutdown(wait=False)
        self.worker.shutdown(wait=True)
        self.assertFalse(process.is_alive())


if __name__ == "__main__":
    unittest.main()
