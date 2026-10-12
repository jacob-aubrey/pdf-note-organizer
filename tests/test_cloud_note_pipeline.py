"""Disposable libraries exercise source independence, migration and rebuilds."""
import hashlib
import json
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import fitz

from note_organizer.cloud_notes import document_path, save_cloud_notes
from note_organizer.combined_pdf import materialize_combined
from note_organizer.extraction import extract, scan_fingerprint
from note_organizer.paper_registry import Registry
from note_organizer.remarkable_cloud import CloudError
from note_organizer.remarkable_pdf import annotated_pdf, RENDER_REVISION
from note_organizer.remarkable_sources import save_source_bundle, source_info
from note_organizer.remarkable_sync import RemarkableSync, default_config
from note_organizer.service import Service
from note_organizer.storage import Store, DEFAULT_SETTINGS, canonical, digest_file
from note_organizer.view_state import read_view
from tests.test_remarkable import fixture, folder


class CloudNotePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pc = self.root / 'Literature'
        self.pc.mkdir()
        self.store = Store(self.root / 'data' / 'library.sqlite3')
        self.source = folder('Literature')
        self.item, self.bundle = fixture(self.source.id)
        self.sync = RemarkableSync(self.store, threading.Event(), Mock())
        self.sync.client = Mock()
        self.sync.client.library.return_value = [self.source, self.item]
        self.sync.client.pdf_bundle.return_value = self.bundle
        self.store.set_preference('remarkable', {**default_config(self.store.path.parent),
            'integration_enabled': True, 'enabled': True, 'pc_root': str(self.pc)})

    def tearDown(self):
        self.temp.cleanup()

    def run_sync(self):
        self.assertTrue(self.sync.sync())
        saved = self.store.remarkable_items()[self.item.id]
        self.assertEqual(saved['state'], 'synced', saved.get('reason'))
        return saved

    def test_new_cloud_paper_publishes_one_original_and_saves_notes_without_render(self):
        saved = self.run_sync()
        main = Path(saved['path'])
        self.assertEqual(list(self.pc.glob('*.pdf')), [main])
        self.assertEqual(main.read_bytes(), self.bundle[self.item.id + '.pdf'])
        self.assertFalse(document_path(self.store, self.item.id).exists())
        service = Service(self.store)
        service.sync()
        self.assertEqual(len(read_view(self.store.path).documents()), 1)
        entries = self.store.entries()
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(entry['source_link_path'] == canonical(main) for entry in entries))
        self.assertTrue(all(not entry['missing'] for entry in entries))
        self.assertTrue(any(entry['kind'] == 'drawing' and entry['image'] for entry in entries))

    def test_pc_and_tablet_notes_stay_independent_and_combined_pdf_contains_both(self):
        main = self.pc / (self.item.name + '.pdf')
        main.write_bytes(self.bundle[self.item.id + '.pdf'])
        with fitz.open(main) as pdf:
            pdf[0].add_text_annot((70, 160), 'PC only note')
            data = pdf.tobytes()
        main.write_bytes(data)
        self.run_sync()
        service = Service(self.store)
        service.sync()
        entries = self.store.entries()
        self.assertEqual(sum(entry['comment'] == 'PC only note' for entry in entries), 1)
        self.assertEqual(sum(entry['comment'] == 'Typed margin note' for entry in entries), 1)
        self.assertEqual(main.read_bytes(), data)
        with fitz.open(materialize_combined(self.store, main)) as pdf:
            comments = [annotation.info.get('content') for annotation in pdf[0].annots()]
        self.assertIn('PC only note', comments)
        self.assertIn('Typed margin note', comments)

    def test_inherited_pc_note_is_not_reextracted_as_tablet_note(self):
        raw = self.bundle[self.item.id + '.pdf']
        with fitz.open(stream=raw, filetype='pdf') as pdf:
            pdf[0].add_text_annot((70, 160), 'Already on PC')
            raw = pdf.tobytes()
        self.bundle[self.item.id + '.pdf'] = raw
        main = self.pc / (self.item.name + '.pdf')
        main.write_bytes(raw)
        self.run_sync()
        Service(self.store).sync()
        self.assertEqual(sum(entry['comment'] == 'Already on PC' for entry in self.store.entries()), 1)

    def test_native_import_note_missing_from_pc_requires_review_instead_of_disappearing(self):
        raw = self.bundle[self.item.id + '.pdf']
        main = self.pc / (self.item.name + '.pdf')
        main.write_bytes(raw)
        with fitz.open(stream=raw, filetype='pdf') as pdf:
            pdf[0].add_text_annot((70, 160), 'Native note only in tablet import')
            self.bundle[self.item.id + '.pdf'] = pdf.tobytes()
        self.item = replace(self.item, hash=hashlib.sha256(b''.join(self.bundle.values())).hexdigest())
        self.sync.client.library.return_value = [self.source, self.item]
        self.sync.sync()
        saved = self.store.remarkable_items()[self.item.id]
        self.assertEqual(saved['state'], 'review')
        self.assertEqual(main.read_bytes(), raw)
        with fitz.open(saved['review_pdf']) as pdf:
            self.assertIn('Native note only in tablet import', [note.info.get('content') for note in pdf[0].annots()])

    def test_legacy_document_id_and_history_survive_migration_and_scan(self):
        project = self.store.add_project(self.pc)
        legacy = self.pc / f'{self.item.name} [reMarkable {self.item.id[:8]}].pdf'
        legacy.write_bytes(annotated_pdf(self.item, self.bundle))
        digest, signature, metadata, entries = extract(legacy, DEFAULT_SETTINGS)
        self.store.save_scan(project, legacy, digest, signature, scan_fingerprint(DEFAULT_SETTINGS), metadata, entries)
        doc_id = self.store.document_at(project, legacy)['id']
        history = self.store.history(doc_id)
        self.store.save_remarkable_item(self.item.id, {'hash': self.item.hash, 'state': 'synced',
            'path': canonical(legacy), 'digest': digest, 'render_revision': RENDER_REVISION, 'name': self.item.name})
        self.sync.register_download(self.item, self.bundle, self.store.remarkable_items()[self.item.id])
        saved = self.run_sync()
        self.assertTrue(legacy.exists())
        self.assertEqual(saved['legacy_document_ids'], [doc_id])
        self.assertEqual(self.store.document_at(project, document_path(self.store, self.item.id))['id'], doc_id)
        self.assertTrue(all(row in self.store.history(doc_id) for row in history))
        Service(self.store).sync()
        self.assertEqual(len(read_view(self.store.path).documents()), 1)
        self.assertEqual(len(self.store.entries()), 3)
        from note_organizer.source_storage import plan_legacy_cleanup, execute_legacy_cleanup
        plan = plan_legacy_cleanup(self.store)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]['status'], 'ready', plan[0]['reasons'])
        notes_before, history_before = self.store.entries(), self.store.history(doc_id)
        result = execute_legacy_cleanup(self.store, plan, external_links_acknowledged=True)
        self.assertEqual(result[0]['status'], 'removed', result)
        self.assertFalse(legacy.exists())
        self.assertTrue(Path(saved['main_path']).exists())
        self.assertEqual(self.store.entries(), notes_before)
        self.assertEqual(self.store.history(doc_id), history_before)
        self.assertTrue(materialize_combined(self.store, saved['main_path']).exists())

    def test_edited_legacy_pdf_is_preserved_for_review(self):
        legacy = self.pc / f'{self.item.name} [reMarkable {self.item.id[:8]}].pdf'
        legacy.write_bytes(annotated_pdf(self.item, self.bundle))
        digest = digest_file(legacy)
        self.store.save_remarkable_item(self.item.id, {'hash': self.item.hash, 'state': 'synced',
            'path': canonical(legacy), 'digest': digest, 'render_revision': 0, 'name': self.item.name})
        with legacy.open('ab') as stream:
            stream.write(b'\nPC edit')
        expected = legacy.read_bytes()
        self.sync.sync()
        self.assertEqual(self.store.remarkable_items()[self.item.id]['state'], 'review')
        self.assertEqual(legacy.read_bytes(), expected)
        self.assertFalse(self.store.documents())

    def test_interrupted_manifest_publication_recovers_migrated_document_ids_on_retry(self):
        project = self.store.add_project(self.pc)
        legacy = self.pc / f'{self.item.name} [reMarkable {self.item.id[:8]}].pdf'
        legacy.write_bytes(annotated_pdf(self.item, self.bundle))
        digest, signature, metadata, entries = extract(legacy, DEFAULT_SETTINGS)
        self.store.save_scan(project, legacy, digest, signature, scan_fingerprint(DEFAULT_SETTINGS), metadata, entries)
        doc_id = self.store.document_at(project, legacy)['id']
        history = self.store.history(doc_id)
        self.store.save_remarkable_item(self.item.id, {'hash': self.item.hash, 'state': 'synced',
            'path': canonical(legacy), 'digest': digest, 'render_revision': RENDER_REVISION, 'name': self.item.name})
        self.sync.register_download(self.item, self.bundle, self.store.remarkable_items()[self.item.id])
        original_save = self.store.save_remarkable_item
        def interrupted(cloud_id, payload):
            if payload.get('storage_version') == 2:
                raise RuntimeError('Synthetic interrupted sync record publication')
            return original_save(cloud_id, payload)
        with patch.object(self.store, 'save_remarkable_item', side_effect=interrupted):
            self.sync.sync()
        self.assertEqual(self.store.document_at(project, document_path(self.store, self.item.id))['id'], doc_id)
        saved = self.run_sync()
        self.assertEqual(saved['legacy_document_ids'], [doc_id])
        self.assertTrue(all(row in self.store.history(doc_id) for row in history))
        self.assertEqual(len(Registry(self.store).local_for_cloud(self.item.id)), 2)

    def test_different_pc_edition_is_reviewed_without_modifying_original(self):
        main = self.pc / (self.item.name + '.pdf')
        with fitz.open() as pdf:
            pdf.new_page().insert_text((30, 50), 'A different paper version')
            data = pdf.tobytes()
        main.write_bytes(data)
        self.sync.sync()
        self.assertEqual(self.store.remarkable_items()[self.item.id]['state'], 'review')
        self.assertEqual(main.read_bytes(), data)
        self.assertEqual(len(list(self.pc.glob('*.pdf'))), 1)

    def test_cache_can_be_removed_and_view_rebuilt_offline_without_changing_notes(self):
        saved = self.run_sync()
        before = self.store.entries()
        path = materialize_combined(self.store, saved['main_path'])
        path.unlink()
        self.sync.client.pdf_bundle.side_effect = AssertionError('Offline reconstruction must not download')
        rebuilt = materialize_combined(self.store, saved['main_path'])
        self.assertTrue(rebuilt.exists())
        self.assertEqual(self.store.entries(), before)

    def test_failed_extraction_keeps_old_entries_and_history(self):
        saved = self.run_sync()
        project = self.store.projects()[0]['id']
        anchor = document_path(self.store, self.item.id)
        doc_id = self.store.document_at(project, anchor)['id']
        before, history = self.store.entries(), self.store.history(doc_id)
        with self.assertRaises(RuntimeError):
            save_cloud_notes(self.store, self.item, self.bundle, saved['main_path'], old=saved,
                             extractor=Mock(side_effect=RuntimeError('Synthetic failure')))
        self.assertEqual(self.store.entries(), before)
        self.assertEqual(self.store.history(doc_id), history)

    def test_reconnecting_moved_watched_folder_updates_private_note_paths(self):
        saved = self.run_sync()
        Service(self.store).sync()
        project = self.store.projects()[0]
        moved = self.root / 'Moved Literature'
        self.pc.rename(moved)
        self.store.relocate_project(project['id'], moved)
        new_main = canonical(moved / Path(saved['main_path']).name)
        self.assertEqual(self.store.remarkable_items()[self.item.id]['main_path'], new_main)
        entries = self.store.entries()
        self.assertTrue(entries)
        self.assertTrue(all(entry['path'] == new_main and entry['source_link_path'] == new_main for entry in entries))
        self.assertTrue(materialize_combined(self.store, new_main).exists())

    def test_local_settings_refreshes_tablet_notes_and_new_parent_membership_offline(self):
        self.run_sync()
        project = self.store.projects()[0]
        settings = {**DEFAULT_SETTINGS, 'grouping': 'Whole page', 'context_padding': 80}
        self.store.set_settings(project['id'], settings)
        parent = self.store.add_project(self.root)
        self.sync.client.pdf_bundle.side_effect = AssertionError('Local refresh must not download')
        Service(self.store).sync()
        anchor = document_path(self.store, self.item.id)
        self.assertEqual(self.store.document_at(project['id'], anchor)['settings'], scan_fingerprint(settings))
        self.assertIsNotNone(self.store.document_at(parent, anchor))

    def test_pc_edit_during_version_check_is_not_accepted_as_verified(self):
        main = self.pc / (self.item.name + '.pdf')
        main.write_bytes(self.bundle[self.item.id + '.pdf'])
        def raced(path, item, bundle):
            with Path(path).open('ab') as stream:
                stream.write(b'\nConcurrent edit')
            return b'unused'
        self.sync.combined_renderer = raced
        self.sync.sync()
        saved = self.store.remarkable_items()[self.item.id]
        self.assertEqual(saved['state'], 'review')
        self.assertIn('changed during version', saved['reason'])

    def test_failed_new_revision_does_not_replace_accepted_notes_or_offline_view(self):
        saved = self.run_sync()
        self.bundle[next(name for name in self.bundle if name.endswith('.rm'))] = b'New unsupported layer'
        newer = replace(self.item, hash=hashlib.sha256(b'new cloud revision').hexdigest())
        self.sync.client.library.return_value = [self.source, newer]
        self.sync.renderer = Mock(side_effect=BrokenProcessPool('Synthetic process failure'))
        self.sync.sync()
        self.assertEqual(self.store.remarkable_items()[self.item.id], saved)
        self.assertEqual(source_info(self.store, self.item.id)['cloud_hash'], newer.hash)
        Service(self.store).sync(force=True)
        for project in self.store.projects():
            self.assertEqual(self.store.document_at(project['id'], document_path(self.store, self.item.id))['signature'], self.item.hash)
        with fitz.open(materialize_combined(self.store, saved['main_path'])) as pdf:
            self.assertIn('Typed margin note', [note.info.get('content') for note in pdf[0].annots()])

    def test_unresolved_review_stays_unresolved_when_cloud_source_is_unavailable(self):
        saved = self.run_sync()
        self.store.save_remarkable_item(self.item.id, {**saved, 'state': 'cloud unavailable',
            'reason_kind': 'conversion', 'reason': 'Outside the selected source'})
        with patch('note_organizer.cloud_notes.save_cloud_notes') as refresh:
            Service(self.store).sync(force=True)
        refresh.assert_not_called()

    def test_changed_folder_membership_preserves_old_records_for_review(self):
        saved = self.run_sync()
        self.store.add_project(self.root)
        before = self.store.entries()
        with self.assertRaisesRegex(CloudError, 'different watched folder'):
            save_cloud_notes(self.store, self.item, self.bundle, self.root / 'Other' / 'article.pdf', old=saved)
        self.assertEqual(self.store.entries(), before)

    def test_legacy_review_reason_survives_cloud_item_becoming_unavailable(self):
        saved = self.run_sync()
        saved.pop('reason_kind')
        self.store.save_remarkable_item(self.item.id, {**saved, 'state': 'review',
            'reason': 'Annotation conversion needs review: unsupported layer'})
        self.sync.client.library.return_value = [self.source]
        self.sync.sync()
        unavailable = self.store.remarkable_items()[self.item.id]
        self.assertEqual(unavailable['state'], 'cloud unavailable')
        self.assertEqual(unavailable['reason_kind'], 'conversion')
        with self.assertRaisesRegex(CloudError, 'waiting for review'):
            materialize_combined(self.store, saved['main_path'])
