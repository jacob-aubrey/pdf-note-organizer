"""Run native PDF work in one spawned process, leaving Tk's interpreter free."""
from concurrent.futures import CancelledError, ProcessPoolExecutor, TimeoutError
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
import json
import logging
import math
import multiprocessing
import os
from pathlib import Path
import sqlite3
import threading
import heapq
import itertools


_cancel_event = None
_job_cancel_event = None
MAX_PREVIEW_SIDE = 1600
MAX_PREVIEW_PIXELS = 2_000_000


def _initialize(cancel_event, job_cancel_event=None):
    global _cancel_event, _job_cancel_event
    _cancel_event = cancel_event
    _job_cancel_event = job_cancel_event


def _cancelled():
    return bool((_cancel_event is not None and _cancel_event.is_set()) or
                (_job_cancel_event is not None and _job_cancel_event.is_set()))


def _check_cancelled():
    if _cancelled():
        raise InterruptedError("PDF work stopped")


def _extract(path, settings):
    from .extraction import extract
    _check_cancelled()
    result = extract(path, settings, _cancelled)
    _check_cancelled()
    return result


def _render(item, bundle):
    from .remarkable_pdf import annotated_pdf
    _check_cancelled()
    result = annotated_pdf(item, bundle, _cancelled)
    _check_cancelled()
    return result


class _ReadOnlyPDFStore:
    """Minimal existing-library reader; viewing must never initialize a Store."""
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connect(self):
        # URI mode=ro refuses a missing library instead of creating an empty
        # SQLite file, and prevents a reading job from changing its schema.
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        try:
            yield db
        finally:
            db.close()

    def remarkable_items(self):
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='remarkable_items'").fetchone():
                return {}
            return {row["id"]: json.loads(row["payload"]) for row in db.execute("SELECT id,payload FROM remarkable_items")}


def _materialize(library_path, reference):
    from .combined_pdf import materialize_combined
    _check_cancelled()
    result = materialize_combined(_ReadOnlyPDFStore(library_path), reference, cancelled=_cancelled)
    _check_cancelled()
    return os.fspath(result)


def _export_combined(library_path, reference, target, expected_digest, require_absent):
    from .combined_pdf import export_combined
    _check_cancelled()
    result = export_combined(_ReadOnlyPDFStore(library_path), reference, target,
                             expected_digest=expected_digest, require_absent=require_absent,
                             cancelled=_cancelled)
    _check_cancelled()
    return os.fspath(result)


def _render_combined(local_path, item, bundle):
    from .combined_pdf import render_combined_pdf
    _check_cancelled()
    result = render_combined_pdf(local_path, item, bundle, cancelled=_cancelled)
    _check_cancelled()
    return result


def _tablet_only(item, bundle):
    from .cloud_notes import tablet_only_pdf
    _check_cancelled()
    result = tablet_only_pdf(item, bundle, _cancelled)
    _check_cancelled()
    return result


def _file_version(path):
    value = os.stat(path)
    # File identity also catches an atomic replacement with the same size/date.
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _inspect(path):
    import pymupdf as fitz
    from .storage import digest_file
    _check_cancelled()
    before = _file_version(path)
    digest = digest_file(path)
    with fitz.open(path) as pdf:
        metadata = dict(pdf.metadata or {})
        annotations = None if pdf.needs_pass else 0
        if not pdf.needs_pass:
            for page in pdf:
                _check_cancelled()
                annotations += sum(1 for _ in page.annots() or ())
        error = "This PDF requires a password; its annotations were not inspected." if pdf.needs_pass else ""
    if _file_version(path) != before:
        raise OSError("PDF changed during comparison; run the check again.")
    _check_cancelled()
    return digest, metadata, annotations, error


def _supplement_links(path):
    import pymupdf as fitz
    from .supplements import SUPPLEMENT
    links = []
    _check_cancelled()
    with fitz.open(path) as document:
        if document.needs_pass:
            raise ValueError("This PDF requires a password.")
        for number, page in enumerate(document, 1):
            _check_cancelled()
            for link in page.get_links():
                url = link.get("uri", "")
                if not url.startswith(("http://", "https://")):
                    continue
                rect = fitz.Rect(link["from"]) + (-25, -12, 25, 12)
                label = " ".join(page.get_textbox(rect).split())
                if SUPPLEMENT.search(url + " " + label):
                    links.append({"url": url, "label": label[:180] or "Supplementary file",
                                  "source": f"PDF page {number}"})
    return links


