"""Exact helper status smoke using only a disposable synthetic state directory."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
from note_organizer.zotero_worker import Worker
from note_organizer.zotero_review import fingerprint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--helper', type=Path, required=True)
    args = parser.parse_args()
    helper = args.helper.resolve(strict=True)
    helper_hash = hashlib.sha256(helper.read_bytes()).hexdigest()
    parent = root / '.test-tmp' / 'audit-status-package-smoke'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as state:
        worker = Worker(Path(state))
        records = [
            ('WAITPDF2', 'Waiting.PDF'), ('WORDKEY2', 'Filed.docx'),
            ('SLIDEKEY', 'Filed.pptx'), ('LINKED23', 'Linked.pdf'), ('PAUSED23', 'Paused.pdf')]
        for key, filename in records:
            digest = fingerprint(key)
            identity = worker.review.offer('zotero', key, digest, {'path': filename})
            worker.review.begin(identity, digest, {'filename': filename, 'source': key})
            worker.review.finish(identity)
        worker.state.write('documents', {
            'linked-pdf': {'source_key': 'LINKED23', 'revision': 'received'},
            'paused-pdf': {'source_key': 'PAUSED23'},
            'staged-pdf': {'origin': 'zotero', 'source_key': 'STAGED23', 'uploaded': False},
            'paused-staged': {'origin': 'zotero', 'source_key': 'PAUSEUP2', 'uploaded': False},
            'missing-staged': {'origin': 'zotero', 'source_key': 'MISSING2', 'uploaded': False, 'unavailable': True}})
        worker.review.link_control('paused-pdf', paused=True)
        worker.review.link_control('paused-staged', paused=True)
        worker.config['sync_paused'] = True
        worker.save()
        requests = [{'id': 1, 'method': 'status', 'params': {}}, {'id': 2, 'method': 'shutdown'}]
        result = subprocess.run([str(helper), '--state', state, '--debug-stacks'],
                                input=''.join(json.dumps(row) + '\n' for row in requests).encode('utf-8'),
                                capture_output=True, timeout=60, cwd=root)
        packets = [json.loads(line) for line in result.stdout.splitlines()]
        expected = {'approved_waiting_sync': 2, 'linked': 4, 'pdfs_received': 1}
        actual = next(row['result']['filing_summary'] for row in packets if row.get('id') == 1)
        record = {'helper': str(helper), 'helper_sha256': helper_hash, 'returncode': result.returncode,
                  'expected': expected, 'actual': actual,
                  'stderr': result.stderr.decode('utf-8', errors='replace')}
        target = Path(__file__).with_name('packaged-status-smoke-results.json')
        target.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(record, indent=2))
        if result.returncode != 0 or actual != expected:
            raise SystemExit('Packaged status smoke failed')


if __name__ == '__main__':
    main()
