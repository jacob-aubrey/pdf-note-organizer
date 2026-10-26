"""Read-only cloud/native checks after sync is idle; no content is published.

Uses saved encrypted grants. Writes only aggregate counts, digests and booleans.
Reads three remote baseline blobs and up to three native managed-view PDFs.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from note_organizer.remarkable_cloud import CloudClient, TokenVault
from note_organizer.zotero_pilot import LocalZotero


def main():
    spec = importlib.util.spec_from_file_location('audit_state', ROOT / 'documentation/audits/2026-10-25/verify_sync_state.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    state = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default/notable'
    snapshot = audit.capture(state, 10)
    if snapshot['changed_during_capture']:
        raise RuntimeError('Helper state changed during capture; wait until sync is idle.')
    uploaded = {key: row for key, row in snapshot['documents'].items() if row.get('uploaded') is True}
    token = TokenVault(state / 'tablet-token.dpapi').load()
    if not token:
        raise RuntimeError('Saved reMarkable grant unavailable')
    client = CloudClient(token, cache_dir=state / 'blobs')
    catalog = client.library()
    active = {row.id: row for row in catalog if row.is_pdf and not row.deleted}
    matching = {key for key, row in uploaded.items() if key in active and any(
        file['id'] == key + '.pdf' and file['hash'] == row['baseline'] for file in active[key].files)}
    candidates = []
    for key in matching:
        original = snapshot['active'] / 'bridge/originals' / (uploaded[key]['baseline'] + '.pdf')
        if original.is_file():
            candidates.append((original.stat().st_size, key))
    samples = []
    fresh = CloudClient(token)
    for size, key in sorted(candidates)[:3]:
        if size > 32 * 1024 * 1024:
            continue
        data = fresh.blob(uploaded[key]['baseline'], key + '.pdf')
        samples.append({'bytes': len(data), 'sha256_matches': hashlib.sha256(data).hexdigest() == uploaded[key]['baseline']})
    publications = {row['source']: row for row in snapshot['db']['publisher']['tables'].get('publications', [])}
    local = LocalZotero(grant_store=TokenVault(state / 'zotero-grant.dpapi'), interactive=False)
    native = []
    try:
        # Stable order, no whole-library text export or mutation.
        for key in sorted(snapshot['documents']):
            row = snapshot['documents'][key]
            receipt = publications.get(key, {})
            if not row.get('view_key') or not receipt.get('md5'):
                continue
            data = local.file_path(row['view_key']).read_bytes()
            native.append({'managed_view_exists': True, 'bytes': len(data),
                           'md5_matches_receipt': hashlib.md5(data).hexdigest() == receipt['md5'],
                           'native_annotation_records': len(local.native_annotation_text(row['view_key']))})
            if len(native) == 3:
                break
    finally:
        local.close()
    result = {'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'read_only_cloud_and_native': True,
              'uploaded_mapping_count': len(uploaded), 'present_active_cloud_count': sum(key in active for key in uploaded),
              'cloud_pdf_digest_match_count': len(matching), 'fresh_remote_blob_samples': samples,
              'native_managed_view_samples': native,
              'limits': ['Cloud digest metadata covers all uploaded identities; remote and native PDF bytes are sampled.',
                         'Native annotation counts prove readability, not comparison of every annotation against a physical device.',
                         'No new tablet pen stroke, physical download or second-computer account round trip was tested.']}
    Path(__file__).with_name('live-preservation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
