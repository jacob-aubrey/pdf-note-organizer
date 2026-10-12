"""Offline SI naming, reuse, filing, recovery, and identity regressions."""
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import threading
import unittest
from unittest.mock import patch
from docx import Document

from note_organizer.citations import save_citation
from note_organizer.inbox import file_signature
from note_organizer.paper_registry import Registry
from note_organizer.reconciliation import scan_reconciliation
from note_organizer.sorting.core_logic import build_proposed_filename, FILENAME_FORMATS
from note_organizer.storage import Store, canonical, digest_file, timestamp
from note_organizer.supplement_library import (attach_file, attachments, filed, find_existing,
                                              parent_details, proposed_name)
from note_organizer.supplements import download_and_attach
from tests import test_research_features as research_tests
from tests import test_inbox as inbox_tests


class SupplementIntegrationTests(unittest.TestCase):
    setUp = research_tests.ResearchTests.setUp
    tearDown = research_tests.ResearchTests.tearDown
    scan = research_tests.ResearchTests.scan
    make_pdf = staticmethod(research_tests.ResearchTests.make_pdf)

    def citation(self):
        record = {"title": "Paper title", "authors": ["Doe, Jane", "Smith, Alex"],
                  "journal": "Synthetic Chemistry", "year": "2025", "doi": "10.1234/parent"}
        save_citation(self.store, self.document_id, record)
        return record

    def supplement(self, name="data.pdf"):
        path = self.folder / name
        self.make_pdf(path, ["Supporting information: independent experiments"])
        return path

    def response(self, data):
        response = BytesIO(data)
        response.headers = {"Content-Type": "application/pdf"}
        return response

    def test_all_naming_styles_delegate_to_sorter_and_preserve_data_extension(self):
        details = parent_details(self.citation())
        for style in FILENAME_FORMATS:
            with self.subTest(style=style):
                template = "{title}_{year}"
                self.store.set_preference("inbox", {"filename_format": style, "custom_filename_template": template})
                expected = build_proposed_filename(details, ".pdf", filename_format=style, custom_template=template)
                self.assertEqual(proposed_name(self.store, self.document_id, ".pdf"), expected)
                self.assertEqual(proposed_name(self.store, self.document_id, ".xlsx"), Path(expected).stem + ".xlsx")
                self.assertEqual(Path(expected).stem.count("_SI"), 1)

    def test_reviewed_journal_abbreviation_is_shared_and_cleared_after_journal_edit(self):
        record = self.citation()
        self.store.save_scan(self.project, self.path, digest_file(self.path), "sig", "settings",
                             {"journal": record["journal"], "journal_abbreviation": "Synth Chem"}, [])
        self.store.set_preference("inbox", {"filename_format": "journal_compact"})
        expected = build_proposed_filename({**parent_details(record), "journal_abbreviation": "Synth Chem"}, ".pdf", filename_format="journal_compact")
        self.assertEqual(proposed_name(self.store, self.document_id, ".pdf"), expected)
        save_citation(self.store, self.document_id, {**record, "journal": "Different journal"})
        self.assertNotIn("Synth Chem", proposed_name(self.store, self.document_id, ".pdf"))

    def test_long_data_filename_keeps_si_marker_and_length_limit(self):
        self.citation()
        self.store.set_preference("inbox", {"filename_format": "custom", "custom_filename_template": "{title}_{title}_{title}_{title}"})
        save_citation(self.store, self.document_id, {"title": "A" * 100})
        for suffix in (".pdf", ".xlsx", ".pptx", ".json"):
            name = proposed_name(self.store, self.document_id, suffix)
            self.assertLessEqual(len(name), 220)
            self.assertTrue(name.endswith("_SI" + suffix))

    def test_legacy_attachment_and_reviewed_filings_upgrade_without_loss(self):
        existing = self.supplement()
        with self.store.connect() as db:
            db.execute("INSERT INTO paper_attachments VALUES(?,?,?)", (self.document_id, str(existing.resolve()), "https://example.org/legacy"))
        self.assertEqual(len(find_existing(self.store, self.document_id)), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT digest FROM supplement_files WHERE path=?", (canonical(existing),)).fetchone()[0], digest_file(existing))
        self.assertEqual(attachments(Store(self.store.path), self.document_id)[0]["url"], "https://example.org/legacy")

    def test_filename_candidate_requires_explicit_attachment(self):
        self.citation()
        existing = self.supplement(proposed_name(self.store, self.document_id, ".pdf"))
        rows = find_existing(self.store, self.document_id)
        self.assertEqual([canonical(row["path"]) for row in rows], [canonical(existing)])
        self.assertIn("review", rows[0]["source"])
        self.assertEqual(attachments(self.store, self.document_id), [])
        attach_file(self.store, self.document_id, existing)
        self.assertEqual(find_existing(self.store, self.document_id)[0]["source"], "Already attached")

    def test_download_reuses_identical_bytes_under_an_unrelated_library_name(self):
        existing = self.supplement("previously downloaded.pdf")
        target = self.folder / "new_SI.pdf"
        with patch("note_organizer.supplements.open_url", return_value=self.response(existing.read_bytes())):
            result = download_and_attach(self.store, self.document_id, "https://example.org/si.pdf", target)
        self.assertTrue(result["reused"])
        self.assertEqual(canonical(result["path"]), canonical(existing))
        self.assertFalse(target.exists())
        self.assertEqual(len(attachments(self.store, self.document_id)), 1)
        self.assertFalse(list(self.folder.glob(".notable-si-*")))

    def test_attached_url_reuse_requires_unchanged_bytes(self):
        existing = self.supplement()
        url = "https://example.org/si.pdf"
        attach_file(self.store, self.document_id, existing, url)
        with patch("note_organizer.supplements.open_url") as request:
            result = download_and_attach(self.store, self.document_id, url, self.folder / "unused.pdf")
            self.assertTrue(result["reused"])
            request.assert_not_called()
        original = existing.read_bytes()
        existing.write_bytes(original + b"changed")
        target = self.folder / "fresh.pdf"
        with patch("note_organizer.supplements.open_url", return_value=self.response(original)) as request:
            result = download_and_attach(self.store, self.document_id, url, target)
            request.assert_called_once()
            self.assertFalse(result["reused"])
        self.assertEqual(target.read_bytes(), original)

    def test_two_simultaneous_downloads_publish_only_one_copy(self):
        staging = self.supplement()
        data = staging.read_bytes()
        staging.unlink()
        ready = threading.Barrier(2)
        def response(url):
            ready.wait(timeout=5)
            return self.response(data)
        with patch("note_organizer.supplements.open_url", side_effect=response), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(download_and_attach, self.store, self.document_id,
                                       "https://example.org/si.pdf", self.folder / name) for name in ("one.pdf", "two.pdf")]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(row["reused"] for row in results), [False, True])
        self.assertEqual(len({canonical(row["path"]) for row in results}), 1)
        self.assertEqual(len(attachments(self.store, self.document_id)), 1)

    def test_different_existing_target_is_never_overwritten(self):
        existing = self.supplement()
        target = self.folder / "occupied.pdf"
        target.write_bytes(b"keep these bytes")
        with patch("note_organizer.supplements.open_url", return_value=self.response(existing.read_bytes() + b"new")):
            with self.assertRaises(FileExistsError):
                download_and_attach(self.store, self.document_id, "https://example.org/si.pdf", target)
        self.assertEqual(target.read_bytes(), b"keep these bytes")
        self.assertEqual(attachments(self.store, self.document_id), [])

    def test_article_download_and_article_copy_cannot_be_attached_as_si(self):
        target = self.folder / "wrong.pdf"
        with patch("note_organizer.supplements.open_url", return_value=self.response(self.path.read_bytes())):
            with self.assertRaisesRegex(ValueError, "article itself"):
                download_and_attach(self.store, self.document_id, "https://example.org/article.pdf", target)
        self.assertFalse(target.exists())
        shutil.copyfile(self.path, target)
        with self.assertRaisesRegex(ValueError, "own supplementary"):
            attach_file(self.store, self.document_id, target)

    def test_cancellation_does_not_publish_or_attach(self):
        target = self.folder / "cancelled.pdf"
        with self.assertRaises(InterruptedError):
            download_and_attach(self.store, self.document_id, "https://example.org/si.pdf", target, lambda: True)
        self.assertFalse(target.exists())
        self.assertEqual(attachments(self.store, self.document_id), [])

    def test_pdf_rename_rescan_repairs_attachment_and_keeps_si_notes_separate(self):
        existing = self.supplement()
        attach_file(self.store, self.document_id, existing)
        self.scan(existing)
        si_id = self.store.document_at(self.project, existing)["id"]
        renamed = self.folder / "renamed.pdf"
        existing.rename(renamed)
        self.scan(renamed)
        self.assertEqual(self.store.document_at(self.project, renamed)["id"], si_id)
        self.assertEqual(attachments(self.store, self.document_id)[0]["path"], str(renamed.resolve()))
        self.assertEqual([row["id"] for row in self.store.search_documents(document_id=self.document_id, whole_paper=True)], [self.document_id])

    def test_non_pdf_move_repaired_by_unique_hash_during_library_search(self):
        existing = self.folder / "results.csv"
        existing.write_text("a,b\n1,2\n")
        attach_file(self.store, self.document_id, existing, "https://example.org/data.csv")
        renamed = self.folder / "moved.csv"
        existing.rename(renamed)
        find_existing(self.store, self.document_id)
        self.assertEqual(attachments(self.store, self.document_id), [{"path": str(renamed.resolve()), "url": "https://example.org/data.csv"}])

    def test_ambiguous_moved_copies_are_not_silently_chosen(self):
        existing = self.supplement()
        attach_file(self.store, self.document_id, existing)
        for name in ("one.pdf", "two.pdf"):
            shutil.copyfile(existing, self.folder / name)
        existing.unlink()
        find_existing(self.store, self.document_id)
        self.assertEqual(canonical(attachments(self.store, self.document_id)[0]["path"]), canonical(existing))
        self.scan(self.folder / "one.pdf")
        self.assertEqual(canonical(attachments(self.store, self.document_id)[0]["path"]), canonical(existing))
        rows = scan_reconciliation(self.store, {}, local_root=self.folder)
        self.assertFalse([row for row in rows if row["kind"] == "local_possible_variants" and canonical(self.path) in row["local_paths"]])

    def test_missing_attachment_location_cannot_be_reused_for_different_download(self):
        original = self.supplement("old_SI.pdf")
        attach_file(self.store, self.document_id, original)
        original.unlink()
        new_data = self.supplement("newdata.pdf").read_bytes() + b"different"
        with patch("note_organizer.supplements.open_url", return_value=self.response(new_data)):
            with self.assertRaisesRegex(ValueError, "different supplementary"):
                download_and_attach(self.store, self.document_id, "https://example.org/new", original)
        self.assertFalse(original.exists())

    def test_relocated_project_updates_non_pdf_attachment_paths(self):
        root = self.folder / "watched"
        root.mkdir()
        project = self.store.add_project(root)
        paper = root / "article.pdf"
        self.make_pdf(paper, ["Article"])
        self.store.save_scan(project, paper, digest_file(paper), "sig", "settings", {}, [])
        document = self.store.document_at(project, paper)["id"]
        data = root / "data.csv"
        data.write_text("results")
        attach_file(self.store, document, data)
        moved = self.folder / "new location"
        root.rename(moved)
        self.store.relocate_project(project, moved)
        self.assertEqual(canonical(attachments(self.store, document)[0]["path"]), canonical(moved / data.name))

    def test_registry_relocation_updates_attachment(self):
        existing = self.supplement()
        attach_file(self.store, self.document_id, existing)
        registry = Registry(self.store)
        source = registry.register_local(existing)
        moved = self.folder / "relocated.pdf"
        existing.rename(moved)
        registry.relocate_local(source["id"], moved)
        self.assertEqual(canonical(attachments(self.store, self.document_id)[0]["path"]), canonical(moved))

    def test_parent_si_merges_rejected_but_si_variants_can_link(self):
        existing = self.supplement()
        self.scan(existing)
        attach_file(self.store, self.document_id, existing)
        registry = Registry(self.store)
        parent = registry.register_local(self.path)
        si = registry.register_local(existing)
        with self.assertRaisesRegex(ValueError, "separate document"):
            registry.link_sources([parent["id"], si["id"]])
        variant = self.supplement("annotated-si.pdf")
        another = registry.register_local(variant)
        registry.link_sources([si["id"], another["id"]])
        with self.assertRaises(ValueError):
            registry.link_sources([parent["id"], another["id"]])
        self.assertNotEqual(registry.source(parent["id"])["paper_id"], registry.source(si["id"])["paper_id"])

    def test_generated_variant_route_cannot_bypass_si_merge_guard(self):
        existing = self.supplement()
        attach_file(self.store, self.document_id, existing)
        registry = Registry(self.store)
        parent = registry.register_local(self.path)
        with self.assertRaisesRegex(ValueError, "separate document"):
            registry.link_local(parent["paper_id"], existing)
        self.assertEqual(len(registry.sources()), 1)

    def test_same_title_and_doi_do_not_suggest_parent_si_variant_merge(self):
        existing = self.supplement()
        self.scan(existing)
        attach_file(self.store, self.document_id, existing)
        rows = scan_reconciliation(self.store, {}, local_root=self.folder)
        self.assertFalse([row for row in rows if row["kind"] == "local_possible_variants"])

    def test_circular_attachment_is_rejected(self):
        existing = self.supplement()
        self.scan(existing)
        attach_file(self.store, self.document_id, existing)
        si_id = self.store.document_at(self.project, existing)["id"]
        with self.assertRaisesRegex(ValueError, "circular"):
            attach_file(self.store, si_id, self.path)

    def test_parent_may_arrive_after_si_and_ambiguous_editions_require_review(self):
        record = {"doi": "10.1234/parent", "title": "Paper title"}
        existing = self.supplement()
        with self.store.connect() as db:
            filed(db, existing, existing, digest_file(existing), parent_details(record))
        self.assertEqual(attachments(self.store, self.document_id), [])
        self.citation()
        self.assertEqual(len(attachments(self.store, self.document_id)), 1)
        second = self.supplement("second-paper.pdf")
        self.scan(second)
        second_id = self.store.document_at(self.project, second)["id"]
        save_citation(self.store, second_id, record)
        ambiguous = self.supplement("unassigned-si.pdf")
        with self.store.connect() as db:
            filed(db, ambiguous, ambiguous, digest_file(ambiguous), parent_details(record))
        self.assertNotIn(canonical(ambiguous), {canonical(row["path"]) for row in attachments(self.store, self.document_id)})
        self.assertEqual(attachments(self.store, second_id), [])
        self.assertIn(canonical(ambiguous), {canonical(row["path"]) for row in find_existing(self.store, self.document_id)})


