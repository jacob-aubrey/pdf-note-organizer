"""Read-only live catalog and sampled blob check for this audit's uploads.

Uses the existing saved grant; never prints it or changes cloud documents.
Only cloud metadata, baseline digests, and aggregate results are recorded.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from note_organizer.remarkable_cloud import CloudClient, TokenVault


def documents(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as db:
        row = db.execute("SELECT value FROM bridge_values WHERE key='documents'").fetchone()
        return json.loads(row[0])


def main():
    private = ROOT / '.test-tmp/full-audit-20261025'
    state = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default/notable'
    before = documents(private / 'pre-085-backup-complete/notable/bridge/pilot.sqlite3')
    after = documents(private / 'post-086-state-snapshot/bridge/pilot.sqlite3')
    expected = {key: after[key] for key, row in before.items()
                if row.get('uploaded') is False and after.get(key, {}).get('uploaded') is True}
    token = TokenVault(state / 'tablet-token.dpapi').load()
    if not token:
        raise RuntimeError('The existing reMarkable connection is unavailable')
    client = CloudClient(token, cache_dir=state / 'blobs')
    catalog = client.library()
    active = {row.id: row for row in catalog if row.is_pdf and not row.deleted}
    present = {key: active[key] for key in expected if key in active}
    matching = {key for key, row in present.items()
                if any(file['id'] == key + '.pdf' and file['hash'] == expected[key]['baseline']
                       for file in row.files)}
    uploaded = {key: row for key, row in after.items() if row.get('uploaded') is True}
    candidates = []
    for key in sorted(matching):
        original = state / 'bridge/originals' / (expected[key]['baseline'] + '.pdf')
        if original.is_file():
            candidates.append((original.stat().st_size, key))
    # Read three small baselines from the server without a local blob cache.
    sampled = []
    fresh = CloudClient(token)
    for size, key in sorted(candidates)[:3]:
        if size > 32 * 1024 * 1024:
            continue
        data = fresh.blob(expected[key]['baseline'], key + '.pdf')
        sampled.append({'bytes': len(data), 'sha256_matches':
                        hashlib.sha256(data).hexdigest() == expected[key]['baseline']})
    result = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'cloud_read_only': True,
              'catalog_items': len(catalog), 'active_pdfs': len(active),
              'expected_newly_uploaded_identities': len(expected),
              'present_active_cloud_identities': len(present),
              'cloud_pdf_blob_digests_match': len(matching), 'fresh_remote_blob_samples': sampled,
              'all_uploaded_mapping_identities': len(uploaded),
              'all_uploaded_mapping_identities_present_active': sum(key in active for key in uploaded),
              'all_uploaded_mapping_pdf_digests_match': sum(
                  any(file['id'] == key + '.pdf' and file['hash'] == row['baseline']
                      for file in active[key].files) for key, row in uploaded.items() if key in active),
              'limits': ['Metadata checks cover the 43 uploaded identities, blob byte checks are sampled.',
                         'This does not establish a physical tablet download or fresh pen-stroke round trip.']}
    output = Path(__file__).with_name('post-086-cloud-verification.json')
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
