"""Check the actual offline distribution, including fresh GitHub checkouts."""
import http.client
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from note_organizer.reader_server import ReaderServer


class ReaderAssetTests(unittest.TestCase):
    def test_every_file_in_the_upstream_manifest_is_available(self):
        root = Path(__file__).resolve().parents[1] / "note_organizer/assets/pdfjs"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue({"build/pdf.mjs", "build/pdf.worker.mjs", "web/pdf_viewer.mjs"}.issubset(manifest["files"]))
        for name in manifest["files"]:
            with self.subTest(asset=name):
                path = (root / name).resolve()
                self.assertTrue(path.is_relative_to(root.resolve()))
                self.assertTrue(path.is_file(), f"Missing bundled PDF.js asset: {name}")

    def test_real_reader_modules_can_be_served_with_javascript_mime_types(self):
        server = ReaderServer()
        try:
            url = urlsplit(server.url)
            base = url.path.removesuffix("reader/index.html")
            for asset in ("reader/reader.mjs", "pdfjs/build/pdf.mjs", "pdfjs/build/pdf.worker.mjs", "pdfjs/web/pdf_viewer.mjs"):
                with self.subTest(asset=asset):
                    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
                    try:
                        connection.request("HEAD", base + asset)
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200, f"Cannot load bundled viewer module: {asset}")
                        self.assertEqual(response.getheader("Content-Type"), "text/javascript")
                        self.assertGreater(int(response.getheader("Content-Length")), 1000)
                        response.read()
                    finally:
                        connection.close()
        finally:
            server.close()
