"""Local, disposable research search/citation/download regressions."""
from io import BytesIO
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

import fitz
from PIL import Image

from note_organizer.clipboard import image_dib, copy_image
from note_organizer.citations import citation_for, save_citation, export_citations, ris, bibtex
from note_organizer.pdf_worker import _text_pages, _supplement_links
from note_organizer.paper_registry import Registry
from note_organizer.research_search import search_library
from note_organizer.research_tools import save_labels
from note_organizer.search import SearchSyntaxError
from note_organizer.storage import Store, canonical, digest_file
from note_organizer.supplements import (SupplementLinks, find_supplements, download_supplement,
                                       attach_file, attachments, public_url, PublicRedirects)
from note_organizer.sorting.metadata_lookup import DOIResolution, DOIReference


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = Store(self.folder / "library.sqlite3")
        self.project = self.store.add_project(self.folder)
        self.path = self.folder / "paper.pdf"
        self.make_pdf(self.path, ["Gold imaging is useful.", "Supplementary iodine experiments."])
        self.scan(self.path, [{"key": "note", "kind": "highlight", "page": 1,
                              "rect": [1, 2, 3, 4], "quote": "A cobalt note"}])
        self.document_id = self.store.documents()[0]["id"]
        self.worker = Mock()
        self.worker.text_pages.side_effect = _text_pages
        self.worker.supplement_links.side_effect = _supplement_links

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def make_pdf(path, texts):
        with fitz.open() as pdf:
            for text in texts:
                page = pdf.new_page()
                page.insert_text((50, 75), text)
            pdf.save(path)

    def scan(self, path, entries=()):
        self.store.save_scan(self.project, path, digest_file(path), "signature", "settings",
                             {"title": "Paper title", "pages": 2}, list(entries))

    def search(self, query, scope="All", **kwargs):
        return search_library(self.store, self.worker, scope, query=query, include_images=False, **kwargs)

    def test_all_scope_combines_note_and_unannotated_page_results(self):
        results = self.search("cobalt OR iodine")
        self.assertEqual([(entry["kind"], entry["page"]) for entry in results], [("highlight", 1), ("pdf", 2)])
        self.assertIn("iodine", results[1]["quote"])
        self.assertIn("experiments", results[1]["context"])
        self.assertEqual(self.search("iodine", "Notes"), [])
        self.assertEqual(self.search("cobalt", "PDFs"), [])

    def test_search_includes_papers_without_annotations_and_respects_paper_filter(self):
        other = self.folder / "unannotated.pdf"
        self.make_pdf(other, ["Unique nickel observation"])
        self.scan(other)
        self.assertEqual(len(self.search("nickel", "PDFs")), 1)
        self.assertEqual(self.search("nickel", "PDFs", document_id=self.document_id), [])

    def test_boolean_matching_is_per_page_and_cache_is_reused_after_reopening(self):
        self.assertEqual(self.search("gold AND iodine", "PDFs"), [])
        self.assertEqual(len(self.search('"gold imaging" NOT iodine', "PDFs")), 1)
        self.store = Store(self.store.path)
        self.assertEqual(len(self.search("iodine", "PDFs")), 1)
        self.worker.text_pages.assert_called_once()

    def test_empty_queries_browse_notes_and_one_row_per_pdf_without_reading_files(self):
        with patch("note_organizer.research_search.file_version") as version, \
             patch("note_organizer.research_search.indexed_pages") as index:
            notes = self.search("", "Notes")
            pdfs = self.search("  ", "PDFs")
            combined = self.search("")
        self.assertEqual([entry["kind"] for entry in notes], ["highlight"])
        self.assertEqual([entry["kind"] for entry in combined], ["highlight", "pdf"])
        self.assertEqual(len(pdfs), 1)
        document = pdfs[0]
        self.assertEqual(document["document_id"], self.document_id)
        self.assertEqual(document["key"], "pdf-document")
        self.assertTrue(document["pdf_document"])
        self.assertEqual(document["page"], 1)
        self.assertIsNone(document["page_count"])
        self.assertEqual(document["quote"], "")
        self.assertEqual(document["context"], "")
        self.assertEqual(self.worker.mock_calls, [])
        version.assert_not_called()
        index.assert_not_called()

    def test_invalid_query_syntax_is_checked_without_documents(self):
        with self.store.connect() as db:
            db.execute("UPDATE documents SET hidden=1")
        with self.assertRaises(SearchSyntaxError):
            self.search("gold AND", "PDFs")

    def test_empty_pdf_browsing_obeys_paper_folder_and_label_filters(self):
        other = self.folder / "unannotated.pdf"
        self.make_pdf(other, ["Different text"])
        self.scan(other)
        other_id = self.store.document_at(self.project, other)["id"]
        other_folder = self.folder / "second-folder"
        other_folder.mkdir()
        other_project = self.store.add_project(other_folder)
        third = other_folder / "third.pdf"
        self.store.save_scan(other_project, third, "third-digest", "sig", "settings", {}, [])
        save_labels(self.store, other_id, {"tag": "Relevant"})
        self.assertEqual({entry["document_id"] for entry in self.search("", "PDFs")},
                         {self.document_id, other_id, self.store.document_at(other_project, third)["id"]})
        self.assertEqual({entry["document_id"] for entry in self.search("", "PDFs", project_id=self.project)},
                         {self.document_id, other_id})
        self.assertEqual([entry["document_id"] for entry in self.search("", "PDFs", document_id=other_id)],
                         [other_id])
        self.assertEqual([entry["document_id"] for entry in self.search("", "All", label_filter="tag: Relevant")],
                         [other_id])
        self.assertEqual(self.search("", "PDFs", label_filter="tag: Missing"), [])
        self.assertEqual(self.worker.mock_calls, [])

    def test_empty_browsing_keeps_missing_pdfs_and_incomplete_metadata(self):
        self.path.unlink()
        self.store.mark_missing(self.project, set())
        with self.store.connect() as db:
            db.execute("UPDATE documents SET metadata='{}'")
        result = self.search("", "PDFs")
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["missing"])
        self.assertEqual(result[0]["metadata"], {})
        self.assertEqual(result[0]["path"], canonical(self.path))
        self.assertFalse(result.warnings)
        self.assertEqual(self.worker.mock_calls, [])

    def test_pdf_browsing_deduplicates_overlapping_folders_but_keeps_independent_copies(self):
        overlapping = self.store.add_project(self.folder.parent)
        self.store.save_scan(overlapping, self.path, digest_file(self.path), "sig", "settings", {}, [])
        copy = self.folder / "copy.pdf"
        copy.write_bytes(self.path.read_bytes())
        self.scan(copy)
        pdfs = self.search("", "PDFs")
        self.assertEqual({entry["path"] for entry in pdfs},
                         {canonical(self.path), canonical(copy)})
        self.assertEqual(len(pdfs), 2)

    def test_empty_browsing_does_not_fetch_managed_tablet_documents(self):
        managed = self.folder / "managed.pdf"
        standalone = self.folder / "standalone.pdf"
        self.store.save_scan(self.project, managed, "managed-digest", "sig", "settings",
                             {"managed_cloud_id": "managed-cloud", "primary_path": canonical(self.path)}, [])
        self.store.save_scan(self.project, standalone, "standalone-digest", "sig", "settings",
                             {"managed_cloud_id": "standalone-cloud"}, [])
        pdfs = self.search("", "PDFs")
        self.assertEqual({entry["path"] for entry in pdfs},
                         {canonical(self.path), canonical(standalone)})
        self.assertEqual(len(pdfs), 2)
        self.assertEqual(self.worker.mock_calls, [])

    def test_pdf_browsing_and_page_search_reuse_reviewed_citation_metadata(self):
        save_citation(self.store, self.document_id,
                      {"title": "Reviewed paper", "authors": "Doe, Jane", "year": "2025", "pages": "12-19"})
        for query in ("", "gold"):
            with self.subTest(query=query):
                metadata = self.search(query, "PDFs")[0]["metadata"]
                self.assertEqual(metadata["title"], "Reviewed paper")
                self.assertEqual(metadata["authors"], ["Doe, Jane"])
                self.assertEqual(metadata["author"], "Doe, Jane")
                self.assertEqual(metadata["year"], "2025")
                self.assertEqual(metadata["pages"], 2)
                self.assertEqual(metadata["citation_pages"], "12-19")

    def test_empty_browsing_honors_cancellation_after_reading_catalog(self):
        cancelled = [False]
        original = self.store.search_documents
        def documents(*args, **kwargs):
            result = original(*args, **kwargs)
            cancelled[0] = True
            return result
        with patch.object(self.store, "search_documents", side_effect=documents), \
             self.assertRaises(InterruptedError):
            self.search("", "PDFs", cancelled=lambda: cancelled[0])
        self.assertEqual(self.worker.mock_calls, [])

    def test_changed_pdf_is_reported_until_rescanned_then_cache_refreshes(self):
        self.search("gold", "PDFs")
        self.path.unlink()
        self.make_pdf(self.path, ["A zinc replacement"])
        stale = self.search("zinc", "PDFs")
        self.assertFalse(stale)
        self.assertIn("Sync PDFs", stale.warnings[0])
        self.scan(self.path)
        self.assertEqual(len(self.search("zinc", "PDFs")), 1)
        self.assertEqual(self.search("gold", "PDFs"), [])

    def test_missing_pdf_does_not_remove_saved_note_results(self):
        self.path.unlink()
        results = self.search("cobalt OR gold")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["kind"], "highlight")
        self.assertEqual(len(results.warnings), 1)

    def test_cancelled_query_does_not_cache_or_return_partial_results(self):
        with self.assertRaises(InterruptedError):
            self.search("gold", "PDFs", cancelled=lambda: True)
        self.worker.text_pages.assert_not_called()

    def test_citation_edits_survive_rescan_and_are_searchable(self):
        self.assertEqual(citation_for(self.store, self.document_id)["pages"], "")
        record = {"title": "Reviewed citation", "authors": "Doe, Jane; Müller, A.",
                  "year": "2025", "journal": "Research", "doi": "https://doi.org/10.1234/test", "pages": "12-19"}
        save_citation(self.store, self.document_id, record)
        self.scan(self.path)
        self.assertEqual(citation_for(Store(self.store.path), self.document_id)["authors"], ["Doe, Jane", "Müller, A."])
        self.assertEqual(citation_for(self.store, self.document_id)["pages"], "12-19")
        # Restore an annotation to check the existing note search fields.
        self.scan(self.path, [{"key": "note", "kind": "highlight", "page": 1, "rect": [0, 0, 1, 1], "quote": "text"}])
        self.assertEqual(len(self.store.entries(query="Reviewed AND Müller")), 1)
        metadata = self.store.entries()[0]["metadata"]
        self.assertEqual(metadata["pages"], 2)
        self.assertEqual(metadata["citation_pages"], "12-19")

    def test_exports_unicode_and_escapes_format_control_characters(self):
        record = {"title": "A {study} & 50% result\nER  - injected", "authors": ["Müller, Jane", "Li, A."],
                  "year": "2025", "journal": "Research", "pages": "12–19", "doi": "10.1234/test"}
        text = ris([record])
        self.assertEqual(text.count("\nER  - "), 1)
        self.assertIn("AU  - Müller, Jane", text)
        self.assertIn("SP  - 12\nEP  - 19", text)
        tex = bibtex([record])
        self.assertIn(r"\{study\} \& 50\%", tex)
        self.assertIn("Müller, Jane and Li, A.", tex)
        save_citation(self.store, self.document_id, record)
        target = self.folder / "citations.ris"
        self.assertEqual(export_citations(self.store, [self.document_id, self.document_id], target), 1)
        self.assertIn("Müller", target.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            export_citations(self.store, [self.document_id], self.path)

    def test_attachments_persist_and_rescans_do_not_replace_them(self):
        supplementary = self.folder / "supplement.txt"
        supplementary.write_text("data", encoding="utf-8")
        attach_file(self.store, self.document_id, supplementary, "https://example.org/si.txt")
        self.scan(self.path)
        self.assertEqual(attachments(Store(self.store.path), self.document_id),
                         [{"path": str(supplementary.resolve()), "url": "https://example.org/si.txt"}])

    def test_linked_variants_share_citations_and_export_once(self):
        variant = self.folder / "variant.pdf"
        self.make_pdf(variant, ["Independent edition"])
        self.scan(variant)
        variant_id = self.store.document_at(self.project, variant)["id"]
        registry = Registry(self.store)
        primary = registry.register_local(self.path)
        registry.link_local(primary["paper_id"], variant)
        save_citation(self.store, variant_id, {"title": "Shared citation", "authors": "Doe, Jane"})
        self.assertEqual(citation_for(self.store, self.document_id)["title"], "Shared citation")
        target = self.folder / "linked.bib"
        self.assertEqual(export_citations(self.store, [self.document_id, variant_id], target), 1)
        for query in ("", "gold OR edition"):
            results = self.search(query, "PDFs", document_id=self.document_id)
            self.assertEqual(len(results), 2)
            self.assertEqual({entry["result_paper_id"] for entry in results}, {primary["paper_id"]})
            # Grouping identity must not redirect independently paginated
            # source PDFs through the combined notebook's page mapping.
            self.assertTrue(all(entry["logical_paper_id"] is None for entry in results))

    def test_overlapping_watched_folders_share_metadata_without_duplicate_exports(self):
        overlapping = self.store.add_project(self.folder.parent)
        self.store.save_scan(overlapping, self.path, digest_file(self.path), "sig", "settings", {}, [])
        duplicate_id = self.store.document_at(overlapping, self.path)["id"]
        save_citation(self.store, duplicate_id, {"title": "One paper in two folders"})
        self.assertEqual(citation_for(self.store, self.document_id)["title"], "One paper in two folders")
        self.assertEqual(export_citations(self.store, [self.document_id, duplicate_id], self.folder / "overlap.ris"), 1)

    def test_image_only_pdf_has_explicit_search_issue(self):
        self.path.unlink()
        with fitz.open() as pdf:
            pdf.new_page()
            pdf.save(self.path)
        self.scan(self.path)
        result = self.search("NOT gold", "PDFs")
        self.assertFalse(result)
        self.assertIn("No searchable text layer", result.warnings[0])

    def test_pdf_hyperlink_is_identified_as_supporting_information(self):
        self.path.unlink()
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 75), "Supporting information")
            page.insert_link({"kind": fitz.LINK_URI, "from": page.search_for("Supporting information")[0],
                              "uri": "https://example.org/supplement.pdf"})
            pdf.save(self.path)
        self.assertEqual(_supplement_links(self.path)[0]["url"], "https://example.org/supplement.pdf")

    def test_discovery_combines_explicit_links_and_deduplicates(self):
        save_citation(self.store, self.document_id, {"title": "Study", "doi": "10.1234/test"})
        resolution = DOIResolution(doi="10.1234/test", provider="Crossref", evidence_label="DOI lookup",
                                   url="https://example.org/article", relations=(
                                       DOIReference("is_supplemented_by", "10.1234/si", "doi"),
                                       DOIReference("is_supplement_to", "10.1234/parent", "doi")))
        response = Mock()
        response.headers = {"Content-Type": "text/html"}
        response.geturl.return_value = "https://example.org/article"
        response.read.return_value = b'<a href="/supporting.pdf">Supporting information</a><a href="/supporting.pdf">SI</a>'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("note_organizer.supplements.resolve_doi", return_value=resolution), \
             patch("note_organizer.supplements.open_url", return_value=response):
            links, warnings, landing = find_supplements(self.store, self.worker, self.document_id)
        self.assertFalse(warnings)
        self.assertEqual(len(links), 2)
        self.assertEqual(landing, "https://example.org/article")
        self.assertNotIn("parent", " ".join(link["url"] for link in links))

    def test_non_web_citation_url_is_not_used_for_article_navigation(self):
        save_citation(self.store, self.document_id, {"title": "Study", "url": "file:///C:/private.txt"})
        with patch("note_organizer.supplements.open_url") as request:
            links, warnings, landing = find_supplements(self.store, self.worker, self.document_id)
        request.assert_not_called()
        self.assertEqual(landing, "")
        self.assertIn("HTTP/HTTPS", warnings[0])

    def test_author_separator_preserves_organization_names(self):
        record = save_citation(self.store, self.document_id,
                               {"title": "Study", "authors": "Research and Development Group; Doe, Jane"})
        self.assertEqual(record["authors"], ["Research and Development Group", "Doe, Jane"])
        self.assertIn("{Research and Development Group} and Doe, Jane", bibtex([record]))


