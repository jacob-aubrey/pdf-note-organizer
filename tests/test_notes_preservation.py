"""Preserve physical annotations and persisted identities across reader changes."""
import json
from pathlib import Path
import tempfile
import unittest

import fitz

from note_organizer.extraction import extract, scan_fingerprint
from note_organizer.paper_registry import Registry
from note_organizer.service import Service
from note_organizer.storage import Store, DEFAULT_SETTINGS, canonical, digest_file
from note_organizer.view_state import read_view


class PreservationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "Watched"
        self.folder.mkdir()
        self.store = Store(self.root / "data" / "notes.sqlite3")
        self.project = self.store.add_project(self.folder)
        self.service = Service(self.store)

    def tearDown(self):
        self.service.stop()
        self.temp.cleanup()

    def pdf(self, path, notes=(("stable-note", "Saved comment", 100),)):
        with fitz.open() as document:
            page = document.new_page()
            for identity, comment, y in notes:
                annotation = page.add_text_annot((50, y), comment)
                document.xref_set_key(annotation.xref, "NM", fitz.get_pdf_str(identity))
            document.save(path)
        return path

    def save(self, path, project=None):
        digest, signature, metadata, entries = extract(path, DEFAULT_SETTINGS)
        counts = self.store.save_scan(project or self.project, path, digest, signature,
                                      scan_fingerprint(DEFAULT_SETTINGS), metadata, entries)
        return counts

    def pair(self):
        self.original = self.pdf(self.folder / "original.pdf")
        self.tablet = self.folder / "tablet.pdf"
        with fitz.open(self.original) as document:
            annotation = document[0].add_text_annot((50, 200), "New tablet comment")
            document.xref_set_key(annotation.xref, "NM", fitz.get_pdf_str("tablet-note"))
            document.save(self.tablet)
        self.save(self.original)
        self.save(self.tablet)
        self.registry = Registry(self.store)
        self.local = self.registry.register_local(self.original)
        self.cloud = self.registry.link_cloud(self.local["paper_id"], "cloud-paper", digest=digest_file(self.original))
        self.render = self.registry.link_local(self.local["paper_id"], self.tablet, metadata={
            "role": "tablet_render", "cloud_id": "cloud-paper", "page_mapping_identity": True,
            "original_pdf_digest": digest_file(self.original)})

    def note_tables(self):
        with self.store.connect() as database:
            return {table: [tuple(row) for row in database.execute("SELECT * FROM " + table)]
                    for table in ("documents", "entries", "history")}


class AnnotationIdentityTests(PreservationFixture):
    def test_duplicate_pdf_ids_preserve_both_notes_and_original_pdf(self):
        pdf = self.pdf(self.folder / "duplicate.pdf", (("duplicate", "First comment", 100),
                                                      ("duplicate", "Second comment", 200)))
        before = digest_file(pdf)
        self.save(pdf)
        entries = self.store.entries(self.project)
        self.assertEqual({entry["comment"] for entry in entries}, {"First comment", "Second comment"})
        self.assertEqual(len({entry["key"] for entry in entries}), 2)
        self.assertEqual(len(self.store.history(entries[0]["document_id"])), 2)
        self.assertEqual(digest_file(pdf), before)
        with fitz.open(pdf) as document:
            self.assertEqual(len(list(document[0].annots())), 2)
        self.assertEqual(self.save(pdf), {"added": 0, "updated": 0, "removed": 0})

    def test_group_delimiters_in_pdf_ids_cannot_collide(self):
        pdf = self.folder / "drawing.pdf"
        with fitz.open() as document:
            page = document.new_page()
            for identity, x, y in (("a", 100, 100), ("b", 110, 100), ("a+b", 400, 600)):
                annotation = page.add_ink_annot([[(x, y), (x + 5, y + 5)]])
                document.xref_set_key(annotation.xref, "NM", fitz.get_pdf_str(identity))
            document.save(pdf)
        self.save(pdf)
        self.assertEqual(len(self.store.entries(self.project)), 2)

    def test_unresolved_duplicate_scan_is_rejected_before_saved_history_changes(self):
        pdf = self.pdf(self.folder / "paper.pdf")
        self.save(pdf)
        before = self.note_tables()
        entry = {"key": "duplicate", "comment": "New note"}
        with self.assertRaisesRegex(ValueError, "Duplicate annotation"):
            self.store.save_scan(self.project, pdf, "new-digest", "new-signature", "{}", {}, [entry, entry])
        self.assertEqual(self.note_tables(), before)