class SupplementInboxTests(unittest.TestCase):
    setUp = inbox_tests.InboxTests.setUp
    tearDown = inbox_tests.InboxTests.tearDown
    pdf = inbox_tests.InboxTests.pdf
    ready = inbox_tests.InboxTests.ready

    def parent(self):
        path = self.pdf("article.pdf", self.library)
        project = self.store.add_project(self.library)
        self.store.save_scan(project, path, digest_file(path), "sig", "settings", {}, [])
        document = self.store.document_at(project, path)["id"]
        record = {"title": "Article", "authors": ["Doe, Jane"], "journal": "Chemistry", "year": "2025", "doi": "10.1234/parent"}
        save_citation(self.store, document, record)
        return document, record

    def test_known_attachment_in_inbox_uses_parent_naming_and_tracks_filing(self):
        document, record = self.parent()
        incoming = self.pdf()
        # Distinguish SI bytes from its article.
        incoming.write_bytes(incoming.read_bytes().replace(b"%%EOF", b"%SI\n%%EOF"))
        attach_file(self.store, document, incoming)
        with patch("note_organizer.sorting.core_logic.get_basic_document_details") as extract:
            review = self.ready(incoming)
            extract.assert_not_called()
        self.assertEqual(review["proposed_filename"], build_proposed_filename(parent_details(record), ".pdf"))
        result = self.inbox.file_item(incoming, review["proposed_filename"], self.library)
        self.assertEqual(canonical(attachments(self.store, document)[0]["path"]), result["path"])
        self.assertFalse(incoming.exists())
        self.assertTrue(Path(result["path"]).exists())

    def test_sorter_explicit_parent_doi_creates_attachment(self):
        document, record = self.parent()
        incoming = self.pdf()
        incoming.write_bytes(incoming.read_bytes().replace(b"%%EOF", b"%SI\n%%EOF"))
        with patch("note_organizer.sorting.core_logic.get_basic_document_details", return_value=parent_details(record)):
            review = self.ready(incoming)
        result = self.inbox.file_item(incoming, review["proposed_filename"], self.library)
        self.assertEqual(canonical(attachments(self.store, document)[0]["path"]), result["path"])
        reopened = Store(self.store.path)
        self.assertEqual(len(attachments(reopened, document)), 1)

    def test_manual_parent_selection_updates_an_already_cached_inbox_review(self):
        document, record = self.parent()
        incoming = self.pdf()
        incoming.write_bytes(incoming.read_bytes().replace(b"%%EOF", b"%SI\n%%EOF"))
        self.ready(incoming)
        attach_file(self.store, document, incoming)
        review = self.inbox.prepare(incoming)
        self.assertTrue(review["is_supplementary_material"])
        self.assertEqual(review["proposed_filename"], build_proposed_filename(parent_details(record), ".pdf"))
        result = self.inbox.file_item(incoming, review["proposed_filename"], self.library)
        self.assertEqual(canonical(attachments(self.store, document)[0]["path"]), result["path"])

    def test_interrupted_copy_recovery_replays_attachment_handoff(self):
        document, record = self.parent()
        incoming = self.pdf()
        incoming.write_bytes(incoming.read_bytes().replace(b"%%EOF", b"%SI\n%%EOF"))
        signature = file_signature(incoming)
        target = self.library / "recovered_SI.pdf"
        shutil.copyfile(incoming, target)
        with self.store.connect() as db:
            db.execute("""INSERT INTO inbox_jobs(id,source,path,signature,digest,details,state,created_at)
                VALUES(?,?,?,?,?,?,'copied',?)""", ("recover-si", canonical(incoming), canonical(target), signature,
                    digest_file(target), json.dumps(parent_details(record)), timestamp()))
        self.assertEqual(len(self.inbox.pending_filings()), 1)
        self.assertEqual(canonical(attachments(self.store, document)[0]["path"]), canonical(target))
        self.assertFalse(incoming.exists())

    def test_non_pdf_filing_attaches_si_without_a_pdf_service_handoff(self):
        document, record = self.parent()
        incoming = self.incoming / "support.docx"
        doc = Document()
        doc.add_paragraph("Supporting information")
        doc.save(incoming)
        with patch("note_organizer.sorting.core_logic.get_basic_document_details", return_value=parent_details(record)):
            review = self.ready(incoming)
        result = self.inbox.file_item(incoming, review["proposed_filename"], self.library)
        self.assertFalse(result["is_pdf"])
        self.assertEqual(canonical(attachments(self.store, document)[0]["path"]), result["path"])

    def test_old_confirmed_si_filings_are_migrated_on_open(self):
        document, record = self.parent()
        target = self.pdf("previous_SI.pdf", self.library)
        target.write_bytes(target.read_bytes().replace(b"%%EOF", b"%SI\n%%EOF"))
        with self.store.connect() as db:
            db.execute("""INSERT INTO inbox_jobs(id,source,path,signature,digest,details,state,created_at)
                VALUES(?,?,?,?,?,?,'handed_off',?)""", ("old-si", "old-source", canonical(target), "sig",
                    digest_file(target), json.dumps(parent_details(record)), timestamp()))
        self.assertEqual(attachments(self.store, document), [])
        reopened = Store(self.store.path)
        self.assertEqual(canonical(attachments(reopened, document)[0]["path"]), canonical(target))

    def test_stale_si_destination_does_not_delete_inbox_source(self):
        document, _ = self.parent()
        old = self.pdf("old_SI.pdf", self.library)
        old.write_bytes(old.read_bytes().replace(b"%%EOF", b"%SI\n%%EOF"))
        attach_file(self.store, document, old)
        old.unlink()
        incoming = self.pdf()
        self.ready(incoming)
        with self.assertRaisesRegex(ValueError, "different supplementary"):
            self.inbox.file_item(incoming, old.name, self.library)
        self.assertTrue(incoming.is_file())
        self.assertFalse(old.exists())


if __name__ == "__main__":
    unittest.main()
