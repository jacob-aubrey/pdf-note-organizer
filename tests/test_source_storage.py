"""Reviewed cleanup preserves originals, tablet layers and saved note history."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE

from note_organizer.paper_registry import Registry
from note_organizer.remarkable_pdf import annotated_pdf
from note_organizer.remarkable_sources import save_source_bundle, source_bundle, source_info
from note_organizer.source_storage import plan_legacy_cleanup, execute_legacy_cleanup
from note_organizer.storage import Store, canonical, digest_file
from tests.test_remarkable import fixture


class LegacyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.library = self.root / "Research library"
        self.library.mkdir()
        self.project_id = self.store.add_project(self.library)
        self.item, self.bundle = fixture()
        self.manifest = save_source_bundle(self.store, self.item, self.bundle)
        self.main = self.library / "Paper.pdf"
        self.main.write_bytes(self.bundle[self.item.id + ".pdf"])
        self.legacy = self.library / f"Paper [reMarkable {self.item.id[:8]}].pdf"
        self.legacy.write_bytes(annotated_pdf(self.item, self.bundle))
        self.registry = Registry(self.store)
        self.cloud = self.registry.register_cloud(self.item.id, digest=digest_file(self.main))
        self.registry.link_local(self.cloud["paper_id"], self.main)
        self.render = self.registry.link_local(self.cloud["paper_id"], self.legacy, metadata={
            "role": "tablet_render", "cloud_id": self.item.id, "page_mapping_identity": True})
        self.entry = {"key": "0:tablet-note", "kind": "text", "page": 1, "rect": [10, 10, 20, 20],
                      "comment": "Preserve my tablet note", "image": ""}
        self.store.save_scan(self.project_id, self.legacy, digest_file(self.legacy), "signature", "{}",
                             {"title": "Research paper"}, [self.entry])
        self.document_id = self.store.document_at(self.project_id, self.legacy)["id"]
        self.anchor = self.store.path.parent / "remarkable" / "documents" / (self.item.id + ".pdf")
        self.registry.relocate_local(self.render["id"], self.anchor)
        with self.store.connect() as db:
            db.execute("UPDATE documents SET path=?,metadata=? WHERE id=?", (canonical(self.anchor), json.dumps({
                "managed_cloud_id": self.item.id, "primary_path": canonical(self.main),
                "logical_folder": canonical(self.library)}), self.document_id))
        self.payload = {"storage_version": 2, "notes_migrated": True, "state": "synced", "name": "Paper",
                        "path": canonical(self.main), "digest": digest_file(self.main),
                        "main_path": canonical(self.main), "main_digest": digest_file(self.main),
                        "original_pdf_digest": self.manifest["pdf_hash"], "hash": self.item.hash,
                        "legacy_path": canonical(self.legacy), "legacy_digest": digest_file(self.legacy),
                        "legacy_cloud_hash": self.item.hash, "legacy_document_ids": [self.document_id]}
        self.store.save_remarkable_item(self.item.id, self.payload)
        self.output = Path(self.store.project(self.project_id)["output"])
        self.save_notebook()

    def tearDown(self):
        self.temporary.cleanup()

    def save_notebook(self, link=None):
        notebook = Document()
        notebook.add_paragraph("Saved research notes")
        if link:
            notebook.part.relate_to(link, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        notebook.save(self.output)
        self.store.export_result(self.project_id, digest_file(self.output))

    def plan(self):
        return plan_legacy_cleanup(self.store)[0]

    def saved_note_rows(self):
        with self.store.connect() as db:
            return {name: [tuple(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY 1")]
                    for name in ("documents", "entries", "history", "paper_sources", "paper_document_sources")}

    def save_new_revision(self, *, change_baseline=False):
        bundle = dict(self.bundle)
        content = json.loads(bundle[self.item.id + ".content"])
        content["lastOpenedPage"] = 1
        bundle[self.item.id + ".content"] = json.dumps(content).encode()
        if change_baseline:
            bundle[self.item.id + ".pdf"] += b"\nChanged original PDF"
        item = replace(self.item, hash=hashlib.sha256(b"".join(bundle.values())).hexdigest())
        manifest = save_source_bundle(self.store, item, bundle)
        self.payload["hash"] = item.hash
        self.payload["original_pdf_digest"] = manifest["pdf_hash"]
        self.store.save_remarkable_item(self.item.id, self.payload)
        return item, bundle, manifest

    def test_planning_is_read_only_and_reports_real_reclaimable_bytes(self):
        before_db = self.store.path.read_bytes()
        before_files = {str(file): file.read_bytes() for file in self.root.rglob("*") if file.is_file()}
        plan = self.plan()
        self.assertEqual(plan["status"], "ready", plan["reasons"])
        self.assertEqual(plan["bytes"], self.legacy.stat().st_size)
        self.assertEqual(plan["document_ids"], [self.document_id])
        self.assertEqual(self.store.path.read_bytes(), before_db)
        self.assertEqual({str(file): file.read_bytes() for file in self.root.rglob("*") if file.is_file()}, before_files)

    def test_cleanup_requires_explicit_review_of_unknown_old_links(self):
        with self.assertRaisesRegex(ValueError, "old links"):
            execute_legacy_cleanup(self.store, [self.plan()])
        self.assertTrue(self.legacy.exists())

    @unittest.skipUnless(os.name == "nt", "Mandatory Windows sharing guards are required")
    def test_reviewed_cleanup_removes_only_copy_and_preserves_sources_ids_and_history(self):
        before = self.saved_note_rows()
        main_bytes = self.main.read_bytes()
        result = execute_legacy_cleanup(self.store, [self.plan()], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "removed", result)
        self.assertFalse(self.legacy.exists())
        self.assertEqual(self.main.read_bytes(), main_bytes)
        self.assertEqual(self.saved_note_rows(), before)
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)
        self.assertEqual(self.plan()["status"], "removed")

    def test_changed_legacy_pdf_is_preserved(self):
        self.legacy.write_bytes(self.legacy.read_bytes() + b"User edits")
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("changed outside Notable", " ".join(plan["reasons"]))
        result = execute_legacy_cleanup(self.store, [plan], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "blocked")
        self.assertTrue(self.legacy.exists())

    def test_edit_after_review_invalidates_plan(self):
        plan = self.plan()
        self.legacy.write_bytes(self.legacy.read_bytes() + b"New edit")
        result = execute_legacy_cleanup(self.store, [plan], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "blocked")
        self.assertTrue(self.legacy.exists())

    def test_main_pdf_edit_after_review_is_preserved_and_blocks_cleanup(self):
        plan = self.plan()
        self.main.write_bytes(self.main.read_bytes() + b"PC annotation changes")
        result = execute_legacy_cleanup(self.store, [plan], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "blocked")
        self.assertTrue(self.legacy.exists())
        self.assertIn("PC annotation changes", self.main.read_text(encoding="latin1"))

    def test_generated_notebook_legacy_hyperlink_requires_rebuild(self):
        self.save_notebook(self.legacy.as_uri() + "#page=1")
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("Rebuild the generated notebook", " ".join(plan["reasons"]))

    def test_relative_encoded_notebook_link_is_also_detected(self):
        self.save_notebook(self.legacy.name.replace(" ", "%20") + "#page=1")
        self.assertEqual(self.plan()["status"], "blocked")

    def test_current_notebook_links_to_main_are_safe(self):
        self.save_notebook(self.main.as_uri() + "#page=1")
        self.assertEqual(self.plan()["status"], "ready")

    def test_unsaved_or_edited_notebook_blocks_cleanup(self):
        self.store.mark_dirty(self.project_id)
        self.assertIn("waiting to save", " ".join(self.plan()["reasons"]))
        self.store.export_result(self.project_id, digest_file(self.output))
        self.output.write_bytes(self.output.read_bytes() + b"Editorial edit")
        self.assertIn("not been verified", " ".join(self.plan()["reasons"]))

    def test_missing_source_layers_are_preserved_for_review(self):
        layers = self.store.path.parent / "remarkable" / self.manifest["layers"]
        layers.write_bytes(layers.read_bytes() + b"Corrupt")
        self.assertIn("retained tablet source cannot", " ".join(self.plan()["reasons"]))
        self.assertTrue(layers.exists())
        self.assertTrue(self.legacy.exists())

    def test_different_tablet_revision_is_not_assumed_reconstructable(self):
        self.payload["legacy_cloud_hash"] = "a" * 64
        self.store.save_remarkable_item(self.item.id, self.payload)
        self.assertIn("revision does not match", " ".join(self.plan()["reasons"]))

    def test_retained_exact_historical_revision_with_same_original_is_ready(self):
        item, bundle, manifest = self.save_new_revision()
        self.assertNotEqual(manifest["layers_hash"], self.manifest["layers_hash"])
        self.assertEqual(manifest["pdf_hash"], self.manifest["pdf_hash"])
        plan = self.plan()
        self.assertEqual(plan["status"], "ready", plan["reasons"])
        history = source_info(self.store, self.item.id, revision=self.item.hash)
        guarded = {row["path"]: row["digest"] for row in plan["guard_files"]}
        self.assertIn(canonical(history["source_path"]), guarded)
        self.assertIn(canonical(history["layers_path"]), guarded)
        self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
        self.assertEqual(source_bundle(self.store, item.id), bundle)

    @unittest.skipUnless(os.name == "nt", "Mandatory Windows sharing guards are required")
    def test_historical_cleanup_retains_both_tablet_revisions_and_notes(self):
        item, bundle, _ = self.save_new_revision()
        before = self.saved_note_rows()
        result = execute_legacy_cleanup(self.store, [self.plan()], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "removed", result)
        self.assertFalse(self.legacy.exists())
        self.assertEqual(self.saved_note_rows(), before)
        self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
        self.assertEqual(source_bundle(self.store, item.id), bundle)

    def test_tampered_historical_manifest_blocks_cleanup_even_if_latest_is_valid(self):
        item, bundle, _ = self.save_new_revision()
        old = source_info(self.store, self.item.id, revision=self.item.hash)
        path = Path(old["source_path"])
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["layers_hash"] = "a" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("manifest failed its integrity check", " ".join(plan["reasons"]))
        self.assertTrue(self.legacy.exists())
        self.assertEqual(source_bundle(self.store, item.id), bundle)

    def test_historical_layers_edit_after_review_blocks_cleanup(self):
        item, bundle, _ = self.save_new_revision()
        plan = self.plan()
        old = source_info(self.store, self.item.id, revision=self.item.hash)
        path = Path(old["layers_path"])
        path.write_bytes(path.read_bytes() + b"Later edit")
        result = execute_legacy_cleanup(self.store, [plan], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "blocked")
        self.assertTrue(self.legacy.exists())
        self.assertEqual(source_bundle(self.store, item.id), bundle)

    def test_historical_copy_from_different_original_stays_blocked(self):
        self.save_new_revision(change_baseline=True)
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("original PDF does not match", " ".join(plan["reasons"]))
        self.assertTrue(self.legacy.exists())

    def test_missing_migration_identity_attestation_blocks_cleanup(self):
        self.payload.pop("legacy_document_ids")
        self.store.save_remarkable_item(self.item.id, self.payload)
        self.assertIn("pre-migration saved note records is missing", " ".join(self.plan()["reasons"]))

    def test_notes_not_relocated_or_hidden_block_cleanup(self):
        with self.store.connect() as db:
            db.execute("UPDATE documents SET path=? WHERE id=?", (canonical(self.legacy), self.document_id))
        self.assertIn("still depend", " ".join(self.plan()["reasons"]))
        with self.store.connect() as db:
            db.execute("UPDATE documents SET path=?,hidden=1 WHERE id=?", (canonical(self.anchor), self.document_id))
        self.assertIn("visible folder and private tablet identity", " ".join(self.plan()["reasons"]))

    def test_note_changes_after_review_invalidate_proof(self):
        plan = self.plan()
        with self.store.connect() as db:
            db.execute("UPDATE entries SET payload=? WHERE document_id=?", (json.dumps({**self.entry, "comment": "Updated saved note"}), self.document_id))
        result = execute_legacy_cleanup(self.store, [plan], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "blocked")
        self.assertTrue(self.legacy.exists())

    def test_migrated_notes_outside_their_watched_folder_block_cleanup(self):
        with self.store.connect() as db:
            metadata = json.loads(db.execute("SELECT metadata FROM documents WHERE id=?", (self.document_id,)).fetchone()[0])
            metadata["logical_folder"] = canonical(self.root / "Unwatched")
            db.execute("UPDATE documents SET metadata=? WHERE id=?", (json.dumps(metadata), self.document_id))
        self.assertIn("visible folder and private tablet identity", " ".join(self.plan()["reasons"]))

    def test_wrong_original_identity_blocks_cleanup(self):
        with self.store.connect() as db:
            db.execute("UPDATE paper_sources SET metadata=? WHERE locator=?", (json.dumps({"role": "tablet_render"}), canonical(self.main)))
        self.assertIn("independent original", " ".join(self.plan()["reasons"]))

    def test_pre_migration_library_has_review_report_and_is_untouched(self):
        self.store.save_remarkable_item(self.item.id, {"path": canonical(self.legacy), "digest": digest_file(self.legacy), "state": "synced"})
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("notes have not finished moving", " ".join(plan["reasons"]))
        self.assertTrue(self.legacy.exists())

    @unittest.skipUnless(os.name == "nt", "Mandatory Windows sharing guards are required")
    def test_write_race_before_guarded_delete_preserves_new_edit(self):
        plan = self.plan()
        from note_organizer.source_storage import _guarded_file as original_guard

        def edit_before_guard(path, digest, action, **kwargs):
            if canonical(path) == canonical(self.legacy):
                self.legacy.write_bytes(self.legacy.read_bytes() + b"Last moment edit")
            return original_guard(path, digest, action, **kwargs)

        with patch("note_organizer.source_storage._guarded_file", side_effect=edit_before_guard):
            result = execute_legacy_cleanup(self.store, [plan], external_links_acknowledged=True)
        self.assertEqual(result[0]["status"], "blocked")
        self.assertTrue(self.legacy.exists())
        self.assertTrue(self.legacy.read_bytes().endswith(b"Last moment edit"))


if __name__ == "__main__":
    unittest.main()
