"""Read only native item versions, never item bodies; finite local requests.

Use after a completed sync. IDs/versions stay in ignored private evidence;
the public result contains only counts and hashes. No grants are printed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from note_organizer.remarkable_cloud import TokenVault
from note_organizer.zotero_pilot import LocalZotero


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--compare')
    args = parser.parse_args()
    if not all(re.fullmatch(r'[a-z0-9-]{1,48}', value) for value in (args.label, args.compare or 'none')):
        parser.error('Use a short audit label')
    private = ROOT / '.test-tmp/sync-diagnostics-20261026'
    target = private / ('native-versions-' + args.label + '.json')
    if target.exists():
        raise RuntimeError('Evidence label already exists; use a new label')
    state = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default/notable'
    client = LocalZotero(grant_store=TokenVault(state / 'zotero-grant.dpapi'), interactive=False)
    try:
        versions = client.zot.item_versions()
    finally:
        client.close()
    if not isinstance(versions, dict) or not all(re.fullmatch(r'[A-Z0-9]{8}', key) and isinstance(value, int) for key, value in versions.items()):
        raise RuntimeError('Unexpected native version response; no item bodies were requested')
    target.write_text(json.dumps(versions, sort_keys=True))
    result = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'label': args.label, 'item_count': len(versions), 'keys_sha256': digest(sorted(versions)),
              'versions_sha256': digest(versions)}
    if args.compare:
        old = json.loads((private / ('native-versions-' + args.compare + '.json')).read_text())
        result['comparison'] = {'baseline': args.compare, 'added_keys': len(set(versions) - set(old)),
                                'removed_keys': len(set(old) - set(versions)),
                                'changed_versions': sum(old[key] != versions[key] for key in set(old) & set(versions))}
    Path(__file__).with_name('native-versions-' + args.label + '.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
