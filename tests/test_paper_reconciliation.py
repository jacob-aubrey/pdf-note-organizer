"""Paper identities and offline suggestions preserve independent annotation work."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
import zipfile

import fitz

from note_organizer.paper_registry import Registry, annotation_identity
from note_organizer.reconciliation import scan_reconciliation, link_registry_sources
from note_organizer.storage import Store, canonical
from note_organizer.remarkable_sources import save_source_bundle


def pdf_bytes(title="Research paper", note=""):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((60, 90), "A useful research result")
        document.set_metadata({"title": title})
        if note:
            page.add_text_annot((65, 100), note)
        return document.tobytes()


class ReconciliationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.local = self.root / "Topics" / "Sorted"
        self.local.mkdir(parents=True)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.config = {"integration_enabled": True, "pc_root": str(self.local),
                       "source_folder_id": "literature", "source_folder_name": "Literature",
                       "mappings": {}, "review_dir": str(self.root / "review")}
        self.store.set_preference("remarkable_folders", [
            {"id": "literature", "name": "Literature", "parent": "", "ancestor_ids": [], "path": "/Literature"},
            {"id": "research", "name": "Research", "parent": "literature", "ancestor_ids": ["literature"], "path": "/Literature/Research"},
        ])

    def tearDown(self):
        self.temp.cleanup()

    def local_pdf(self, name, data=None):
        path = self.local / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if data is not None else pdf_bytes())
        return path

    def cloud_pdf(self, cloud_id="cloud-paper", data=None, strokes=False, name="Research paper", parent="literature"):
        self.store.save_remarkable_item(cloud_id, {"name": name, "parent": parent,
            "cloud_path": "/Literature/" + name, "state": "synced"})
        archive = self.store.path.parent / "remarkable" / "sources" / (cloud_id + ".rmdoc")
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(cloud_id + ".pdf", data if data is not None else pdf_bytes())
            if strokes:
                zipped.writestr(cloud_id + "/page.rm", b"Retained tablet stroke data")
        return archive

    def scan(self):
        return scan_reconciliation(self.store, self.config)


class ReconciliationTests(ReconciliationFixture):
    def test_scan_requires_explicit_root_and_preserves_database(self):
        self.local_pdf("paper.pdf")
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            scan_reconciliation(self.store, {})
        self.scan()
        self.assertEqual(self.store.path.read_bytes(), before)
        with self.store.connect() as db:
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='paper_registry'").fetchone())

    def test_local_exact_duplicates_do_not_merge_or_delete(self):
        first = self.local_pdf("one.pdf")
        second = self.local_pdf("Elsewhere/two.pdf", first.read_bytes())
        result = next(row for row in self.scan() if row["kind"] == "local_duplicate")
        self.assertEqual(set(result["local_paths"]), {canonical(first), canonical(second)})
        self.assertEqual(result["confidence"], "exact_bytes")
        self.assertTrue(first.exists() and second.exists())

    def test_generated_backup_and_media_folders_do_not_become_cleanup_findings(self):
        paper = self.local_pdf("Research/paper.pdf")
        snapshots = {}
        for directory in ("Notebook backups", "notes_media", ".git"):
            helper_pdf = self.local_pdf(f"Research/{directory}/Nested/paper.pdf", paper.read_bytes())
            snapshots[helper_pdf] = helper_pdf.read_bytes()
        rows = self.scan()
        self.assertFalse(any(row["kind"] == "local_duplicate" for row in rows))
        for row in rows:
            self.assertFalse(any(directory in path for directory in ("Notebook backups", "notes_media", ".git")
                                 for path in row.get("local_paths", [])))
        self.assertEqual({path: path.read_bytes() for path in snapshots}, snapshots)

    def test_original_archive_hash_matches_not_rendered_digest(self):
        original = pdf_bytes()
        local = self.local_pdf("A differently named paper.pdf", original)
        self.cloud_pdf(data=original, name="Tablet renamed this completely", strokes=True)
        rows = self.scan()
        match = next(row for row in rows if row["kind"] == "paper_match")
        self.assertEqual(match["basis"], "exact_original")
        self.assertEqual(match["local_paths"], [canonical(local)])
        self.assertEqual(match["sources"][1]["digest"], hashlib.sha256(original).hexdigest())

    def test_independently_annotated_variants_are_suggestions_and_preserved(self):
        local = self.local_pdf("PC version.pdf", pdf_bytes(note="PC note"))
        self.cloud_pdf(data=pdf_bytes(), strokes=True)
        old_bytes = local.read_bytes()
        row = next(row for row in self.scan() if row["kind"] == "annotation_variants")
        self.assertEqual(row["confidence"], "title_candidate")
        self.assertTrue(row["annotation_variants"])
        paper_id = link_registry_sources(self.store, row["sources"])
        self.assertEqual(local.read_bytes(), old_bytes)
        self.assertEqual(len(Registry(self.store).sources(paper_id)), 2)

    def test_title_matches_never_claim_exact_match(self):
        self.local_pdf("paper.pdf")
        self.cloud_pdf(data=pdf_bytes(note="Different PDF bytes"))
        row = next(row for row in self.scan() if row["kind"] == "possible_paper_match")
        self.assertEqual(row["confidence"], "title_candidate")
        self.assertIn("Review before linking", row["reason"])

    def test_local_pdf_annotation_variants_are_detected_without_cloud(self):
        self.local_pdf("paper.pdf")
        self.local_pdf("paper with comments.pdf", pdf_bytes(note="Old PC note"))
        rows = scan_reconciliation(self.store, {"integration_enabled": False}, local_root=self.local)
        row = next(row for row in rows if row["kind"] == "local_possible_variants")
        self.assertEqual(len(row["sources"]), 2)
        self.assertFalse(any(row.get("cloud_ids") for row in rows))

    def test_scope_excludes_topics_and_other_cloud_roots(self):
        data = pdf_bytes()
        self.local_pdf("one.pdf", data)
        (self.local.parent / "outside.pdf").write_bytes(data)
        self.cloud_pdf(data=data, parent="other-root")
        self.store.save_remarkable_item("cloud-paper", {"name": "Paper", "parent": "other-root", "cloud_path": "/Other/Paper"})
        rows = self.scan()
        self.assertFalse(any(row["kind"] == "local_duplicate" for row in rows))
        self.assertFalse(any(row["cloud_ids"] for row in rows))

    def test_broader_local_review_keeps_tablet_suggestions_inside_sorted(self):
        outside = self.local.parent / "outside.pdf"
        outside.write_bytes(pdf_bytes())
        self.cloud_pdf(data=outside.read_bytes())
        rows = scan_reconciliation(self.store, self.config, local_root=self.local.parent)
        self.assertFalse(any(canonical(outside) in row["local_paths"] and row["cloud_ids"] for row in rows))
        self.assertTrue(any(row["kind"] == "cloud_cached_only" for row in rows))

    def test_incomplete_cache_never_labels_tablet_paper_missing(self):
        self.local_pdf("paper.pdf")
        row = next(row for row in self.scan() if row["kind"] == "local_not_compared")
        self.assertEqual(row["confidence"], "cached_only")
        self.assertIn("does not prove", row["reason"])
        self.store.save_remarkable_item("uncached", {"name": "A different paper", "parent": "literature"})
        row = next(row for row in self.scan() if row["kind"] == "cloud_cached_only")
        self.assertIn("not been cached", row["reason"])

    def test_initial_listing_can_match_raw_hash_without_download(self):
        data = pdf_bytes()
        local = self.local_pdf("paper.pdf", data)
        self.store.set_preference("remarkable_documents", [{"id": "new-cloud", "name": "New cloud title",
            "parent": "literature", "in_scope": True, "pdf_hash": hashlib.sha256(data).hexdigest()}])
        row = next(row for row in self.scan() if row["kind"] == "paper_match")
        self.assertEqual(row["local_paths"], [canonical(local)])
        self.assertEqual(row["cloud_ids"], ["new-cloud"])

    def test_separate_baseline_and_layers_support_offline_annotation_comparison(self):
        data = pdf_bytes(note="Inherited PC note")
        local = self.local_pdf("Original.pdf", data)
        item = SimpleNamespace(id="cas-cloud", hash="a" * 64)
        save_source_bundle(self.store, item, {item.id + ".pdf": data,
            item.id + ".content": json.dumps({"fileType": "pdf", "pages": ["page"]}).encode(),
            item.id + "/page.rm": b"Retained tablet stroke data"})
        self.store.save_remarkable_item(item.id, {"name": "Research paper", "parent": "literature"})
        row = next(row for row in self.scan() if row["kind"] == "annotation_variants")
        self.assertEqual(row["basis"], "exact_original")
        self.assertEqual(row["local_paths"], [canonical(local)])
        self.assertFalse((self.store.path.parent / "remarkable" / "sources" / (item.id + ".rmdoc")).exists())

    def test_stale_archive_does_not_match_newer_catalog_hash(self):
        data = pdf_bytes("Old title")
        self.local_pdf("old.pdf", data)
        self.cloud_pdf(data=data, name="New title")
        self.store.set_preference("remarkable_documents", [{"id": "cloud-paper", "name": "New title",
            "parent": "literature", "pdf_hash": hashlib.sha256(pdf_bytes("New title")).hexdigest()}])
        rows = self.scan()
        self.assertFalse(any(row.get("basis") == "exact_original" for row in rows))

    def test_folder_name_difference_and_unmapped_folder_are_reviewed(self):
        local = self.local / "My Research"
        local.mkdir()
        self.config["mappings"] = {"research": str(local)}
        row = next(row for row in self.scan() if row["kind"] == "folder_name_difference")
        self.assertEqual(row["folder_ids"], ["research"])
        self.assertEqual(row["local_paths"], [canonical(local)])
        self.config["mappings"] = {}
        row = next(row for row in self.scan() if row["kind"] == "cloud_folder_unmapped")
        self.assertEqual(row["confidence"], "cached_only")
        self.assertTrue(local.exists())

    def test_modified_review_file_cannot_be_linked(self):
        data = pdf_bytes()
        path = self.local_pdf("paper.pdf", data)
        self.cloud_pdf(data=data)
        row = next(row for row in self.scan() if row["kind"] == "paper_match")
        path.write_bytes(pdf_bytes(note="Edited after scanning"))
        with self.assertRaisesRegex(ValueError, "changed"):
            link_registry_sources(self.store, row["sources"])
        with self.store.connect() as db:
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='paper_registry'").fetchone())

    def test_cancelled_scan_stops_without_writes(self):
        self.local_pdf("paper.pdf")
        stopped = threading.Event()
        stopped.set()
        before = self.store.path.read_bytes()
        with self.assertRaises(InterruptedError):
            scan_reconciliation(self.store, self.config, stopped)
        self.assertEqual(self.store.path.read_bytes(), before)


class RegistryTests(ReconciliationFixture):
    def test_registry_identical_copies_remain_distinct_until_confirmed(self):
        data = pdf_bytes()
        first, second = self.local_pdf("one.pdf", data), self.local_pdf("two.pdf", data)
        registry = Registry(self.store)
        a, b = registry.register_local(first), registry.register_local(second)
        self.assertNotEqual(a["paper_id"], b["paper_id"])
        self.assertNotEqual(a["id"], b["id"])
        registry.link_sources([a["id"], b["id"]])
        self.assertEqual(registry.source(a["id"])["paper_id"], registry.source(b["id"])["paper_id"])
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_source_revisions_and_project_memberships_remain_independent(self):
        path = self.local_pdf("paper.pdf")
        parent = self.store.add_project(self.local)
        child = self.store.add_project(self.local / "Another project")
        registry = Registry(self.store)
        first = registry.register_local(path, project_id=parent)
        path.write_bytes(pdf_bytes(note="New annotation"))
        second = registry.register_local(path, project_id=child)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["paper_id"], second["paper_id"])
        self.assertEqual(len(registry.revisions(first["id"])), 2)
        self.assertEqual(registry.projects(first["id"]), sorted([parent, child]))

    def test_cloud_identity_survives_rename_and_returns_known_local(self):
        registry = Registry(self.store)
        local = registry.register_local(self.local_pdf("paper.pdf"))
        cloud = registry.link_cloud(local["paper_id"], "cloud-paper", title="Old name")
        updated = registry.register_cloud("cloud-paper", title="New name", digest="new-revision")
        self.assertEqual(cloud["paper_id"], updated["paper_id"])
        self.assertEqual(registry.local_for_cloud("cloud-paper")[0]["id"], local["id"])
        rendered = self.local_pdf("tablet-render.pdf", pdf_bytes(note="Tablet note"))
        linked = registry.link_local(cloud["paper_id"], rendered, metadata={"role": "tablet_render"})
        self.assertEqual(linked["paper_id"], local["paper_id"])

    def test_linking_preserves_scanned_notes_and_history(self):
        path = self.local_pdf("paper.pdf", pdf_bytes(note="PC note"))
        project_id = self.store.add_project(self.local)
        self.store.save_scan(project_id, path, hashlib.sha256(path.read_bytes()).hexdigest(), "signature", "{}",
                             {"title": "Research paper"}, [{"key": "note-1", "comment": "Keep this PC note"}])
        with self.store.connect() as db:
            before = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
                      for table in ("documents", "entries", "history")}
        registry = Registry(self.store)
        local = registry.register_local(path)
        cloud = registry.register_cloud("independent-cloud")
        registry.link_sources([local["id"], cloud["id"]])
        with self.store.connect() as db:
            after = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
                     for table in ("documents", "entries", "history")}
        self.assertEqual(before, after)
        self.assertNotEqual(annotation_identity(local["id"], "note-1"), annotation_identity(cloud["id"], "note-1"))

    def test_existing_distinct_source_requires_confirmed_link(self):
        registry = Registry(self.store)
        a = registry.register_local(self.local_pdf("one.pdf"))
        b = registry.register_cloud("cloud-paper")
        with self.assertRaisesRegex(ValueError, "Confirm"):
            registry.link_cloud(a["paper_id"], b["cloud_id"])
        self.assertEqual(registry.source(b["id"])["paper_id"], b["paper_id"])

    def test_explicit_rename_preserves_source_identity(self):
        registry = Registry(self.store)
        old_path = self.local_pdf("paper.pdf")
        source = registry.register_local(old_path)
        new_path = self.local / "Renamed paper.pdf"
        shutil.move(str(old_path), new_path)
        moved = registry.relocate_local(source["id"], new_path)
        self.assertEqual(moved["paper_id"], source["paper_id"])
        self.assertEqual(moved["path"], canonical(new_path))
        self.assertEqual(registry.register_local(new_path)["id"], source["id"])


if __name__ == "__main__":
    unittest.main()
