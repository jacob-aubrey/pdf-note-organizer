"""Offline source reconstruction and bounded disposable-cache regressions."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid
import zipfile

import fitz

from note_organizer.paper_registry import Registry
from note_organizer.remarkable_cloud import CloudClient, CloudError
from note_organizer.remarkable_pdf import annotated_pdf, UnsupportedAnnotations
from note_organizer import remarkable_sources
from note_organizer.remarkable_sources import (save_source_bundle, source_bundle, source_info,
                                             export_source_archive, source_storage_usage)
from note_organizer.remarkable_sync import RemarkableSync
from note_organizer.storage import Store
from tests.test_remarkable import fixture


class RemarkableSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data" / "library.sqlite3")
        self.item, self.bundle = fixture()
        self.private = self.store.path.parent / "remarkable"

    def tearDown(self):
        self.temp.cleanup()

    def test_offline_reconstruction_preserves_pdf_layers_page_info_and_metadata(self):
        self.bundle[self.item.id + ".metadata"] = b'{"visibleName":"Original title"}'
        manifest = save_source_bundle(self.store, self.item, self.bundle)
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)
        info = source_info(self.store, self.item.id)
        self.assertTrue(info["annotations_cached"])
        self.assertEqual(info["content"], json.loads(self.bundle[self.item.id + ".content"]))
        self.assertEqual(info["pdf_hash"], hashlib.sha256(self.bundle[self.item.id + ".pdf"]).hexdigest())
        with zipfile.ZipFile(self.private / manifest["layers"]) as archive:
            self.assertNotIn(self.item.id + ".pdf", archive.namelist())
        self.assertFalse((self.private / "sources" / (self.item.id + ".rmdoc")).exists())

    def test_identical_cloud_pdfs_share_one_baseline_and_repeated_layers_are_stable(self):
        first = save_source_bundle(self.store, self.item, self.bundle)
        again = save_source_bundle(self.store, self.item, self.bundle)
        self.assertEqual(first["layers_hash"], again["layers_hash"])
        second_id = str(uuid.uuid4())
        other = {name.replace(self.item.id, second_id): data for name, data in self.bundle.items()}
        second_item = replace(self.item, id=second_id)
        second = save_source_bundle(self.store, second_item, other)
        self.assertEqual(first["baseline"], second["baseline"])
        self.assertEqual(len(list((self.private / "baselines").glob("*.pdf"))), 1)
        self.assertEqual(len(list((self.private / "layers" / self.item.id).glob("*.zip"))), 1)
        self.assertEqual(source_bundle(self.store, second_id), other)

    def changed_bundle(self):
        changed = dict(self.bundle)
        with fitz.open(stream=changed[self.item.id + ".pdf"], filetype="pdf") as pdf:
            pdf[0].insert_text((60, 130), "New edition with a corrected result")
            changed[self.item.id + ".pdf"] = pdf.tobytes()
        content = json.loads(changed[self.item.id + ".content"])
        content["lastOpenedPage"] = 0
        changed[self.item.id + ".content"] = json.dumps(content).encode()
        revision = hashlib.sha256(b"".join(changed.values())).hexdigest()
        return replace(self.item, hash=revision), changed

    def test_revision_history_reconstructs_exact_old_and_new_baselines_and_layers(self):
        old = save_source_bundle(self.store, self.item, self.bundle)
        old_path = self.private / "sources" / "history" / self.item.id / (self.item.hash + ".json")
        old_bytes, old_time = old_path.read_bytes(), old_path.stat().st_mtime_ns
        item, changed = self.changed_bundle()
        new = save_source_bundle(self.store, item, changed)
        self.assertNotEqual(old["pdf_hash"], new["pdf_hash"])
        self.assertNotEqual(old["layers_hash"], new["layers_hash"])
        self.assertEqual(source_bundle(self.store, self.item.id), changed)
        self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
        self.assertEqual(source_bundle(self.store, self.item.id, revision=item.hash), changed)
        self.assertEqual(source_info(self.store, self.item.id, revision=self.item.hash)["cloud_hash"], self.item.hash)
        self.assertEqual(Path(source_info(self.store, self.item.id, revision=self.item.hash)["source_path"]), old_path)
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertEqual(old_path.stat().st_mtime_ns, old_time)
        # Re-fetching an older cloud revision must reuse its immutable manifest.
        repeated = save_source_bundle(self.store, self.item, self.bundle)
        self.assertEqual(repeated, old)
        self.assertEqual(old_path.read_bytes(), old_bytes)
        self.assertEqual(old_path.stat().st_mtime_ns, old_time)

    def test_pre_history_upgrade_publishes_both_revisions_before_latest_pointer(self):
        old = save_source_bundle(self.store, self.item, self.bundle)
        latest = self.private / "sources" / (self.item.id + ".json")
        history = self.private / "sources" / "history" / self.item.id
        (history / (self.item.hash + ".json")).unlink()
        old.pop("manifest_hash")
        latest.write_text(json.dumps(old), encoding="utf-8")
        self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
        item, changed = self.changed_bundle()
        writes = []
        real_write = remarkable_sources.atomic_write

        def checked_write(path, data, **kwargs):
            writes.append(Path(path))
            if Path(path) == latest:
                for revision in (self.item.hash, item.hash):
                    self.assertTrue((history / (revision + ".json")).is_file())
                self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
            return real_write(path, data, **kwargs)

        with patch.object(remarkable_sources, "atomic_write", side_effect=checked_write):
            save_source_bundle(self.store, item, changed)
        self.assertLess(writes.index(history / (self.item.hash + ".json")), writes.index(latest))
        self.assertLess(writes.index(history / (item.hash + ".json")), writes.index(latest))
        self.assertEqual(source_bundle(self.store, self.item.id), changed)

    def test_failed_conversion_of_new_revision_keeps_previous_exact_sources(self):
        save_source_bundle(self.store, self.item, self.bundle)
        item, changed = self.changed_bundle()
        stroke_name = next(name for name in changed if name.endswith(".rm"))
        changed[stroke_name] = b"Unsupported tablet scene bytes"
        item = replace(item, hash=hashlib.sha256(b"".join(changed.values())).hexdigest())
        save_source_bundle(self.store, item, changed)
        with self.assertRaises(UnsupportedAnnotations):
            annotated_pdf(item, source_bundle(self.store, item.id))
        self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
        self.assertEqual(source_bundle(self.store, item.id, revision=item.hash), changed)
        with fitz.open(stream=annotated_pdf(self.item, source_bundle(self.store, self.item.id, revision=self.item.hash)),
                       filetype="pdf") as pdf:
            self.assertEqual(len(list(pdf[0].annots())), 3)

    def test_history_is_immutable_and_conflicting_reuse_of_revision_fails_closed(self):
        saved = save_source_bundle(self.store, self.item, self.bundle)
        latest = self.private / "sources" / (self.item.id + ".json")
        before = latest.read_bytes()
        _, changed = self.changed_bundle()
        with self.assertRaisesRegex(CloudError, "different source references"):
            save_source_bundle(self.store, self.item, changed)
        self.assertEqual(latest.read_bytes(), before)
        self.assertEqual(source_bundle(self.store, self.item.id, revision=self.item.hash), self.bundle)
        self.assertTrue((self.private / saved["baseline"]).is_file())

    def test_history_tampering_and_revision_path_injection_are_rejected(self):
        saved = save_source_bundle(self.store, self.item, self.bundle)
        history = self.private / "sources" / "history" / self.item.id / (self.item.hash + ".json")
        original = history.read_bytes()
        tampered = json.loads(original)
        tampered["at"] = "changed timestamp"
        history.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(CloudError, "integrity"):
            source_bundle(self.store, self.item.id, revision=self.item.hash)
        history.write_bytes(original)
        for revision in ("../../Outside", "A" * 64, "g" * 64, self.item.hash + "\n", "", None, 25):
            if revision is None:
                continue  # None explicitly selects the latest version.
            with self.subTest(revision=revision), self.assertRaises(CloudError):
                source_bundle(self.store, self.item.id, revision=revision)
        unknown = "0" * 64
        with self.assertRaises(CloudError):
            source_info(self.store, self.item.id, revision=unknown)
        # Even a matching checksum cannot assign a baseline to a different path.
        tampered = dict(saved)
        tampered["baseline"] = "layers/" + self.item.id + "/" + saved["pdf_hash"] + ".pdf"
        tampered["manifest_hash"] = remarkable_sources._manifest_digest(tampered)
        history.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(CloudError, "baseline"):
            source_bundle(self.store, self.item.id, revision=self.item.hash)

    def test_legacy_archives_still_reconstruct_and_upgrade_does_not_modify_them(self):
        archive = self.private / "sources" / (self.item.id + ".rmdoc")
        archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive, "w") as zipped:
            for name, data in self.bundle.items():
                zipped.writestr(name, data)
        before = archive.read_bytes()
        self.assertTrue(source_info(self.store, self.item.id)["legacy"])
        self.assertEqual(source_bundle(self.store, self.item.id), self.bundle)
        with self.assertRaises(CloudError):
            source_bundle(self.store, self.item.id, revision=self.item.hash)
        self.assertEqual(archive.read_bytes(), before)
        save_source_bundle(self.store, self.item, self.bundle)
        self.assertEqual(archive.read_bytes(), before)
        self.assertFalse(source_info(self.store, self.item.id)["legacy"])

    def test_corrupt_baseline_is_preserved_and_reconstruction_fails_closed(self):
        manifest = save_source_bundle(self.store, self.item, self.bundle)
        baseline = self.private / manifest["baseline"]
        baseline.write_bytes(b"Changed baseline")
        with self.assertRaises(CloudError):
            source_bundle(self.store, self.item.id)
        with self.assertRaises(CloudError):
            save_source_bundle(self.store, self.item, self.bundle)
        self.assertEqual(baseline.read_bytes(), b"Changed baseline")

    def test_manifest_paths_cannot_read_outside_private_storage(self):
        manifest = save_source_bundle(self.store, self.item, self.bundle)
        manifest["baseline"] = "../../Outside.pdf"
        path = self.private / "sources" / (self.item.id + ".json")
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(CloudError):
            source_bundle(self.store, self.item.id)

    def test_explicit_portable_export_and_storage_accounting(self):
        save_source_bundle(self.store, self.item, self.bundle)
        output = self.root / "Portable.rmdoc"
        export_source_archive(self.store, self.item.id, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, self.bundle)
        with self.assertRaises(CloudError):
            export_source_archive(self.store, self.item.id, output)
        cache = self.private / "reading-cache"
        cache.mkdir()
        (cache / "combined.pdf").write_bytes(b"disposable reading PDF")
        usage = source_storage_usage(self.store)
        self.assertEqual(usage["baselines"], len(self.bundle[self.item.id + ".pdf"]))
        self.assertGreater(usage["layers"], 0)
        self.assertEqual(usage["reading-cache"], len(b"disposable reading PDF"))
        self.assertEqual(usage["total"], sum(usage[key] for key in usage if key != "total"))

    def test_render_provenance_proves_identity_mapping_and_rejects_added_pages(self):
        path = self.root / "rendered.pdf"
        path.write_bytes(self.bundle[self.item.id + ".pdf"])
        engine = RemarkableSync(self.store, threading.Event(), Mock())
        payload = {"state": "synced", "path": str(path), "digest": hashlib.sha256(path.read_bytes()).hexdigest()}
        engine.register_download(self.item, self.bundle, payload)
        metadata = Registry(self.store).local_for_cloud(self.item.id)[0]["metadata"]
        self.assertTrue(metadata["page_mapping_identity"])
        self.assertEqual(metadata["original_pdf_digest"], hashlib.sha256(path.read_bytes()).hexdigest())
        content = json.loads(self.bundle[self.item.id + ".content"])
        content["cPages"]["pages"].append({"id": "added", "idx": {"value": "bb"}})
        self.bundle[self.item.id + ".content"] = json.dumps(content).encode()
        engine.register_download(self.item, self.bundle, payload)
        self.assertFalse(Registry(self.store).local_for_cloud(self.item.id)[0]["metadata"]["page_mapping_identity"])

    def test_cache_limit_removes_only_disposable_blobs_and_retained_baseline_is_reused(self):
        manifest = save_source_bundle(self.store, self.item, self.bundle)
        cache = self.private / "blobs"
        cache.mkdir()
        for number in range(3):
            path = cache / (str(number) * 64)
            path.write_bytes(bytes([number]) * 100)
            os.utime(path, (number + 1, number + 1))
        marker = cache / "keep-non-cache-file.txt"
        marker.write_text("Retained", encoding="utf-8")
        client = CloudClient(cache_dir=cache, cache_limit_bytes=150)
        self.assertEqual(client.prune_cache(), 2)
        self.assertTrue(marker.is_file())
        self.assertTrue((self.private / manifest["baseline"]).is_file())
        client.baseline_dir = self.private / "baselines"
        client.get = Mock(side_effect=AssertionError("Retained source must be usable offline"))
        self.assertEqual(client.blob(manifest["pdf_hash"], self.item.id + ".pdf"), self.bundle[self.item.id + ".pdf"])
        client.get.assert_not_called()

    def test_new_pdf_and_stroke_downloads_do_not_duplicate_retained_data_in_blob_cache(self):
        cache = self.private / "blobs"
        client = CloudClient(cache_dir=cache)
        data = self.bundle[self.item.id + ".pdf"]
        digest = hashlib.sha256(data).hexdigest()
        client.get = Mock(return_value=data)
        self.assertEqual(client.blob(digest, self.item.id + ".pdf"), data)
        self.assertFalse(cache.exists())
        strokes = next(data for name, data in self.bundle.items() if name.endswith(".rm"))
        client.get.return_value = strokes
        client.blob(hashlib.sha256(strokes).hexdigest(), "page.rm")
        self.assertFalse(cache.exists())

    def test_corrupt_root_cache_is_refetched_before_any_cloud_write(self):
        cache = self.private / "blobs"
        cache.mkdir(parents=True)
        correct = b"4\n0:.:0:0\n"
        digest = hashlib.sha256(correct).hexdigest()
        (cache / digest).write_bytes(b"4\n")
        client = CloudClient(cache_dir=cache)
        client.get = Mock(return_value=correct)
        self.assertEqual(client.blob(digest, "root.docSchema"), correct)
        client.get.assert_called_once()
        client.get.return_value = b"4\n"
        (cache / digest).write_bytes(b"4\n")
        with self.assertRaises(CloudError):
            client.blob(digest, "root.docSchema")


if __name__ == "__main__":
    unittest.main()