def _text_pages(path, expected_digest=None, start=0, stop=None):
    import pymupdf as fitz
    from .storage import digest_file
    _check_cancelled()
    version = _file_version(path)
    if expected_digest and digest_file(path) != expected_digest:
        raise ValueError("PDF changed since its last scan. Use Sync PDFs before searching it.")
    pages = []
    with fitz.open(path) as document:
        if document.needs_pass:
            raise ValueError("Password-protected PDF: save an unlocked copy to search it.")
        for index in range(start, min(stop, len(document)) if stop is not None else len(document)):
            _check_cancelled()
            page = document[index]
            pages.append({"page": index+1, "pdf_label": page.get_label() or "",
                          "text": page.get_text(sort=True)})
    if _file_version(path) != version:
        raise OSError("PDF changed during text extraction. Try again after Sync PDFs.")
    return pages


def _full_page(path, page_number):
    import pymupdf as fitz
    from .extraction import drawing_page_bounds, preview_canvas
    _check_cancelled()
    if type(page_number) is not int or page_number < 1:
        raise ValueError("Choose a physical PDF page number starting at 1.")
    version = _file_version(path)
    with fitz.open(path) as document:
        if document.needs_pass:
            raise ValueError("Password-protected PDF: save an unlocked copy to preview it.")
        if page_number > len(document):
            raise ValueError(f"PDF page {page_number} is unavailable; this file has {len(document)} pages.")
        page = document[page_number-1]
        bounds = drawing_page_bounds(page)
        display = bounds * page.rotation_matrix
        width, height = display.width, display.height
        if width <= 0 or height <= 0 or not math.isfinite(width*height):
            raise ValueError("This PDF page has invalid dimensions.")
        scale = min(2, MAX_PREVIEW_SIDE/max(width, height),
                    math.sqrt(MAX_PREVIEW_PIXELS/(width*height)))
        # Account for pixel rounding before rendering so square pages also fit
        # the memory bound. Rotation and the cropbox come from page.rect.
        for _ in range(4):
            pixels_w, pixels_h = math.ceil(width*scale), math.ceil(height*scale)
            if max(pixels_w, pixels_h) <= MAX_PREVIEW_SIDE and pixels_w*pixels_h <= MAX_PREVIEW_PIXELS:
                break
            scale *= min(MAX_PREVIEW_SIDE/max(pixels_w, pixels_h),
                         math.sqrt(MAX_PREVIEW_PIXELS/(pixels_w*pixels_h))) * .9999
        _check_cancelled()
        with preview_canvas(page, bounds) as (canvas, region):
            pixmap = canvas.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=region * canvas.rotation_matrix,
                                      colorspace=fitz.csRGB, alpha=False, annots=True)
        _check_cancelled()
        result = pixmap.tobytes("png")
    if _file_version(path) != version:
        raise OSError("PDF changed while the page preview was loading; try again.")
    _check_cancelled()
    return result