class SourceRevisionTests(PreservationFixture):
    def test_filesystem_rename_keeps_registry_identity_and_combined_notes(self):
        self.pair()
        document_id = self.store.document_at(self.project, self.original)["id"]
        revisions = self.registry.revisions(self.local["id"])
        renamed = self.folder / "renamed.pdf"
        self.original.rename(renamed)
        self.service.scan(self.store.project(self.project), renamed)
        self.assertEqual(self.store.document_at(self.project, renamed)["id"], document_id)
        source = self.registry.source(self.local["id"])
        self.assertEqual(source["path"], canonical(renamed))
        self.assertEqual(source["paper_id"], self.cloud["paper_id"])
        self.assertEqual(self.registry.revisions(source["id"]), revisions)
        papers = read_view(self.store.path).documents(self.project)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["count"], 2)

    def test_rename_destination_with_another_registered_identity_retains_saved_notes(self):
        self.pair()
        renamed = self.folder / "renamed.pdf"
        self.registry.register_local(renamed, digest="unrelated-source")
        before = self.note_tables()
        self.original.rename(renamed)
        with self.assertRaisesRegex(ValueError, "another paper source"):
            self.service.scan(self.store.project(self.project), renamed)
        self.assertEqual(self.note_tables(), before)
        self.assertEqual(self.registry.source(self.local["id"])["path"], canonical(self.original))

    def test_digest_only_change_refreshes_inherited_note_export(self):
        self.pair()
        self.assertEqual(len(self.store.entries(self.project)), 2)
        self.store.export_result(self.project, "previous-export")
        with fitz.open(self.original) as document:
            document[0].draw_rect(fitz.Rect(400, 600, 450, 650))
            document.saveIncr()
        self.assertEqual(self.save(self.original), {"added": 0, "updated": 0, "removed": 0})
        self.assertEqual(len(self.store.entries(self.project)), 3)
        self.assertTrue(self.store.project(self.project)["dirty"])

    def drawing(self):
        path = self.folder / "drawing.pdf"
        entry = {"key": "0:drawing", "kind": "drawing", "page": 1, "rect": [0, 0, 10, 10],
                 "comment": "Original comment", "image": "ORIGINAL_IMAGE"}
        self.store.save_scan(self.project, path, "original-digest", "signature", "{}", {}, [entry])
        return path, entry, self.store.entries(self.project, include_images=False)[0]

    def test_deferred_export_rejects_changed_pdf_image(self):
        path, entry, row = self.drawing()
        self.store.save_scan(self.project, path, "changed-digest", "new-signature", "{}", {},
                             [{**entry, "comment": "New comment", "image": "NEW_IMAGE"}])
        with self.assertRaisesRegex(ValueError, "Refresh Notes"):
            self.service.export_images([row])

    def test_deferred_export_rejects_same_pdf_rescan_and_removed_drawing(self):
        path, entry, row = self.drawing()
        self.assertEqual(self.service.export_images([row])[0]["image"], "ORIGINAL_IMAGE")
        self.store.save_scan(self.project, path, "original-digest", "signature", "new-settings", {},
                             [{**entry, "image": "NEW_CROP"}])
        with self.assertRaisesRegex(ValueError, "Refresh Notes"):
            self.service.export_images([row])
        current = self.store.entries(self.project, include_images=False)[0]
        self.store.save_scan(self.project, path, "original-digest", "signature", "new-settings", {}, [])
        with self.assertRaisesRegex(ValueError, "Refresh Notes"):
            self.service.export_images([current])