class DownloadTests(unittest.TestCase):
    def response(self, body, content_type="application/pdf"):
        response = BytesIO(body)
        response.headers = {"Content-Type": content_type}
        return response

    def test_download_publishes_complete_file_and_keeps_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "si.pdf"
            with patch("note_organizer.supplements.open_url", return_value=self.response(b"%PDF-1.7\nsynthetic")):
                self.assertEqual(download_supplement("https://example.org/si.pdf", path), path)
            with self.assertRaises(FileExistsError):
                download_supplement("https://example.org/si.pdf", path)
            self.assertEqual(path.read_bytes(), b"%PDF-1.7\nsynthetic")
            self.assertEqual(list(Path(folder).glob(".notable-si-*")), [])

    def test_html_wrong_format_and_cancelled_downloads_never_publish(self):
        for body, kind, cancelled in [(b"<html>Log in</html>", "text/html", lambda: False),
                                       (b"not a PDF", "application/pdf", lambda: False),
                                       (b"%PDF-1.7", "application/pdf", lambda: True)]:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "si.pdf"
                with patch("note_organizer.supplements.open_url", return_value=self.response(body, kind)), \
                     self.assertRaises((ValueError, InterruptedError)):
                    download_supplement("https://example.org/si.pdf", path, cancelled)
                self.assertFalse(path.exists())
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_non_http_and_private_addresses_are_rejected(self):
        for url in ("file:///C:/private.txt", "https://user:password@example.org/si.pdf"):
            with self.assertRaises(ValueError):
                public_url(url)
        with patch("note_organizer.supplements.socket.getaddrinfo", return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]), self.assertRaises(ValueError):
            public_url("https://localhost/si.pdf")

    def test_parser_resolves_relative_links_and_ignores_unrelated_links(self):
        parser = SupplementLinks("https://example.org/article/")
        parser.feed('<a href="../si.pdf">Supporting <b>information</b></a>'
                    '<a href="/article.pdf">Main paper</a><a href="javascript:alert(1)">Supplement</a>')
        self.assertEqual([link["url"] for link in parser.links], ["https://example.org/si.pdf"])


