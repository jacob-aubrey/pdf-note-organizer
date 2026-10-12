"""Worker regressions for hidden documents and queued reMarkable edits."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from note_organizer.extraction import extract
from note_organizer.remarkable_sync import default_config
from note_organizer.service import Service
from note_organizer.storage import Store
from tests.test_notebook import sample_pdf


class ServiceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.service = Service(self.store)

    def tearDown(self):
        self.service.stop()
        self.temp.cleanup()

    def run_queued_cloud_edits(self):
        # The first cloud check is a barrier after queued edits. Stop there so
        # this exercises the real worker loop without network or timers.
        self.service.remarkable.sync = Mock(side_effect=lambda *args, **kwargs: self.service.stop() or False)
        self.service.run()

    def test_unchanged_hidden_source_is_restored_and_exported(self):
        watched = self.root / "Research"
        watched.mkdir()
        pdf = watched / "paper.pdf"
        sample_pdf(pdf)
        pid = self.store.add_project(watched)
        self.service.scan(self.store.project(pid), pdf)
        initial = self.store.entries(project_id=pid)
        document_id = self.store.document_at(pid, pdf)["id"]
        self.assertTrue(initial)

        # Relocation outside this project hides its old rows. A preserved local
        # copy can still exist at the old path and must become readable again.
        self.store.relocate_source(pdf, self.root / "Elsewhere" / "paper.pdf")
        self.assertTrue(self.store.document_at(pid, pdf)["hidden"])
        self.assertFalse(self.store.entries(project_id=pid))
        self.assertTrue(pdf.exists())
        self.store.export_result(pid, "hidden-notebook-version")
        self.assertFalse(self.store.project(pid)["dirty"])

        with patch("note_organizer.service.extract", wraps=extract) as reader:
            self.service.scan(self.store.project(pid), pdf)
        reader.assert_called_once()
        restored = self.store.document_at(pid, pdf)
        self.assertFalse(restored["hidden"])
        self.assertEqual(restored["id"], document_id)
        self.assertEqual({e["key"] for e in self.store.entries(project_id=pid)}, {e["key"] for e in initial})
        self.assertTrue(self.store.project(pid)["dirty"])

        with patch("note_organizer.service.export_notebook", return_value=("restored-notebook-version", None)) as writer:
            self.service.export_pending()
        writer.assert_called_once()
        self.assertEqual({e["key"] for e in writer.call_args.args[2]}, {e["key"] for e in initial})
        self.assertFalse(self.store.project(pid)["dirty"])

    def test_queued_partial_settings_preserve_each_other_and_existing_routes(self):
        config = {**default_config(self.store.path.parent), "pc_root": str(self.root / "Original"),
                  "source_folder_id": "literature-id", "mappings": {"existing-folder": str(self.root / "Mapped")}}
        self.store.set_preference("remarkable", config)
        self.service.command("remarkable_settings", {"enabled": True})
        self.service.command("remarkable_settings", {"pc_root": str(self.root / "New sorted")})
        self.run_queued_cloud_edits()
        saved = self.store.preference("remarkable")
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["pc_root"], str(self.root / "New sorted"))
        self.assertEqual(saved["source_folder_id"], config["source_folder_id"])
        self.assertEqual(saved["mappings"], config["mappings"])
        self.assertEqual(saved["review_dir"], config["review_dir"])

    def test_queued_map_mutations_preserve_latest_settings_and_other_mappings(self):
        config = {**default_config(self.store.path.parent), "pc_root": str(self.root / "Original"),
                  "mappings": {"remove-folder": str(self.root / "Old mapped")}}
        self.store.set_preference("remarkable", config)
        self.service.command("remarkable_settings", {"enabled": True, "source_folder_id": "new-literature-id"})
        self.service.command("remarkable_map", "folder-a", str(self.root / "Original" / "A"))
        self.service.command("remarkable_map", "folder-b", str(self.root / "Original" / "B"))
        self.service.command("remarkable_map", "remove-folder", None)
        self.service.command("remarkable_settings", {"pc_root": str(self.root / "New sorted")})
        self.run_queued_cloud_edits()
        saved = self.store.preference("remarkable")
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["source_folder_id"], "new-literature-id")
        self.assertEqual(saved["pc_root"], str(self.root / "New sorted"))
        self.assertEqual(saved["mappings"], {"folder-a": str(self.root / "Original" / "A"),
                                           "folder-b": str(self.root / "Original" / "B")})
        self.assertEqual(saved["review_dir"], config["review_dir"])

    def test_unlink_source_stops_downloads_and_preserves_pdfs_notes_and_pairing(self):
        watched = self.root / "Sorted"
        watched.mkdir()
        pdf = watched / "paper.pdf"
        pdf.write_bytes(b"existing PDF; the test never processes it")
        project = self.store.add_project(watched)
        self.store.save_scan(project, pdf, "digest", "signature", "settings", {},
                             [{"key": "quote", "kind": "highlight", "quote": "Saved annotation", "page": 1,
                               "rect": [1, 1, 20, 20]}])
        entries = self.store.entries()
        vault = self.service.remarkable.vault.path
        vault.parent.mkdir(parents=True, exist_ok=True)
        vault.write_bytes(b"synthetic pairing placeholder")
        config = {**default_config(self.store.path.parent), "pc_root": str(watched), "enabled": True,
                  "source_folder_id": "literature", "mappings": {"literature": str(watched), "other": "Other PC folder"}}
        self.store.set_preference("remarkable", config)
        self.service.command("remarkable_unlink", "literature")
        with patch.object(self.service, "check_cloud", side_effect=lambda: self.service.stop() or False):
            self.service.run()
        saved = self.store.preference("remarkable")
        self.assertEqual(saved["pc_root"], "")
        self.assertFalse(saved["enabled"])
        self.assertEqual(saved["source_folder_id"], "literature")
        self.assertEqual(saved["mappings"], {"other": "Other PC folder"})
        self.assertEqual(self.store.entries(), entries)
        self.assertEqual(pdf.read_bytes(), b"existing PDF; the test never processes it")
        self.assertEqual(vault.read_bytes(), b"synthetic pairing placeholder")

    def test_unlink_override_keeps_source_and_other_overrides(self):
        config = {**default_config(self.store.path.parent), "pc_root": "Sorted", "enabled": True,
                  "source_folder_id": "literature", "mappings": {"remove": "Mapped A", "keep": "Mapped B"}}
        self.store.set_preference("remarkable", config)
        self.service.command("remarkable_unlink", "remove")
        with patch.object(self.service, "check_cloud", side_effect=lambda: self.service.stop() or False):
            self.service.run()
        saved = self.store.preference("remarkable")
        self.assertEqual(saved["pc_root"], "Sorted")
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["mappings"], {"keep": "Mapped B"})


if __name__ == "__main__":
    unittest.main()
