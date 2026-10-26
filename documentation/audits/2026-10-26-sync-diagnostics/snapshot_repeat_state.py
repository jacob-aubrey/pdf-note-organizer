"""Read-only idle snapshots for this audit's repeat-sync comparison.

Uses the earlier reviewed bounded SQLite reader. Only selected identities and
receipts are stored privately; public evidence contains counts and hashes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / '.test-tmp/sync-diagnostics-20261026'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--compare')
    args = parser.parse_args()
    if not all(re.fullmatch(r'[a-z0-9-]{1,48}', value) for value in (args.label, args.compare or 'none')):
        parser.error('Use a short audit label')
    target = PRIVATE / ('repeat-state-' + args.label + '.json')
    public = Path(__file__).with_name('repeat-state-' + args.label + '.json')
    if target.exists() or public.exists():
        raise RuntimeError('Evidence label already exists')
    spec = importlib.util.spec_from_file_location('audit_state', ROOT / 'documentation/audits/2026-10-25/verify_sync_state.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    state = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default/notable'
    snapshot = audit.capture(state, 10)
    if snapshot['changed_during_capture']:
        raise RuntimeError('State changed during snapshot; wait until idle')
    fields = ('source_key', 'view_key', 'baseline', 'rendered', 'revision', 'page_map_digest', 'uploaded', 'tag_state', 'tag_pending')
    receipt_fields = ('source', 'parent', 'attachment', 'md5', 'pending_md5', 'indexed_sha', 'published')
    selected = {
        'documents': {key: {field: row.get(field) for field in fields} for key, row in snapshot['documents'].items()},
        'publications': {row['source']: {field: row.get(field) for field in receipt_fields}
                         for row in snapshot['db']['publisher']['tables'].get('publications', [])},
        'review_sha256': digest(snapshot['db']['review']['tables']),
        'config_sha256': digest(snapshot['config']),
    }
    result = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'label': args.label, 'mapping_count': len(selected['documents']),
              'publication_count': len(selected['publications']), 'selected_state_sha256': digest(selected)}
    if args.compare:
        old = json.loads((PRIVATE / ('repeat-state-' + args.compare + '.json')).read_text())
        comparison = {'baseline': args.compare}
        for table in ('documents', 'publications'):
            current, previous = selected[table], old[table]
            comparison[table] = {
                'added': len(set(current) - set(previous)), 'removed': len(set(previous) - set(current)),
                'changed_rows': sum(current[key] != previous[key] for key in set(current) & set(previous)),
                'changed_fields': {field: sum(current[key].get(field) != previous[key].get(field)
                                              for key in set(current) & set(previous))
                                   for field in (fields if table == 'documents' else receipt_fields)},
            }
        comparison['review_unchanged'] = old['review_sha256'] == selected['review_sha256']
        comparison['config_unchanged'] = old['config_sha256'] == selected['config_sha256']
        result['comparison'] = comparison
    target.write_text(json.dumps(selected, sort_keys=True) + '\n')
    public.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
