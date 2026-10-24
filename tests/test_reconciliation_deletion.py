"""Deletion reuses the completed check and updates only related papers."""
from unittest.mock import patch

from note_organizer import reconciliation
from note_organizer.storage import canonical
from note_organizer.paper_registry import Registry
from tests.test_paper_reconciliation import ReconciliationFixture, pdf_bytes


class ReviewDeletionTests(ReconciliationFixture):
    def assert_matches_fresh_check(self, rows):
        self.assertEqual(sorted(rows, key=lambda row: row["id"]),
                         sorted(self.scan(), key=lambda row: row["id"]))

    def test_cross_folder_duplicates_update_without_reading_unrelated_pdfs(self):
        data = pdf_bytes(title="First paper")
        first = self.local_pdf("first.pdf", data)
        second = self.local_pdf("Elsewhere/second.pdf", data)
        third = self.local_pdf("third.pdf", data)
        other_data = pdf_bytes(title="Unrelated paper")
        self.local_pdf("other-one.pdf", other_data)
        self.local_pdf("other-two.pdf", other_data)
        rows = self.scan()
        unrelated = next(row for row in rows if row["kind"] == "local_duplicate" and "other-one.pdf" in str(row["local_paths"]))
        folder_rows = [row for row in rows if "folder" in row["kind"]]
        second.unlink()
        with patch.object(reconciliation, "_local_info", side_effect=AssertionError("PDF reread")), \
                patch.object(reconciliation, "_archive_info", side_effect=AssertionError("Archive reread")), \
                patch.object(reconciliation.Path, "rglob", side_effect=AssertionError("Folder rescan")), \
                patch.object(reconciliation, "_compare_sources", wraps=reconciliation._compare_sources) as compare:
            updated = rows.snapshot.after_delete(rows, [str(second)])
        self.assertEqual({item["path"] for item in compare.call_args.args[0]}, {canonical(first), canonical(third)})
        self.assertTrue(any(row is unrelated for row in updated))
        self.assertTrue(all(any(row is folder for row in updated) for folder in folder_rows))
        self.assert_matches_fresh_check(updated)
        # The updated snapshot remembers prior removals across further actions.
        third.unlink()
        updated = updated.snapshot.after_delete(updated, [str(third)])
        self.assert_matches_fresh_check(updated)

    def test_deleting_exact_match_reveals_cached_title_candidate(self):
        original = pdf_bytes()
        exact = self.local_pdf("exact.pdf", original)
        candidate = self.local_pdf("candidate.pdf", pdf_bytes(note="Different revision"))
        self.cloud_pdf(data=original)
        rows = self.scan()
        self.assertEqual(next(row for row in rows if row["kind"] == "paper_match")["local_paths"], [canonical(exact)])
        exact.unlink()
        updated = rows.snapshot.after_delete(rows, [str(exact)])
        match = next(row for row in updated if row["kind"] == "possible_paper_match")
        self.assertEqual(match["local_paths"], [canonical(candidate)])
        self.assert_matches_fresh_check(updated)

    def test_deleting_last_local_copy_retains_cloud_and_folder_findings(self):
        original = pdf_bytes()
        local = self.local_pdf("paper.pdf", original)
        self.cloud_pdf(data=original)
        rows = self.scan()
        local.unlink()
        updated = rows.snapshot.after_delete(rows, [str(local)])
        self.assertTrue(any(row["kind"] == "cloud_cached_only" for row in updated))
        self.assert_matches_fresh_check(updated)

    def test_only_successfully_deleted_paths_are_removed(self):
        data = pdf_bytes()
        paths = [self.local_pdf(f"copy-{index}.pdf", data) for index in range(3)]
        rows = self.scan()
        paths[2].unlink()
        updated = rows.snapshot.after_delete(rows, [str(paths[2])])
        duplicate = next(row for row in updated if row["kind"] == "local_duplicate")
        self.assertEqual(set(duplicate["local_paths"]), {canonical(path) for path in paths[:2]})
        self.assert_matches_fresh_check(updated)

    def test_confirmed_link_survives_deletion_of_the_exact_original(self):
        original = pdf_bytes(title="Original")
        exact = self.local_pdf("original.pdf", original)
        other = self.local_pdf("other.pdf", pdf_bytes(title="Renamed edition", note="Independent note"))
        self.cloud_pdf(data=original, name="Different tablet name")
        registry = Registry(self.store)
        sources = [registry.register_local(path) for path in (exact, other)]
        sources.append(registry.register_cloud("cloud-paper"))
        registry.link_sources([source["id"] for source in sources])
        rows = self.scan()
        exact.unlink()
        updated = rows.snapshot.after_delete(rows, [str(exact)])
        match = next(row for row in updated if row["kind"] == "paper_match")
        self.assertEqual(match["basis"], "confirmed_link")
        self.assertEqual(match["local_paths"], [canonical(other)])
        self.assert_matches_fresh_check(updated)
