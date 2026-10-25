"""Isolated audit reproductions. Assertions describe observed defects, not fixes.

Run from repository root with: .venv/Scripts/python.exe -m unittest discover
  -s documentation/audits/2026-10-25 -p backend_repros.py -v
No account, production profile, or physical tablet is used.
"""
import unittest
from unittest.mock import patch
import uuid

from note_organizer.zotero_pilot import PilotError
from tests import test_zotero_worker as worker_fixtures
from tests import test_zotero_bridge as bridge_fixtures


class ConflictRecoveryRepro(unittest.TestCase):
    setUp = worker_fixtures.WorkerTests.setUp

    def test_lost_conflict_confirmation_leaves_an_unresumable_applying_review(self):
        child = self.cloud.create_folder('Topic', self.croot.id, str(uuid.uuid4()), self.croot.id)
        self.worker.sync()
        key = next(k for k, row in self.worker.state.read('folders').items() if row['cloud'] == child.id)
        self.zot.collection_records[key]['name'] = 'Desktop choice'
        self.cloud.update_item(child.id, expected_hash=child.hash, name='Tablet choice', scope_id=self.croot.id)
        self.worker.sync()
        review = next(row for row in self.worker.review.rows() if row['kind'] == 'conflict')
        update = self.cloud.update_item
        def commit_then_lose(*args, **kwargs):
            update(*args, **kwargs)
            raise OSError('Synthetic lost response after successful commit')
        with patch.object(self.cloud, 'update_item', side_effect=commit_then_lose):
            with self.assertRaises(OSError):
                self.worker.resolve_conflict(review['id'], review['digest'], 'desktop')
        self.assertEqual(next(item.name for item in self.cloud.library() if item.id == child.id), 'Desktop choice')
        with self.assertRaisesRegex(PilotError, 'changed since review'):
            self.worker.resolve_conflict(review['id'], review['digest'], 'desktop')
        self.worker.sync()
        current = self.worker.review.row(review['id'])
        self.assertEqual(current['status'], 'applying')
        with self.assertRaisesRegex(PilotError, 'current pending review'):
            self.worker.dismiss_review(review['id'], review['digest'])

    def test_interrupted_cloud_filing_overwrites_a_subsequent_tablet_rename(self):
        item = self.cloud.upload_pdf(worker_fixtures.pdf_bytes(), 'Tablet paper', self.croot.id,
                                     str(uuid.uuid4()), self.croot.id)
        self.worker.sync()
        row = next(row for row in self.worker.review.rows() if row['kind'] == 'cloud')
        args = (row['id'], row['digest'], 'Reviewed.pdf', 'Reviewed paper', 'journal_article', 'ROOT2345')
        with patch.object(self.worker.review, 'finish', side_effect=OSError('Synthetic interrupted completion')):
            with self.assertRaises(OSError):
                self.worker.approve(*args)
        self.assertEqual(self.worker.review.row(row['id'])['status'], 'applying')
        current = next(value for value in self.cloud.library() if value.id == item.id)
        self.cloud.update_item(item.id, expected_hash=current.hash, name='Later user rename', scope_id=self.croot.id)
        self.worker.approve(*args)
        self.assertEqual(next(value.name for value in self.cloud.library() if value.id == item.id), 'Reviewed')


class PartialDesktopMoveRepro(unittest.TestCase):
    setUp = bridge_fixtures.BridgeTests.setUp
    add_desktop = bridge_fixtures.BridgeTests.add_desktop

    def test_invalid_windows_name_is_validated_after_collection_membership_changes(self):
        self.add_desktop()
        row = {'parent': 'PARENT23', 'collection': 'ROOT2345', 'source_key': 'SOURCE23'}
        with self.assertRaises(ValueError):
            self.engine.set_desktop_document(row, 'Invalid:WindowsName', 'TARGET23', {})
        self.assertEqual(self.zot.items['PARENT23']['collections'], ['TARGET23'])


if __name__ == '__main__':
    unittest.main()
