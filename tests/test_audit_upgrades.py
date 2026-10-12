"""Audit fixes: recoverability, history fidelity, query parity and scheduling."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from note_organizer.storage import Store, digest_file
from note_organizer import maintenance
from note_organizer.citations import CitationConflict, citation_for, save_citation
from note_organizer.paper_registry import Registry
from note_organizer.pdf_worker import PDFWorker
from note_organizer.research_tools import save_labels, label_ids
from note_organizer.search import compile_search, normalize
from note_organizer.search_index import read as read_index
from note_organizer.supplement_library import filed, parent_details


class AuditUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.papers = self.folder / "papers"
        self.papers.mkdir()
        self.store = Store(self.folder / "data" / "library.sqlite3")
        self.project = self.store.add_project(self.papers)
        self.path = self.papers / "paper.pdf"
        import pymupdf
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 50), "A synthetic research paper")
            pdf.save(self.path)
        self.image = base64.b64encode(b"identical synthetic image bytes").decode()
        self.entry = {"key": "note", "kind": "drawing", "page": 1, "rect": [1, 2, 3, 4], "comment": "first", "image": self.image}
        self.scan()
        self.document = self.store.documents()[0]["id"]

    def tearDown(self):
        self.temporary.cleanup()

    def scan(self, entry=None):
        return self.store.save_scan(self.project, self.path, digest_file(self.path), "sig", "settings", {"title": "Synthetic"}, [entry or self.entry])

    def test_images_are_shared_without_changing_current_or_historical_payloads(self):
        self.scan({**self.entry, "comment": "second"})
        self.assertEqual(self.store.entry_image(self.document, "note"), self.image)
        self.assertEqual([json.loads(row["payload"])["image"] for row in self.store.history(self.document)], [self.image, self.image])
        self.assertTrue(all("image_ref" not in json.loads(row["payload"]) for row in self.store.history(self.document, False)))
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM note_images").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT length(data) FROM note_images").fetchone()[0], len(base64.b64decode(self.image)))
        self.assertEqual(self.scan({**self.entry, "comment": "second"}), {"added": 0, "updated": 0, "removed": 0})

    def test_compaction_migrates_old_images_after_verified_backup_and_preserves_history(self):
        with self.store.connect() as db:
            db.execute("UPDATE entries SET payload=?", (json.dumps(self.entry),))
            db.execute("UPDATE history SET payload=?", (json.dumps(self.entry),))
        before = self.store.history(self.document)
        archive = self.folder / "backup.zip"
        changed, stats = maintenance.compact(self.store, archive)
        self.assertEqual(changed, 2)
        self.assertEqual(stats["inline_images"], 0)
        self.assertEqual([json.loads(row["payload"]) for row in self.store.history(self.document)], [json.loads(row["payload"]) for row in before])
        maintenance.verify_backup(archive)
        self.assertEqual(self.store.entries()[0]["image"], self.image)

    def test_backup_restores_to_independent_paths_and_refuses_existing_folders(self):
        archive = maintenance.backup(self.store, self.folder / "backup.zip")
        original = digest_file(self.path)
        destination = maintenance.restore(archive, self.folder / "restored")
        restored = Store(destination / "library.sqlite3")
        recovered = Path(restored.documents()[0]["path"])
        self.assertTrue(recovered.is_relative_to(destination))
        self.assertEqual(digest_file(recovered), original)
        self.assertEqual(restored.entry_image(self.document, "note"), self.image)
        self.assertEqual(digest_file(self.path), original)
        with self.assertRaises(FileExistsError):
            maintenance.restore(archive, destination)
        with self.assertRaises(ValueError):
            maintenance.backup(self.store, archive)

    def test_corrupt_backup_is_rejected_before_creating_recovery_folder(self):
        archive = maintenance.backup(self.store, self.folder / "backup.zip")
        corrupt = self.folder / "corrupt.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupt, "w") as target:
            for name in source.namelist():
                target.writestr(name, b"tampered" if name == "library.sqlite3" else source.read(name))
        with self.assertRaises(ValueError):
            maintenance.restore(corrupt, self.folder / "unsafe")
        self.assertFalse((self.folder / "unsafe").exists())

    def test_backup_rejects_recovery_path_traversal(self):
        archive = maintenance.backup(self.store, self.folder / "backup.zip")
        corrupt = self.folder / "unsafe.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupt, "w") as target:
            for name in source.namelist():
                data = source.read(name)
                if name == "manifest.json":
                    manifest = json.loads(data)
                    manifest["folders"] = {"recovered-originals/../../escape": "old"}
                    data = json.dumps(manifest).encode()
                target.writestr(name, data)
        with self.assertRaises(ValueError):
            maintenance.restore(corrupt, self.folder / "unsafe")
        self.assertFalse((self.folder / "escape").exists())

    def test_conflicting_citations_require_review_and_undo_restores_each_original(self):
        other = self.papers / "copy.pdf"
        other.write_bytes(self.path.read_bytes())
        self.store.save_scan(self.project, other, digest_file(other), "sig", "settings", {}, [])
        other_id = next(row["id"] for row in self.store.documents() if row["id"] != self.document)
        first, second = {"title": "First reviewed edition"}, {"title": "Second reviewed edition"}
        save_citation(self.store, self.document, first)
        save_citation(self.store, other_id, second)
        registry = Registry(self.store)
        sources = [registry.register_local(path)["id"] for path in (self.path, other)]
        with self.assertRaises(CitationConflict):
            registry.link_sources(sources)
        registry.link_sources(sources, citation=second)
        self.assertEqual(citation_for(self.store, self.document)["title"], second["title"])
        registry.undo_latest_link()
        self.assertEqual(citation_for(self.store, self.document)["title"], first["title"])
        self.assertEqual(citation_for(self.store, other_id)["title"], second["title"])

    def test_index_candidates_preserve_boolean_phrase_short_term_and_unicode_matching(self):
        pages = [{"page": index+1, "pdf_label": str(index+11), "text": text} for index, text in enumerate(
            ["Gold  imaging\nwith iodine", "Nickel and gold imaging", "Straße and β carotene", "Cu", "A plain page"])]
        digest = digest_file(self.path)
        self.store.cache_pdf_pages(self.document, digest, "version", pages)
        for query, mode in [("gold AND imaging NOT iodine", "All words"), ("NOT gold OR nickel", "All words"),
                            ("gold imaging", "Exact phrase"), ("Cu", "All words"), ("STRASSE", "All words"), ("β carotene", "All words")]:
            with self.subTest(query=query):
                candidates, count, has_text = read_index(self.store, self.document, digest, "version", query, mode)
                matcher = compile_search(query, mode)
                self.assertEqual([page["page"] for page in candidates if matcher([normalize(page["text"])])],
                                 [page["page"] for page in pages if matcher([normalize(page["text"])])])
                self.assertEqual(count, 5)
                self.assertTrue(has_text)
        self.assertEqual(self.store.cached_pdf_pages(self.document, digest, "version"), pages)
        # Replacing an indexed paper removes its old pages without disturbing
        # another document's index, even when SQLite reuses available row IDs.
        other = self.papers / "another.pdf"
        other.write_bytes(self.path.read_bytes())
        self.store.save_scan(self.project, other, digest, "sig", "settings", {}, [])
        other_id = self.store.document_at(self.project, other)["id"]
        self.store.cache_pdf_pages(other_id, digest, "version", pages)
        replacement = [{"page": 1, "pdf_label": "", "text": "New cobalt text"}]
        self.store.cache_pdf_pages(self.document, digest, "new-version", replacement)
        self.assertEqual(self.store.cached_pdf_pages(self.document, digest, "new-version"), replacement)
        self.assertEqual(self.store.cached_pdf_pages(other_id, digest, "version"), pages)

    def test_tags_and_collections_follow_linked_paper_scope(self):
        save_labels(self.store, self.document, {"tag": "Iodine; iodine; methods", "collection": "Thesis; Experiments"})
        self.assertEqual(label_ids(self.store, "tag: IODINE"), {self.document})
        self.assertEqual(label_ids(self.store, "collection: Thesis"), {self.document})
        save_labels(self.store, self.document, {"tag": "", "collection": "Updated"})
        self.assertEqual(label_ids(self.store, "tag: iodine"), set())

    def test_supplement_hashing_occurs_outside_write_transactions(self):
        source = self.papers / "SI.pdf"
        source.write_bytes(b"synthetic supplementary data")
        details = parent_details({"title": "Synthetic", "doi": "10.1234/parent"})
        with self.store.connect() as db:
            filed(db, source, source, digest_file(source), details)
        connections, connect = [], self.store.connect
        @contextmanager
        def tracked():
            with connect() as db:
                connections.append(db)
                try:
                    yield db
                finally:
                    connections.remove(db)
        def checked(path):
            self.assertFalse(any(db.in_transaction for db in connections))
            return digest_file(path)
        with patch.object(self.store, "connect", tracked), patch("note_organizer.supplement_library.digest_file", side_effect=checked):
            save_citation(self.store, self.document, {"title": "Synthetic", "doi": "10.1234/parent"})
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM paper_attachments").fetchone()[0], 1)

    def test_accessible_view_escapes_notes_and_exposes_semantic_structure(self):
        from note_organizer.accessible_reader import render
        page = render([{**self.store.entries()[0], "comment": '<script>alert("unsafe")</script>'}])
        self.assertIn("<main>", page)
        self.assertIn("<h2", page)
        self.assertIn('aria-live="polite"', page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('<script>alert("unsafe")</script>', page)

    def test_only_byte_identical_migrated_recovery_archives_are_eligible(self):
        from note_organizer.archive_storage import plan, cleanup
        from note_organizer.remarkable_sources import save_source_bundle, source_bundle
        from tests.test_remarkable import fixture
        item, bundle = fixture()
        save_source_bundle(self.store, item, bundle)
        self.store.save_remarkable_item(item.id, {"storage_version": 2, "notes_migrated": True, "hash": item.hash})
        archive = self.store.path.parent / "remarkable" / "sources" / (item.id + ".rmdoc")
        with zipfile.ZipFile(archive, "w") as output:
            for name, data in bundle.items():
                output.writestr(name, data)
        rows = plan(self.store)
        self.assertTrue(rows[0]["ready"])
        result = cleanup(self.store, {"rows": rows, "backup": self.folder / "archive-backup.zip"})
        self.assertEqual(result["removed"], [str(archive.resolve())])
        self.assertEqual(source_bundle(self.store, item.id), bundle)
        self.assertFalse(archive.exists())
        with zipfile.ZipFile(archive, "w") as output:
            for name, data in bundle.items():
                output.writestr(name, data + b"independent" if name.endswith(".rm") else data)
        self.assertFalse(plan(self.store)[0]["ready"])


class SchedulingTests(unittest.TestCase):
    def test_preview_overtakes_queued_background_work_and_stale_requests_cancel(self):
        worker, entered, release, stale = PDFWorker(), threading.Event(), threading.Event(), threading.Event()
        order = []
        def task(name):
            order.append(name)
            if name == "active":
                entered.set()
                release.wait(5)
            return name
        # Thread executor substitutes only the process boundary, preserving the
        # real parent scheduler and real Futures with deterministic barriers.
        worker._pool = ThreadPoolExecutor(max_workers=1)
        try:
            with ThreadPoolExecutor(max_workers=4) as callers:
                active = callers.submit(worker._call, task, "active")
                self.assertTrue(entered.wait(2))
                background = callers.submit(worker._call, task, "background", priority=20)
                preview = callers.submit(worker._call, task, "preview", priority=0)
                obsolete = callers.submit(worker._call, task, "obsolete", priority=10, cancelled=stale.is_set)
                deadline = time.monotonic()+2
                while len(worker._waiting) < 3 and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertEqual(len(worker._waiting), 3)
                stale.set()
                with self.assertRaises(InterruptedError):
                    obsolete.result(timeout=2)
                release.set()
                self.assertEqual(active.result(timeout=2), "active")
                self.assertEqual(preview.result(timeout=2), "preview")
                self.assertEqual(background.result(timeout=2), "background")
                self.assertEqual(order, ["active", "preview", "background"])
        finally:
            release.set()
            worker.shutdown()