class PaperLinkUndoTests(PreservationFixture):
    def two_groups(self):
        self.pair()
        second = self.pdf(self.folder / "second.pdf", (("second-note", "Second original note", 100),))
        self.save(second)
        source = self.registry.register_local(second)
        cloud = self.registry.link_cloud(source["paper_id"], "second-cloud")
        self.before = {row["id"]: row["paper_id"] for row in self.registry.sources()}
        self.registry.link_sources([self.local["id"], cloud["id"]])
        return source

    def test_persisted_undo_restores_entire_groups_without_changing_annotations(self):
        self.two_groups()
        notes = self.note_tables()
        operation = self.registry.latest_link_operation()
        self.assertEqual(operation["source_count"], 5)
        self.assertEqual(operation["changed_source_count"], 2)
        self.store.export_result(self.project, "linked-export")
        reopened = Registry(self.store)
        self.assertEqual(reopened.latest_link_operation()["id"], operation["id"])
        reopened.undo_latest_link(operation["id"])
        self.assertEqual({row["id"]: row["paper_id"] for row in reopened.sources()}, self.before)
        self.assertEqual(self.note_tables(), notes)
        self.assertTrue(self.store.project(self.project)["dirty"])
        self.assertIsNone(reopened.latest_link_operation())
        with self.store.connect() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM paper_link_history").fetchone()[0], 4)

    def test_undo_rejects_new_variants_added_after_link(self):
        self.two_groups()
        operation = self.registry.latest_link_operation()
        additional = self.pdf(self.folder / "new-variant.pdf")
        self.registry.link_local(self.local["paper_id"], additional)
        before = {row["id"]: row["paper_id"] for row in self.registry.sources()}
        with self.assertRaisesRegex(ValueError, "identities changed"):
            self.registry.undo_latest_link(operation["id"])
        self.assertEqual({row["id"]: row["paper_id"] for row in self.registry.sources()}, before)
        self.assertEqual(self.registry.latest_link_operation()["id"], operation["id"])

    def test_undo_rejects_stale_operation_and_legacy_history_has_no_snapshot(self):
        self.two_groups()
        operation = self.registry.latest_link_operation()
        additional = self.registry.register_cloud("unrelated-cloud")
        self.registry.link_sources([self.local["id"], additional["id"]])
        with self.assertRaisesRegex(ValueError, "no longer the latest"):
            self.registry.undo_latest_link(operation["id"])
        with self.store.connect() as database:
            database.execute("DELETE FROM paper_link_operations")
        self.assertIsNone(self.registry.latest_link_operation())
        with self.assertRaisesRegex(ValueError, "no recent paper link"):
            self.registry.undo_latest_link()

    def test_reconfirming_existing_group_does_not_create_an_undo_operation(self):
        self.pair()
        self.registry.link_sources([self.local["id"], self.render["id"]])
        self.assertIsNone(self.registry.latest_link_operation())