class ClipboardDataTests(unittest.TestCase):
    def test_native_clipboard_transfers_memory_ownership_only_on_success(self):
        for accepted in (True, False):
            user, kernel = Mock(), Mock()
            user.OpenClipboard.return_value = accepted
            user.EmptyClipboard.return_value = True
            user.SetClipboardData.return_value = 123
            kernel.GlobalAlloc.return_value = 123
            kernel.GlobalLock.return_value = 456
            with self.subTest(accepted=accepted), patch("note_organizer.clipboard.sys.platform", "win32"), \
                 patch("note_organizer.clipboard.ctypes.WinDLL", side_effect=[user, kernel], create=True), \
                 patch("note_organizer.clipboard.ctypes.memmove") as memmove:
                image = Image.new("RGB", (3, 2), "blue")
                if accepted:
                    copy_image(image, 99)
                    user.SetClipboardData.assert_called_once_with(8, 123)
                    kernel.GlobalFree.assert_not_called()
                    user.CloseClipboard.assert_called_once()
                else:
                    with self.assertRaises(OSError):
                        copy_image(image, 99)
                    kernel.GlobalFree.assert_called_once_with(123)
                    user.SetClipboardData.assert_not_called()
                    user.CloseClipboard.assert_not_called()
                memmove.assert_called_once_with(456, image_dib(image), len(image_dib(image)))

    def test_original_pixels_dimensions_and_white_alpha_background(self):
        source = Image.new("RGBA", (37, 19), (255, 0, 0, 0))
        source.putpixel((1, 1), (0, 0, 255, 255))
        dib = image_dib(source)
        # Pillow can read a standalone DIB directly.
        with Image.open(BytesIO(dib)) as decoded:
            self.assertEqual(decoded.size, source.size)
            self.assertEqual(decoded.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(decoded.getpixel((1, 1)), (0, 0, 255))


if __name__ == "__main__":
    unittest.main()
