"""Read-only native Zotero diagnosis of the baseline's three unlinked PDFs."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from note_organizer.zotero_pilot import LocalZotero
from note_organizer.remarkable_cloud import TokenVault
from note_organizer import zotero_connections
from verify_sync_state import BASELINE, capture, unlinked_approvals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--port', type=int, default=23119)
    args = parser.parse_args()
    state = args.state.resolve(strict=True)
    baseline = capture(BASELINE, 10)
    current = capture(state, 10)
    config = current['config']
    excluded = zotero_connections.exclusions(state, config)
    client = LocalZotero(args.port, grant_store=TokenVault(state / 'zotero-grant.dpapi'), interactive=False)
    public, private = [], []
    try:
        if config.get('server_id') and client.server_id != config['server_id']:
            raise RuntimeError('Read-only API is a different saved Zotero instance')
        collections = {row['key']: row for row in client.collections()}
        def in_scope(key):
            seen = set()
            while key and key not in seen:
                if key == config.get('zotero_root'):
                    return True
                if key in excluded['zotero'] or key not in collections or collections[key].get('deleted'):
                    return False
                seen.add(key)
                key = collections[key].get('parentCollection')
            return False
        for number, (source, review) in enumerate(sorted(unlinked_approvals(baseline).items()), 1):
            approval = review['approval']
            record = client.get('item', source)
            parent_key = (record or {}).get('parentItem')
            parent = client.get('item', parent_key) if parent_key else None
            memberships = (parent or record or {}).get('collections', [])
            scoped_homes = [key for key in memberships if in_scope(key)]
            target = approval.get('collection')
            info = {'label': 'expected_pdf_' + str(number), 'native_source_exists': bool(record),
                    'source_trashed': bool((record or {}).get('deleted')),
                    'native_parent_exists': bool(parent), 'parent_trashed': bool((parent or {}).get('deleted')),
                    'content_type_pdf': (record or {}).get('contentType') == 'application/pdf',
                    'saved_home_is_live_in_scope': target in collections and in_scope(target),
                    'parent_in_saved_home': target in memberships, 'parent_in_any_current_scope': bool(scoped_homes),
                    'scoped_home_count': len(scoped_homes), 'source_excluded_by_prior_connection': source in excluded['sources'],
                    'source_excluded_by_document_key': source in excluded['documents'],
                    'already_current_managed_view': any(r.get('view_key') == source for r in current['documents'].values()),
                    'source_has_notable_pilot_marker': 'Notable pilot:' in (record or {}).get('note', ''),
                    'available_same_pdf_baseline_mappings': sum(r.get('baseline') == review['digest'] and not r.get('unavailable') for r in current['documents'].values()),
                    'saved_home_is_currently_mapped': target in current['folders'],
                    'native_parent_matches_approval': parent_key == approval.get('parent'),
                    'current_review_status': next((r['status'] for r in current['review'] if r['id'] == review['id']), None)}
            path = None
            try:
                path = client.file_path(source)
                info['local_file_present'] = path.is_file()
                info['local_extension_pdf'] = path.suffix.lower() == '.pdf'
                if path.is_file():
                    digest = hashlib.sha256()
                    deadline = time.monotonic() + 30
                    with path.open('rb') as stream:
                        while chunk := stream.read(1024 * 1024):
                            if time.monotonic() > deadline:
                                raise TimeoutError('Read-only digest deadline')
                            digest.update(chunk)
                    info['file_digest_matches_approval'] = digest.hexdigest() == review['digest']
            except Exception as error:
                info['file_check_error_type'] = type(error).__name__
            causes = []
            for condition, text in [
                (not record or (record or {}).get('deleted'), 'Source is unavailable or in Zotero Trash.'),
                (not parent or (parent or {}).get('deleted'), 'Source has no live parent reference.'),
                (not info['content_type_pdf'], 'Native attachment is not declared as a PDF.'),
                (not info.get('local_file_present'), 'Source file could not be read locally.'),
                (info.get('file_digest_matches_approval') is False, 'Native PDF bytes changed since approval.'),
                (not info['parent_in_any_current_scope'], 'Parent reference is outside the connected Zotero scope.'),
                (not info['parent_in_saved_home'], 'Parent reference is no longer a member of its approved tablet-home collection.'),
                (not info['saved_home_is_live_in_scope'], 'Approved collection is no longer in the current selected scope.'),
                (info['source_excluded_by_prior_connection'], 'Source belongs to a retained previous connection and is explicitly excluded.'),
                (not info['saved_home_is_currently_mapped'], 'Approved home has no current tablet folder mapping.')]:
                if condition:
                    causes.append(text)
            if info['already_current_managed_view']:
                causes.append('This attachment is already a managed tablet view; it must not be uploaded as a separate source.')
            if info['source_has_notable_pilot_marker']:
                causes.append('Native attachment carries the managed-view marker that the upload loop explicitly excludes.')
            if info['available_same_pdf_baseline_mappings']:
                causes.append('An existing available tablet connection has the exact same original PDF; the upload loop deliberately requires reference reconciliation instead of uploading another copy.')
            info['observed_blockers'] = causes
            public.append(info)
            private.append({**info, 'source': source, 'review_id': review['id'], 'title': review['payload'].get('title'),
                            'filename': approval.get('filename'), 'local_path': str(path) if path else None,
                            'native_parent': parent_key, 'approved_parent': approval.get('parent'),
                            'approved_collection': target, 'native_memberships': memberships,
                            'current_scoped_homes': scoped_homes, 'item_type': (record or {}).get('itemType'),
                            'link_mode': (record or {}).get('linkMode'),
                            'same_baseline_mapping_ids': [key for key, value in current['documents'].items() if value.get('baseline') == review['digest']]})
    finally:
        client.close()
    summary = {'read_only': True, 'authorization_dialogs': False, 'sources_examined': len(public), 'results': public,
               'limits': 'Native API/file checks only; no cloud writes, no reapproval, no source movement.'}
    out = Path(__file__).resolve().parent / 'unlinked-pdf-diagnosis.json'
    private_out = ROOT / '.test-tmp/full-audit-20261025/unlinked-pdf-diagnosis-private.json'
    out.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    private_out.write_text(json.dumps(private, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
