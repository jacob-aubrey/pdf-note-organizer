"""Synthetic audit-verifier checks; no databases, APIs or user documents."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from verify_sync_state import retained_manifest_summary


class ManifestMeaningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / 'bridge/sources/remarkable/sources'
        self.sources.mkdir(parents=True)
        self.identity, self.baseline = 'synthetic-paper', 'b' * 64

    def write_manifest(self, revision, *, latest=True, history=True):
        info = {'id': self.identity, 'cloud_hash': revision, 'pdf_hash': self.baseline}
        info['manifest_hash'] = hashlib.sha256(json.dumps(info, sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        paths = []
        if latest:
            paths.append(self.sources / (self.identity + '.json'))
        if history:
            paths.append(self.sources / 'history' / self.identity / (revision + '.json'))
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(info), encoding='utf-8')

    def summarize(self, revision, **values):
        return retained_manifest_summary({'active': self.root, 'documents': {
            self.identity: {'revision': revision, 'baseline': self.baseline, **values}}})

    def test_exact_history_wins_over_a_newer_latest_pointer(self):
        self.write_manifest('a' * 64)
        self.write_manifest('c' * 64)
        result = self.summarize('a' * 64)
        self.assertEqual(result['mapping_revision_history_present'], 1)
        self.assertEqual(result['mapping_revision_matches_selected_source'], 1)
        self.assertEqual(result['selected_latest_manifest_fallback'], 0)

    def test_post_tag_mapping_revision_is_not_a_missing_source_claim(self):
        self.write_manifest('a' * 64)
        result = self.summarize('c' * 64, tag_state={'paper': ['Synthetic'], 'pages': {}})
        self.assertEqual(result['present'], 1)
        self.assertEqual(result['mapping_revision_history_present'], 0)
        self.assertEqual(result['mapping_revision_differs_from_selected_source'], 1)
        self.assertEqual(result['different_revision_with_completed_tag_state'], 1)
        self.assertEqual(result['selected_source_revision_history_present'], 1)
        self.assertEqual(result['self_hash_valid'], 1)
        self.assertNotIn('missing', result)

    def test_legacy_latest_can_match_without_immutable_history(self):
        self.write_manifest('a' * 64, history=False)
        result = self.summarize('a' * 64)
        self.assertEqual(result['mapping_revision_matches_selected_source'], 1)
        self.assertEqual(result['selected_source_revision_history_present'], 0)

    def test_backup_exclusion_is_not_reported_as_missing(self):
        result = retained_manifest_summary({'active': self.root, 'documents': {}}, source_files_expected=False)
        self.assertFalse(result['checked'])
        self.assertNotIn('missing', result)

    def test_no_history_or_latest_manifest_still_reports_missing(self):
        result = self.summarize('a' * 64)
        self.assertEqual(result['missing'], 1)
        self.assertNotIn('present', result)


if __name__ == '__main__':
    unittest.main()
