"""Linked variants share a reader entry without losing independent annotations."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import fitz

from note_organizer.extraction import extract
from note_organizer.paper_registry import Registry
from note_organizer.reconciliation import scan_reconciliation, link_registry_sources
from note_organizer.exporting import build_notebook
from note_organizer.storage import Store, DEFAULT_SETTINGS, canonical
from note_organizer.view_state import read_view


class LogicalPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data" / "notes.sqlite3")
        self.library = self.root / "Sorted"
        self.library.mkdir()
        self.project = self.store.add_project(self.library)
        self.original = self.library / "Original.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((60, 90), "A valuable baseline quote")
            note = page.add_text_annot((70, 130), "Old Acrobat comment")
            document.xref_set_key(note.xref, "NM", fitz.get_pdf_str("pc-existing-note"))
            mark = page.add_highlight_annot(page.search_for("valuable baseline"))
            document.xref_set_key(mark.xref, "NM", fitz.get_pdf_str("pc-existing-highlight"))
            document.set_metadata({"title": "One research paper"})
            self.original.write_bytes(document.tobytes())
        self.render = self.library / "Tablet copy.pdf"
        with fitz.open(self.original) as document:
            note = document[0].add_text_annot((70, 190), "New tablet comment")
            document.xref_set_key(note.xref, "NM", fitz.get_pdf_str("remarkable-new-note"))
            self.render.write_bytes(document.tobytes())
        self.original_notes = self.save(self.original)
        self.render_notes = self.save(self.render)
        self.original_id = self.store.document_at(self.project, self.original)["id"]
        self.render_id = self.store.document_at(self.project, self.render)["id"]
        self.registry = Registry(self.store)
        self.local_source = self.registry.register_local(self.original)
        self.cloud_source = self.registry.link_cloud(self.local_source["paper_id"], "cloud-paper", digest=self.digest(self.original))
        self.render_source = self.registry.link_local(self.local_source["paper_id"], self.render,
            metadata={"role": "tablet_render", "cloud_id": "cloud-paper", "page_mapping_identity": True,
                      "original_pdf_digest": self.digest(self.original)})

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save(self, path, project=None, entries=None):
        digest, signature, metadata, extracted = extract(path, DEFAULT_SETTINGS)
        self.store.save_scan(project or self.project, path, digest, signature, json.dumps(DEFAULT_SETTINGS),
                             metadata, extracted if entries is None else entries)
        return extracted

    def test_linked_variants_collapse_per_project_and_count_inherited_marks_once(self):
        view = read_view(self.store.path)
        papers = view.documents(self.project)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper["id"], self.original_id)
        self.assertEqual(paper["count"], 3)
        self.assertEqual(paper["inherited_duplicate_count"], 2)
        self.assertEqual(set(paper["variant_document_ids"]), {self.original_id, self.render_id})
        self.assertEqual(paper["logical_paper_id"], self.local_source["paper_id"])
        # Raw documents continue to support scanning each independent source.
        self.assertEqual(len(self.store.documents(self.project)), 2)

    def test_selected_paper_includes_variant_notes_with_their_real_source_ids(self):
        notes = self.store.entries(document_id=self.original_id, include_images=False)
        self.assertEqual(len(notes), 3)
        old = next(note for note in notes if note.get("comment") == "Old Acrobat comment")
        new = next(note for note in notes if note.get("comment") == "New tablet comment")
        self.assertEqual(old["document_id"], self.original_id)
        self.assertEqual(old["path"], canonical(self.original))
        self.assertEqual(new["document_id"], self.render_id)
        self.assertEqual(new["path"], canonical(self.render))
        self.assertEqual(new["source_digest"], self.digest(self.render))
        self.assertTrue(all(note["logical_paper_id"] == self.local_source["paper_id"] for note in notes))
        # History remains attached to physical variants, including omitted marks.
        self.assertEqual(len(self.store.history(self.original_id)), 2)
        self.assertEqual(len(self.store.history(self.render_id)), 3)

    def test_deduplication_happens_before_search_and_keeps_the_original_mark(self):
        notes = self.store.entries(document_id=self.original_id, query="Old Acrobat", fields=["comment"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["document_id"], self.original_id)
        new = self.store.entries(project_id=self.project, query="New tablet", fields=["comment"])
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["document_id"], self.render_id)

    def test_ambiguous_page_mapping_preserves_all_annotation_variants(self):
        self.registry.register_local(self.render, metadata={"role": "tablet_render", "cloud_id": "cloud-paper"})
        self.assertEqual(len(self.store.entries(document_id=self.original_id)), 5)
        self.assertEqual(read_view(self.store.path).documents()[0]["count"], 5)

    def test_changed_original_hash_does_not_suppress_similar_annotations(self):
        self.registry.register_cloud("cloud-paper", digest="another-baseline-revision")
        self.assertEqual(len(self.store.entries(document_id=self.original_id)), 5)
        self.assertEqual(read_view(self.store.path).documents()[0]["count"], 5)

    def test_modified_annotation_comment_or_position_is_retained(self):
        changed = deepcopy(self.render_notes)
        inherited = next(note for note in changed if note.get("comment") == "Old Acrobat comment")
        inherited["comment"] = "Changed independently on the tablet"
        self.save(self.render, entries=changed)
        notes = self.store.entries(document_id=self.original_id)
        self.assertEqual(len(notes), 4)
        self.assertTrue(any(note.get("comment") == "Old Acrobat comment" for note in notes))
        self.assertTrue(any(note.get("comment") == "Changed independently on the tablet" for note in notes))
        self.assertEqual(read_view(self.store.path).documents()[0]["count"], 4)

    def test_project_membership_limits_variant_expansion(self):
        child = self.store.add_project(self.library / "A separate project")
        self.save(self.original, project=child)
        child_id = self.store.document_at(child, self.original)["id"]
        view = read_view(self.store.path)
        self.assertEqual(len(view.documents()), 2)
        self.assertEqual(view.documents(self.project)[0]["count"], 3)
        self.assertEqual(view.documents(child)[0]["count"], 2)
        self.assertEqual(len(self.store.entries(document_id=child_id)), 2)
        self.assertTrue(all(note["document_id"] == child_id for note in self.store.entries(project_id=child)))

    def test_variant_note_revision_invalidates_representative_token(self):
        before = read_view(self.store.path)
        token = before.note_token(self.project, self.original_id)
        revised = deepcopy(self.render_notes)
        next(note for note in revised if note.get("comment") == "New tablet comment")["comment"] = "Corrected tablet comment"
        self.save(self.render, entries=revised)
        after = read_view(self.store.path)
        self.assertEqual(before.documents()[0]["id"], after.documents()[0]["id"])
        self.assertEqual(before.documents()[0]["count"], after.documents()[0]["count"])
        self.assertNotEqual(token, after.note_token(self.project, self.original_id))
        self.assertEqual(after.note_token(self.project, self.original_id), after.note_token(self.project, self.render_id))

    def test_snapshot_and_text_reader_never_load_drawing_images(self):
        marker = "independent drawing image" * 10000
        original = deepcopy(self.original_notes)
        tablet = deepcopy(self.render_notes)
        drawing = {"key": "0:shared-drawing", "kind": "drawing", "page": 1, "page_count": 1,
                   "rect": [10, 10, 20, 20], "image": marker}
        original.append(drawing)
        tablet.append(drawing)
        self.save(self.original, entries=original)
        self.save(self.render, entries=tablet)
        view = read_view(self.store.path)
        self.assertEqual(view.documents()[0]["count"], 5)
        self.assertNotIn(marker, repr(vars(view)))
        notes = self.store.entries(document_id=self.original_id, include_images=False)
        self.assertEqual(len(notes), 5)
        self.assertNotIn(marker, repr(notes))
        self.assertEqual(sum(note["kind"] == "drawing" for note in notes), 2)
        self.assertEqual(self.store.entry_image(self.render_id, drawing["key"]), marker)

    def test_xref_only_keys_and_similar_text_are_not_deduplicated(self):
        notes = deepcopy(self.render_notes)
        inherited = next(note for note in notes if note.get("comment") == "Old Acrobat comment")
        inherited["key"] = "0:xref-12"
        self.save(self.render, entries=notes)
        self.assertEqual(len(self.store.entries(document_id=self.original_id)), 4)
        self.assertEqual(read_view(self.store.path).documents()[0]["count"], 4)

    def test_confirming_original_and_cloud_keeps_existing_tablet_variants_together(self):
        # This is the initial reconciliation case: a local original belongs to
        # A, while the downloaded cloud document and its render already belong
        # to B. The scanner proposes only original/cloud, not the render.
        store = Store(self.root / "merge-case" / "notes.sqlite3")
        project = store.add_project(self.library)
        parent_project = store.add_project(self.root)
        for path, notes in ((self.original, self.original_notes), (self.render, self.render_notes)):
            metadata = json.loads(self.store.document_at(self.project, path)["metadata"])
            store.save_scan(project, path, self.digest(path), "signature", "{}", metadata, notes)
        store.save_scan(parent_project, self.render, self.digest(self.render), "signature", "{}",
                        {"title": "One research paper"}, self.render_notes)
        unrelated = self.library / "Unrelated.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((60, 90), "A different study")
            page.add_text_annot((60, 130), "Keep this independent note")
            document.set_metadata({"title": "Unrelated study"})
            unrelated.write_bytes(document.tobytes())
        digest, signature, metadata, unrelated_notes = extract(unrelated, DEFAULT_SETTINGS)
        store.save_scan(project, unrelated, digest, signature, "{}", metadata, unrelated_notes)
        unrelated_project = store.add_project(self.root / "Other project")
        store.save_scan(unrelated_project, unrelated, digest, signature, "{}", metadata, unrelated_notes)
        registry = Registry(store)
        original_source = registry.register_local(self.original)
        cloud_source = registry.register_cloud("merge-cloud", digest=self.digest(self.original), title="One research paper")
        render_source = registry.link_local(cloud_source["paper_id"], self.render,
            metadata={"role": "tablet_render", "cloud_id": "merge-cloud", "page_mapping_identity": True,
                      "original_pdf_digest": self.digest(self.original)})
        unrelated_source = registry.register_local(unrelated)
        store.set_preference("remarkable_folders", [{"id": "literature", "name": "Literature", "parent": "",
            "ancestor_ids": [], "path": "/Literature"}])
        store.save_remarkable_item("merge-cloud", {"name": "One research paper", "parent": "literature",
            "cloud_path": "/Literature/One research paper", "state": "synced", "path": canonical(self.render),
            "digest": self.digest(self.render)})
        store.set_preference("remarkable_documents", [{"id": "merge-cloud", "name": "One research paper",
            "parent": "literature", "pdf_hash": self.digest(self.original)}])
        findings = scan_reconciliation(store, {"integration_enabled": True, "pc_root": str(self.library),
            "source_folder_id": "literature", "source_folder_name": "Literature"})
        match = next(row for row in findings if row.get("basis") == "exact_original")
        self.assertEqual({source.get("source_id") for source in match["sources"]},
                         {original_source["id"], cloud_source["id"]})
        self.assertEqual(len(read_view(store.path).documents(project)), 3)
        for project_id in (project, parent_project, unrelated_project):
            store.export_result(project_id, "previous-notebook")
        with store.connect() as db:
            before = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
                      for table in ("documents", "entries", "history")}
        paper_id = link_registry_sources(store, match["sources"])
        self.assertEqual(paper_id, original_source["paper_id"])
        self.assertEqual(registry.source(cloud_source["id"])["paper_id"], paper_id)
        self.assertEqual(registry.source(render_source["id"])["paper_id"], paper_id)
        self.assertEqual(registry.source(unrelated_source["id"])["paper_id"], unrelated_source["paper_id"])
        view = read_view(store.path)
        self.assertEqual(len(view.documents(project)), 2)
        merged = next(row for row in view.documents(project) if row["logical_paper_id"] == paper_id)
        self.assertEqual(merged["count"], 3)
        notes = store.entries(document_id=merged["id"], include_images=False)
        self.assertEqual(len(notes), 3)
        self.assertTrue(any(note.get("comment") == "New tablet comment" for note in notes))
        for layout in ("Reading", "Detailed"):
            notebook = build_notebook("Project notes", store.entries(project_id=project, include_images=False), layout=layout)
            headings = [paragraph.text for paragraph in notebook.paragraphs if paragraph.style.name == "Heading 1"]
            self.assertEqual(headings.count("One research paper"), 1)
            self.assertIn("Unrelated study", headings)
        with store.connect() as db:
            after = {table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
                     for table in ("documents", "entries", "history")}
            links = [dict(row) for row in db.execute("SELECT * FROM paper_link_history")]
        self.assertEqual(before, after)
        self.assertEqual({row["source_id"] for row in links}, {cloud_source["id"], render_source["id"]})
        self.assertTrue(all(row["previous_paper_id"] == cloud_source["paper_id"] and row["paper_id"] == paper_id for row in links))
        self.assertTrue(store.project(project)["dirty"])
        self.assertTrue(store.project(parent_project)["dirty"])
        self.assertFalse(store.project(unrelated_project)["dirty"])


if __name__ == "__main__":
    unittest.main()
