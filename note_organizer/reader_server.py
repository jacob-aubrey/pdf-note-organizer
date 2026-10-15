"""Serve the local reader and its one selected PDF to an embedded browser.

Nothing leaves the computer. The listener is loopback-only, every route needs
an unguessable session token, and a PDF URL never contains a filesystem path.
"""
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import re
import secrets
import stat
import threading
from urllib.parse import unquote, urlsplit


_CHUNK_SIZE = 64 * 1024
_RANGE = re.compile(r"bytes=(\d{0,20})-(\d{0,20})", re.IGNORECASE)
_MIME = {".mjs": "text/javascript", ".js": "text/javascript",
         ".wasm": "application/wasm", ".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json"}


def _version(info):
    # Windows stat()/fstat() can disagree about the deprecated ctime field.
    # File identity plus size and nanosecond modification time remain stable
    # between those APIs and also detect atomic replacements.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


@dataclass(frozen=True)
class _Document:
    identifier: str
    path: Path
    version: tuple


class _LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address


class ReaderServer:
    """Own a small HTTP session for trusted, bundled reader assets.

    ``register_document`` replaces the readable PDF, invalidating all previous
    document URLs. Call ``close`` when the reader/app closes. All public methods
    may be used from background preparation threads.
    """
    def __init__(self, *, assets_root=None):
        self.assets_root = Path(assets_root or Path(__file__).with_name("assets")).resolve()
        self._lock = threading.RLock()
        self._closed = False
        self._document = None
        self._prefix = "/" + secrets.token_urlsafe(32) + "/"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                owner._serve(self, head=False)

            def do_HEAD(self):
                owner._serve(self, head=True)

            def log_message(self, format, *args):
                # Neither session tokens nor selected source paths go to logs.
                pass

        self._server = _LocalServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self._server.server_port}"
        self.url = self.origin + self._prefix + "reader/index.html"
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": .1},
                                        name="Local PDF reader", daemon=True)
        self._thread.start()

    def register_document(self, path):
        path = Path(path).resolve(strict=True)
        with path.open("rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Choose a regular PDF file to read.")
            document = _Document(secrets.token_urlsafe(24), path, _version(info))
        with self._lock:
            if self._closed:
                raise RuntimeError("The PDF reader is closed.")
            self._document = document
        return self.origin + self._prefix + "documents/" + document.identifier + ".pdf"

    def clear_document(self):
        """Revoke PDF access while retaining the loaded reader interface."""
        with self._lock:
            self._document = None

    def _current_document(self, document, source):
        with self._lock:
            if self._closed or self._document is not document:
                return False
        try:
            return (_version(os.fstat(source.fileno())) == document.version
                    and _version(document.path.stat()) == document.version)
        except OSError:
            return False

    def _headers(self, handler, status, length, content_type=None, *, document=False,
                 content_range=None):
        handler.send_response(status)
        handler.send_header("Content-Length", str(length))
        if content_type:
            handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store" if document else "private, max-age=3600")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Connection", "close")
        if document:
            handler.send_header("Accept-Ranges", "bytes")
        if content_range:
            handler.send_header("Content-Range", content_range)
        handler.end_headers()
        handler.close_connection = True

    def _error(self, handler, status, *, size=None):
        self._headers(handler, status, 0, document=True,
                      content_range=f"bytes */{size}" if size is not None else None)

    def _serve(self, handler, *, head):
        try:
            if handler.headers.get("Host", "") != self.origin.removeprefix("http://"):
                self._error(handler, 403)
                return
            origin = handler.headers.get("Origin")
            if origin is not None and origin != self.origin:
                self._error(handler, 403)
                return
            if handler.headers.get("Sec-Fetch-Site", "").casefold() == "cross-site":
                self._error(handler, 403)
                return
            with self._lock:
                if self._closed:
                    self._error(handler, 503)
                    return
            parsed = urlsplit(handler.path)
            if parsed.scheme or parsed.netloc:
                self._error(handler, 404)
                return
            path = unquote(parsed.path, errors="strict")
            if not path.startswith(self._prefix) or any(char in path for char in ("\\", "\0", ":")):
                self._error(handler, 404)
                return
            parts = path[len(self._prefix):].split("/")
            if not parts or any(part in {"", ".", ".."} for part in parts):
                self._error(handler, 404)
                return
            if parts[0] == "documents":
                with self._lock:
                    document = self._document
                if document is None or parts != ["documents", document.identifier + ".pdf"]:
                    self._error(handler, 404)
                    return
                self._serve_file(handler, document.path, head=head, document=document)
                return
            if parts[0] not in {"reader", "pdfjs"}:
                self._error(handler, 404)
                return
            target = self.assets_root.joinpath(*parts).resolve()
            if not target.is_relative_to(self.assets_root) or not target.is_file():
                self._error(handler, 404)
                return
            self._serve_file(handler, target, head=head)
        except (UnicodeError, ValueError):
            self._error(handler, 404)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            handler.close_connection = True

    @staticmethod
    def _range(value, size):
        match = _RANGE.fullmatch(value.strip())
        if not match or not size or not any(match.groups()):
            raise ValueError("Unsatisfiable byte range")
        first, last = match.groups()
        if not first:
            count = int(last)
            if count <= 0:
                raise ValueError("Unsatisfiable byte range")
            return max(0, size - count), size - 1
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
        if start >= size or end < start:
            raise ValueError("Unsatisfiable byte range")
        return start, end

    def _serve_file(self, handler, path, *, head, document=None):
        try:
            source = path.open("rb")
        except OSError:
            self._error(handler, 404)
            return
        with source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode):
                self._error(handler, 404)
                return
            if document:
                with self._lock:
                    current = not self._closed and self._document is document
                if not current:
                    self._error(handler, 404)
                    return
                if not self._current_document(document, source):
                    self._error(handler, 409)
                    return
            size = info.st_size
            start, end, status = 0, size - 1, 200
            requested = handler.headers.get("Range")
            if requested:
                try:
                    start, end = self._range(requested, size)
                    status = 206
                except ValueError:
                    self._error(handler, 416, size=size)
                    return
            content_type = "application/pdf" if document else (
                _MIME.get(path.suffix.casefold()) or mimetypes.guess_type(path.name)[0]
                or "application/octet-stream")
            length = max(0, end - start + 1)
            self._headers(handler, status, length, content_type, document=bool(document),
                          content_range=f"bytes {start}-{end}/{size}" if status == 206 else None)
            if head:
                return
            source.seek(start)
            remaining = length
            while remaining:
                if document:
                    if not self._current_document(document, source):
                        handler.close_connection = True
                        return
                chunk = source.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    handler.close_connection = True
                    return
                handler.wfile.write(chunk)
                remaining -= len(chunk)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._document = None
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