class PDFWorker:
    """Blocking API for background callers; all PDF jobs share one process.

    The process starts at the first job. Shutdown and stale individual requests
    cancel cooperatively; previews take priority over queued background work.
    Only paths, settings and bytes cross the process boundary, never PDF objects.
    """
    def __init__(self):
        self._context = multiprocessing.get_context("spawn")
        self._cancel_event = self._context.Event()
        self._job_cancel_event = self._context.Event()
        self._lock = threading.Lock()
        self._schedule = threading.Condition()
        self._waiting = []
        self._sequence = itertools.count()
        self._active = False
        self._pool = None
        self._retiring = set()
        self._closed = False
        self._shutdown_done = threading.Event()

    def _call(self, function, *args, priority=10, cancelled=None):
        ticket = (priority, next(self._sequence))
        with self._schedule:
            heapq.heappush(self._waiting, ticket)
            while self._active or self._waiting[0] != ticket:
                if self._closed or self._cancel_event.is_set() or cancelled and cancelled():
                    self._waiting.remove(ticket)
                    heapq.heapify(self._waiting)
                    self._schedule.notify_all()
                    raise InterruptedError("PDF request cancelled")
                self._schedule.wait(.05)
            heapq.heappop(self._waiting)
            self._active = True
        self._job_cancel_event.clear()
        pool = None
        try:
            with self._lock:
                if self._closed or self._cancel_event.is_set():
                    raise InterruptedError("PDF work stopped")
                if self._pool is None:
                    self._pool = ProcessPoolExecutor(max_workers=1, mp_context=self._context,
                                                    initializer=_initialize, initargs=(self._cancel_event, self._job_cancel_event))
                pool = self._pool
                future = pool.submit(function, *args)
            while True:
                if cancelled and cancelled():
                    self._job_cancel_event.set()
                try:
                    result = future.result(timeout=.05)
                    if cancelled and cancelled():
                        raise InterruptedError("PDF request cancelled")
                    return result
                except TimeoutError:
                    if future.done():
                        raise  # A PDF operation itself raised TimeoutError.
        except BrokenProcessPool:
            if pool is not None:
                self._discard_broken_pool(pool)
            # Never repeat a possibly partial operation automatically. A later
            # user request or normal scan retry will start a fresh process.
            raise
        except CancelledError as error:
            raise InterruptedError("PDF work stopped") from error
        finally:
            with self._schedule:
                self._active = False
                self._schedule.notify_all()

    def _discard_broken_pool(self, pool):
        with self._lock:
            # Another caller may already have replaced this failed pool, or
            # shutdown may own it. Never retire a newer pool by mistake.
            if self._closed or self._pool is not pool:
                return
            self._pool = None
            finished = threading.Event()
            self._retiring.add(finished)
        try:
            pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            logging.exception("Failed PDF process cleanup")
        finally:
            finished.set()
            with self._lock:
                self._retiring.discard(finished)

    def extract(self, path, settings):
        return self._call(_extract, os.fspath(path), dict(settings), priority=20)

    def text_pages(self, path, expected_digest=None):
        return self.text_pages_cancellable(path, expected_digest)

    def text_pages_cancellable(self, path, expected_digest=None, cancelled=None):
        # Yield the process between small batches so page previews do not wait
        # behind a complete book. File identity guards span every batch.
        version, pages, start = _file_version(path), [], 0
        while True:
            chunk = self._call(_text_pages, os.fspath(path), expected_digest if not start else None,
                               start, start+12, priority=15, cancelled=cancelled)
            pages.extend(chunk)
            if len(chunk) < 12:
                break
            start += 12
        if version != _file_version(path):
            raise OSError("PDF changed during indexing; sync and search again.")
        return pages

    def supplement_links(self, path):
        return self._call(_supplement_links, os.fspath(path))

    def render(self, item, bundle):
        return self._call(_render, item, dict(bundle))

    def materialize(self, library_path, reference):
        return self._call(_materialize, os.fspath(library_path), os.fspath(reference), priority=0)

    def export_combined(self, library_path, reference, target, *, expected_digest=None, require_absent=True):
        return self._call(_export_combined, os.fspath(library_path), os.fspath(reference), os.fspath(target),
                          expected_digest, require_absent)

    def render_combined(self, local_path, item, bundle):
        return self._call(_render_combined, os.fspath(local_path) if local_path is not None else None,
                          item, dict(bundle))

    def tablet_only(self, item, bundle):
        return self._call(_tablet_only, item, dict(bundle))

    def full_page(self, path, onebased_page):
        return self.full_page_cancellable(path, onebased_page)

    def full_page_cancellable(self, path, onebased_page, cancelled=None):
        return self._call(_full_page, os.fspath(path), onebased_page, priority=0, cancelled=cancelled)

    def inspect(self, path):
        return self._call(_inspect, os.fspath(path))

    def cancel(self):
        self._cancel_event.set()

    def shutdown(self, wait=True):
        with self._lock:
            first = not self._closed
            if first:
                self._closed = True
                self._cancel_event.set()
            pool = self._pool
            retiring = tuple(self._retiring)
        if not first:
            if wait:
                self._shutdown_done.wait()
            return
        def finish():
            try:
                if pool is not None:
                    pool.shutdown(wait=True, cancel_futures=True)
                for finished in retiring:
                    finished.wait()
            finally:
                self._shutdown_done.set()

        if wait or (pool is None and not retiring):
            finish()
        else:
            # A later shutdown(wait=True) still waits for actual process exit.
            threading.Thread(target=finish, name="PDF process shutdown", daemon=False).start()