class ProjectRelocationTests(PreservationFixture):
    def test_move_rebases_retained_recovery_evidence_and_leaves_external_copies_alone(self):
        self.pair()
        retained = self.folder / "tablet.previous-complete.pdf"
        retained.write_bytes(b"complete preserved tablet PDF")
        external = self.root / "external-preserved.pdf"
        external.write_bytes(b"unrelated preserved PDF")
        self.store.save_remarkable_item("cloud-paper", {"path": canonical(self.tablet), "state": "synced",
            "recovery_paths": [canonical(retained), canonical(external)]})
        moved = self.root / "Relocated"
        self.folder.rename(moved)
        self.store.relocate_project(self.project, moved)
        paths = self.store.remarkable_items()["cloud-paper"]["recovery_paths"]
        self.assertEqual(paths, [canonical(moved / retained.name), canonical(external)])
        from note_organizer.remarkable_sync import retained_recovery_paths
        self.assertEqual(retained_recovery_paths(paths), paths)
        self.assertEqual((moved / retained.name).read_bytes(), b"complete preserved tablet PDF")
        self.assertEqual(external.read_bytes(), b"unrelated preserved PDF")

    def test_retained_parent_project_keeps_logical_identity_after_subfolder_move(self):
        self.pair()
        parent = self.store.add_project(self.root)
        self.save(self.original, parent)
        self.save(self.tablet, parent)
        ids = {document["id"] for document in self.store.documents(parent)}
        self.store.export_result(parent, "parent-export")
        moved = self.root / "Relocated"
        self.folder.rename(moved)
        self.store.relocate_project(self.project, moved)
        papers = read_view(self.store.path).documents(parent)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["count"], 2)
        self.assertEqual(papers[0]["logical_paper_id"], self.local["paper_id"])
        self.assertTrue(papers[0]["missing"])
        self.assertEqual(set(papers[0]["variant_document_ids"]), ids)
        self.assertEqual(len(self.store.entries(document_id=papers[0]["id"])), 2)
        self.assertTrue(self.store.project(parent)["dirty"])

    def test_move_preserves_notes_nested_projects_outputs_and_routing(self):
        self.pair()
        child = self.folder / "Nested"
        child.mkdir()
        child_pdf = self.pdf(child / "child.pdf")
        external_output = self.root / "external.docx"
        nested = self.store.add_project(child, output=external_output)
        self.save(child_pdf, nested)
        child_source = self.registry.register_local(child_pdf)
        self.store.set_preference("remarkable", {"pc_root": str(self.folder), "mappings": {
            "nested": str(child), "external": str(self.root / "Elsewhere")}})
        self.store.set_preference("inbox", {"library_root": str(self.folder), "watch_root": str(self.root / "Incoming")})
        self.store.save_remarkable_item("cloud-paper", {"path": canonical(self.tablet), "state": "synced"})
        self.store.set_preference("remarkable_outbox", [{"id": "queued", "kind": "pdf", "path": canonical(child_pdf),
            "state": "queued", "pc_root": canonical(self.folder), "source_folder_id": "literature"}])
        with self.store.connect() as database:
            database.execute("CREATE TABLE inbox_jobs (id TEXT PRIMARY KEY,path TEXT,source TEXT,signature TEXT,state TEXT)")
            database.execute("INSERT INTO inbox_jobs VALUES(?,?,?,?,?)", ("pending", canonical(child_pdf), "incoming.pdf", "sig", "confirmed"))
        before = self.note_tables()
        original_project = self.store.project(self.project)
        revisions = self.registry.revisions(child_source["id"])
        moved = self.root / "Relocated"
        self.folder.rename(moved)
        updated = self.store.relocate_project(self.project, moved)
        self.assertEqual(updated["id"], self.project)
        self.assertEqual(updated["root"], canonical(moved))
        self.assertEqual(updated["settings"], original_project["settings"])
        self.assertEqual(updated["output"], canonical(moved / Path(original_project["output"]).name))
        self.assertEqual(self.store.project(nested)["root"], canonical(moved / "Nested"))
        self.assertEqual(self.store.project(nested)["output"], str(external_output))
        after = self.note_tables()
        self.assertEqual(before["entries"], after["entries"])
        self.assertEqual(before["history"], after["history"])
        self.assertEqual({row[0] for row in before["documents"]}, {row[0] for row in after["documents"]})
        self.assertEqual(self.registry.source(child_source["id"])["path"], canonical(moved / "Nested" / "child.pdf"))
        self.assertEqual(self.registry.revisions(child_source["id"]), revisions)
        self.assertEqual(read_view(self.store.path).documents(self.project)[0]["count"], 2)
        remarkable = self.store.preference("remarkable")
        self.assertEqual(remarkable["pc_root"], canonical(moved))
        self.assertEqual(remarkable["mappings"]["nested"], canonical(moved / "Nested"))
        self.assertEqual(remarkable["mappings"]["external"], str(self.root / "Elsewhere"))
        self.assertEqual(self.store.preference("inbox")["library_root"], canonical(moved))
        self.assertEqual(self.store.preference("inbox")["watch_root"], str(self.root / "Incoming"))
        self.assertEqual(self.store.remarkable_items()["cloud-paper"]["path"], canonical(moved / "tablet.pdf"))
        job = self.store.preference("remarkable_outbox")[0]
        self.assertEqual(job["path"], canonical(moved / "Nested" / "child.pdf"))
        self.assertEqual(job["state"], "review")
        with self.store.connect() as database:
            job = database.execute("SELECT * FROM inbox_jobs").fetchone()
            self.assertEqual(job["path"], canonical(moved / "Nested" / "child.pdf"))
            self.assertEqual((job["source"], job["signature"], job["state"]), ("incoming.pdf", "sig", "confirmed"))

    def test_conflicting_destination_rolls_back_entire_relocation(self):
        self.pair()
        moved = self.root / "Relocated"
        moved.mkdir()
        occupied = self.registry.register_local(moved / "original.pdf", digest="other-source")
        before = self.note_tables()
        projects = self.store.projects()
        with self.assertRaisesRegex(ValueError, "registered source"):
            self.store.relocate_project(self.project, moved)
        self.assertEqual(self.note_tables(), before)
        self.assertEqual(self.store.projects(), projects)
        self.assertEqual(self.registry.source(occupied["id"])["path"], canonical(moved / "original.pdf"))
        self.assertEqual(self.registry.source(self.local["id"])["path"], canonical(self.original))


if __name__ == "__main__":
    unittest.main()
