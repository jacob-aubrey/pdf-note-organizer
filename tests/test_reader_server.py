"""The embedded reader may access only its current, unchanged local PDF."""
import http.client
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from note_organizer.reader_server import ReaderServer


class ReaderServerTests(unittest.TestCase):
    def test_browser_shutdown_may_abort_an_inflight_asset_request(self):
        handler = Mock()
        handler.path = urlsplit(self.server.url).path
        handler.headers = {"Host": urlsplit(self.server.origin).netloc}
        handler.close_connection = False
        with patch.object(self.server, "_serve_file", side_effect=ConnectionAbortedError("browser closed")):
            self.server._serve(handler, head=False)
        self.assertTrue(handler.close_connection)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.assets = self.folder / "assets"
        (self.assets / "reader").mkdir(parents=True)
        (self.assets / "pdfjs" / "build").mkdir(parents=True)
        (self.assets / "reader" / "index.html").write_text("<!doctype html><title>Reader</title>", encoding="utf-8")
        (self.assets / "pdfjs" / "build" / "pdf.mjs").write_text("export const version = 'test';", encoding="utf-8")
        (self.assets / "pdfjs" / "test.wasm").write_bytes(b"\0asm")
        self.pdf = self.folder / "Private paper #1.pdf"
        self.content = b"%PDF-1.7\n" + bytes(range(256)) * 600
        self.pdf.write_bytes(self.content)
        self.server = ReaderServer(assets_root=self.assets)

    def tearDown(self):
        self.server.close()
        self.temp.cleanup()

    def request(self, url, *, method="GET", headers=None, host=None):
        parsed = urlsplit(url)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
        try:
            connection.putrequest(method, parsed.path + ("?" + parsed.query if parsed.query else ""),
                                  skip_host=host is not None)
            if host is not None:
                connection.putheader("Host", host)
            for key, value in (headers or {}).items():
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def route(self, suffix):
        return self.server.url.rsplit("reader/index.html", 1)[0] + suffix

    def test_assets_are_token_scoped_and_have_required_browser_mime_types(self):
        status, headers, body = self.request(self.server.url)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Reader</title>", body)
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        for suffix, mime in (("pdfjs/build/pdf.mjs", "text/javascript"),
                             ("pdfjs/test.wasm", "application/wasm")):
            with self.subTest(suffix=suffix):
                status, headers, _ = self.request(self.route(suffix))
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], mime)
        self.assertEqual(self.request(self.server.origin + "/reader/index.html")[0], 404)

    def test_host_origin_and_cross_site_requests_are_rejected(self):
        for options in ({"host": "evil.example"},
                        {"host": "localhost:" + str(urlsplit(self.server.url).port)},
                        {"headers": {"Origin": "https://evil.example"}},
                        {"headers": {"Origin": "null"}},
                        {"headers": {"Sec-Fetch-Site": "cross-site"}}):
            with self.subTest(options=options):
                self.assertEqual(self.request(self.server.url, **options)[0], 403)
        self.assertEqual(self.request(self.server.url, headers={"Origin": self.server.origin})[0], 200)

    def test_no_directory_listing_traversal_or_arbitrary_file_route(self):
        (self.folder / "secret.txt").write_text("Never serve this", encoding="utf-8")
        for suffix in ("reader", "reader/", "pdfjs/", "reader/../secret.txt",
                       "reader/%2e%2e/%2e%2e/secret.txt", "reader/%5c..%5csecret.txt",
                       "reader/%00index.html", "reader/C:%5csecret.txt", "secret.txt",
                       "documents/anything.pdf", "reader//index.html"):
            with self.subTest(suffix=suffix):
                status, _, body = self.request(self.route(suffix))
                self.assertEqual(status, 404)
                self.assertNotIn(b"Never serve this", body)

    def test_only_registered_pdf_is_readable_and_urls_hide_original_filename(self):
        url = self.server.register_document(self.pdf)
        self.assertNotIn("Private", url)
        self.assertNotIn(str(self.folder), url)
        status, headers, body = self.request(url)
        self.assertEqual(status, 200)
        self.assertEqual(body, self.content)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(int(headers["Content-Length"]), len(self.content))
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_pdf_single_ranges_and_head_match_http_byte_semantics(self):
        url = self.server.register_document(self.pdf)
        size = len(self.content)
        for value, start, end in (("bytes=1-8", 1, 8), ("bytes=20-", 20, size - 1),
                                  ("bytes=-11", size - 11, size - 1),
                                  (f"bytes={size - 5}-{size + 80}", size - 5, size - 1),
                                  (f"bytes=-{size + 80}", 0, size - 1)):
            with self.subTest(value=value):
                status, headers, body = self.request(url, headers={"Range": value})
                self.assertEqual(status, 206)
                self.assertEqual(body, self.content[start:end + 1])
                self.assertEqual(headers["Content-Range"], f"bytes {start}-{end}/{size}")
                self.assertEqual(int(headers["Content-Length"]), end - start + 1)
                status, head_headers, body = self.request(url, method="HEAD", headers={"Range": value})
                self.assertEqual(status, 206)
                self.assertEqual(body, b"")
                self.assertEqual(head_headers["Content-Range"], headers["Content-Range"])
                self.assertEqual(head_headers["Content-Length"], headers["Content-Length"])
        status, headers, body = self.request(url, method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(int(headers["Content-Length"]), size)

    def test_unsatisfiable_or_multiple_ranges_return_416_without_content(self):
        url = self.server.register_document(self.pdf)
        for value in ("bytes=", "bytes=-", "bytes=-0", "bytes=10-5", "bytes=0-1,2-3",
                      "bytes=99999999-", "bytes=" + "9" * 100 + "-", "items=0-4"):
            with self.subTest(value=value):
                status, headers, body = self.request(url, headers={"Range": value})
                self.assertEqual((status, body), (416, b""))
                self.assertEqual(headers["Content-Range"], f"bytes */{len(self.content)}")

    def test_register_replacement_and_clear_revoke_previous_pdf_urls(self):
        old_url = self.server.register_document(self.pdf)
        other = self.folder / "Another.pdf"
        other.write_bytes(b"%PDF-1.7\nDifferent paper")
        new_url = self.server.register_document(other)
        self.assertNotEqual(old_url, new_url)
        self.assertEqual(self.request(old_url)[0], 404)
        self.assertEqual(self.request(new_url)[2], other.read_bytes())
        self.server.clear_document()
        self.assertEqual(self.request(new_url)[0], 404)
        self.assertEqual(self.request(self.server.url)[0], 200)

    def test_changed_pdf_is_rejected_and_reregistering_accepts_new_version(self):
        old_url = self.server.register_document(self.pdf)
        original_stat = self.pdf.stat()
        changed = b"%PDF-1.7\nEdited contents"
        self.pdf.write_bytes(changed)
        os.utime(self.pdf, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000))
        self.assertEqual(self.request(old_url)[0], 409)
        self.assertEqual(self.request(old_url, method="HEAD")[0], 409)
        new_url = self.server.register_document(self.pdf)
        self.assertEqual(self.request(new_url)[2], changed)
        self.assertEqual(self.request(old_url)[0], 404)

    def test_atomic_file_replacement_and_missing_file_are_not_silently_read(self):
        url = self.server.register_document(self.pdf)
        replacement = self.folder / "replacement.pdf"
        replacement.write_bytes(self.content)
        replacement.replace(self.pdf)
        self.assertEqual(self.request(url)[0], 409)
        self.pdf.unlink()
        self.assertEqual(self.request(url)[0], 404)

    def test_close_is_idempotent_and_stops_listener(self):
        self.server.close()
        self.server.close()
        self.assertFalse(self.server._thread.is_alive())
        with self.assertRaises((ConnectionError, OSError)):
            self.request(self.server.url)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.server.register_document(self.pdf)


if __name__ == "__main__":
    unittest.main()
