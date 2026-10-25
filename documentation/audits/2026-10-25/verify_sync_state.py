"""Read-only post-sync journal comparison. Run only after the helper is idle.

No product imports, API calls, credentials, repairs, or production writes.
SQLite databases are opened mode=ro and backed up into memory with a deadline.
Public output contains counts/booleans; titles and identifiers stay in .test-tmp.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

REPO = Path(__file__).resolve().parents[3]
AUDIT = Path(__file__).resolve().parent
BASELINE = REPO / '.test-tmp/full-audit-20261025/pre-085-backup-complete/notable'
HASH = re.compile(r'[a-f0-9]{64}')


def signature(path):
    if not path.exists():
        return None
    info = path.stat()
    return [info.st_size, info.st_mtime_ns]


def read_db(path, timeout):
    if not path.is_file():
        return {'present': False, 'tables': {}, 'integrity_ok': None}
    deadline = time.monotonic() + timeout
    source = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=min(timeout, 2))
    memory = sqlite3.connect(':memory:')
    try:
        source.execute('PRAGMA query_only=ON')
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError('Read-only snapshot deadline')
        source.backup(memory, pages=128, progress=progress, sleep=.05)
        memory.row_factory = sqlite3.Row
        memory.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        integrity = memory.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        tables = {}
        for row in memory.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            name = row[0]
            quoted = '"' + name.replace('"', '""') + '"'
            # Upload receipts may contain temporary account-upload details.
            # Only their existence/source identity is needed; never read them.
            query = 'SELECT source FROM ' + quoted if name == 'upload_intents' else 'SELECT * FROM ' + quoted
            tables[name] = [dict(item) for item in memory.execute(query)]
        return {'present': True, 'tables': tables, 'integrity_ok': integrity}
    finally:
        memory.close()
        source.close()


def capture(root, timeout):
    root = root.resolve(strict=True)
    config_path = root / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
    identity = config.get('connection_id', 'legacy')
    if identity != 'legacy' and not re.fullmatch(r'[a-f0-9]{32}', identity):
        raise ValueError('Invalid saved connection namespace')
    active = root if identity == 'legacy' else root / 'connections' / identity
    paths = {'review': active / 'review/pilot.sqlite3', 'bridge': active / 'bridge/pilot.sqlite3',
             'publisher': active / 'bridge/publisher/pilot.sqlite3',
             'source_imports': active / 'source-imports/pilot.sqlite3',
             'edition_recovery': root / 'edition-recovery/pilot.sqlite3'}
    watched = [config_path, *paths.values(), *(p.with_name(p.name + '-wal') for p in paths.values())]
    before = {str(p): signature(p) for p in watched}
    databases = {key: read_db(path, timeout) for key, path in paths.items()}
    changed = [str(p.relative_to(root)) for p in watched if before[str(p)] != signature(p)]
    review = []
    for row in databases['review']['tables'].get('review_queue', []):
        review.append({**row, 'payload': json.loads(row['payload']), 'approval': json.loads(row['approval'])})
    values = {row['key']: json.loads(row['value']) for row in databases['bridge']['tables'].get('bridge_values', [])}
    bulk_path = root / 'bulk-library.json'
    bulk = json.loads(bulk_path.read_text(encoding='utf-8')) if bulk_path.is_file() else {}
    return {'root': root, 'active': active, 'config': config, 'db': databases, 'review': review,
            'documents': values.get('documents', {}), 'folders': values.get('folders', {}),
            'changed_during_capture': changed, 'bulk': bulk}


def eligible(row):
    return (row['status'] == 'approved' and row['kind'] in {'cloud', 'zotero', 'inbox'}
            and (row['kind'] == 'cloud' or Path(row['payload'].get('path') or row['approval'].get('filename')
                                              or row['payload'].get('filename', '')).suffix.lower() == '.pdf'))


def unlinked_approvals(state):
    documents = state['documents']
    sources = {row.get('source_key') for row in documents.values()}
    result = {}
    for row in state['review']:
        if eligible(row) and row['identity'] not in documents and row['approval'].get('source') not in sources:
            result.setdefault(row['approval'].get('source') or row['kind'] + ':' + row['identity'], row)
    return result


def duplicate_groups(documents, field):
    groups = defaultdict(list)
    for identity, row in documents.items():
        if row.get(field):
            groups[row[field]].append(identity)
    return {value: ids for value, ids in groups.items() if len(ids) > 1}


def staged_pending(state):
    tables = state['db']['review']['tables']
    suspended = set()
    for row in tables.get('deletion_decisions', []):
        identity = json.loads(row['payload'])['cloud']
        if row['status'] != 'resolved' or row['action'] != 'restore':
            suspended.add(identity)
        else:
            suspended.discard(identity)
    suspended.update(json.loads(row['payload'])['cloud'] for row in tables.get('local_deletions', []) if row['status'] != 'resolved')
    suspended.update(row['identity'] for row in tables.get('link_controls', []) if row['paused'])
    return {identity: row['source_key'] for identity, row in state['documents'].items()
            if row.get('origin') == 'zotero' and row.get('uploaded') is False and row.get('source_key')
            and not row.get('unavailable') and identity not in suspended}


def table_summary(database):
    result = {'present': database['present'], 'integrity_ok': database['integrity_ok'], 'tables': {}}
    for name, rows in database['tables'].items():
        entry = {'rows': len(rows)}
        if rows and 'status' in rows[0]:
            entry['by_status'] = dict(Counter(row['status'] for row in rows))
        if name == 'publications':
            entry.update(published=sum(bool(r.get('published')) for r in rows),
                         pending_md5=sum(bool(r.get('pending_md5')) for r in rows),
                         indexed_sha=sum(bool(r.get('indexed_sha')) for r in rows))
        result['tables'][name] = entry
    return result


def retained_manifest_summary(state, *, source_files_expected=True):
    """Separate retained source revisions from later remote metadata receipts.

    Tag reconciliation can advance a mapping's revision after its observed
    source bundle was saved. A different latest-source revision is therefore
    not, by itself, a missing annotation/archive finding.
    """
    if not source_files_expected:
        return {'checked': False, 'reason': 'Source files were excluded from this baseline backup.'}
    manifest_root = state['active'] / 'bridge/sources/remarkable/sources'
    manifest = Counter()
    for identity, row in state['documents'].items():
        if not row.get('revision') or not re.fullmatch(r'[A-Za-z0-9_-]+', identity) or not HASH.fullmatch(row['revision']):
            continue
        path = manifest_root / 'history' / identity / (row['revision'] + '.json')
        exact_history = path.is_file()
        manifest['mapping_revision_history_present'] += exact_history
        if not exact_history:
            path = manifest_root / (identity + '.json')
        if not path.is_file():
            manifest['missing'] += 1
            continue
        info = json.loads(path.read_text(encoding='utf-8'))
        manifest['present'] += 1
        manifest['selected_latest_manifest_fallback'] += not exact_history
        same_revision = info.get('cloud_hash') == row['revision']
        manifest['mapping_revision_matches_selected_source'] += same_revision
        manifest['mapping_revision_differs_from_selected_source'] += not same_revision
        manifest['different_revision_with_completed_tag_state'] += (
            not same_revision and bool(row.get('tag_state')) and not row.get('tag_pending'))
        manifest['manifest_identity_matches'] += info.get('id') == identity
        source_revision = info.get('cloud_hash', '')
        if isinstance(source_revision, str) and HASH.fullmatch(source_revision):
            manifest['selected_source_revision_history_present'] += (
                manifest_root / 'history' / identity / (source_revision + '.json')).is_file()
        manifest['baseline_matches'] += info.get('pdf_hash') == row.get('baseline')
        for field in ('baseline', 'layers'):
            relative = info.get(field)
            if isinstance(relative, str):
                candidate = (manifest_root.parent / relative).resolve()
                manifest[field + '_file_present'] += candidate.is_relative_to(manifest_root.parent.resolve()) and candidate.is_file()
        if info.get('manifest_hash'):
            payload = {key: value for key, value in info.items() if key != 'manifest_hash'}
            computed = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            manifest['self_hash_valid'] += computed == info['manifest_hash']
    return {'checked': True, **dict(manifest)}


def state_summary(state, *, source_files_expected=True):
    docs = state['documents']
    active_reviews = [r for r in state['review'] if r['status'] in {'pending', 'applying'}]
    controls = state['db']['review']['tables'].get('link_controls', [])
    original_root = state['active'] / 'bridge/originals'
    bulk_rows = state['bulk'].get('rows', [])
    return {
        'mapping_identities': len(docs), 'available_identities': sum(not r.get('unavailable') for r in docs.values()),
        'uploaded_true': sum(r.get('uploaded') is True for r in docs.values()),
        'uploaded_false': sum(r.get('uploaded') is False for r in docs.values()),
        'staged_not_uploaded_by_origin': dict(Counter(r.get('origin', 'unknown') for r in docs.values() if r.get('uploaded') is False)),
        'received_revision': sum(bool(r.get('revision')) for r in docs.values()),
        'managed_view': sum(bool(r.get('view_key')) for r in docs.values()),
        'rendered_receipt': sum(bool(r.get('rendered')) for r in docs.values()),
        'page_map_receipt': sum(bool(r.get('page_map_digest')) for r in docs.values()),
        'desktop_annotations_preserved_documents': sum(bool(r.get('desktop_annotations_preserved')) for r in docs.values()),
        'tag_recovery_pending': sum(bool(r.get('tag_pending')) for r in docs.values()),
        'original_baseline_present': (sum(bool(HASH.fullmatch(str(r.get('baseline', '')))) and (original_root / (r['baseline'] + '.pdf')).is_file() for r in docs.values())
                                      if source_files_expected else None),
        'retained_source_manifest_receipts': retained_manifest_summary(state, source_files_expected=source_files_expected),
        'duplicate_source_groups': len(duplicate_groups(docs, 'source_key')),
        'duplicate_view_groups': len(duplicate_groups(docs, 'view_key')),
        'repeated_baseline_groups_observational': len(duplicate_groups(docs, 'baseline')),
        'review_by_kind_and_status': dict(Counter(r['kind'] + ':' + r['status'] for r in state['review'])),
        'active_reviews_with_issues': sum(bool(r['payload'].get('issues')) for r in active_reviews),
        'active_reviews_repair_required': sum(bool(r['payload'].get('repair_required')) for r in active_reviews),
        'paused_links': sum(bool(r['paused']) for r in controls),
        'approved_unlinked_pdf_sources': len(unlinked_approvals(state)),
        'staged_eligible_upload_identities': len(staged_pending(state)),
        'approved_waiting_sync_pdf_sources_including_staged': len(set(unlinked_approvals(state)) | set(staged_pending(state).values())),
        'bulk_by_status': dict(Counter(r.get('status', 'unknown') for r in bulk_rows)),
        'bulk_rows_with_issues': sum(bool(r.get('issues')) for r in bulk_rows),
        'database_queues_and_receipts': {key: table_summary(value) for key, value in state['db'].items()},
        'changed_during_capture': state['changed_during_capture']}


def compare(baseline, current):
    expected = unlinked_approvals(baseline)
    details, public = [], []
    publications = {r['source']: r for r in current['db']['publisher']['tables'].get('publications', [])}
    for number, (source, row) in enumerate(sorted(expected.items()), 1):
        matches = {key: value for key, value in current['documents'].items()
                   if value.get('source_key') == source or row['kind'] == 'cloud' and key == row['identity']}
        proofs = []
        for identity, link in matches.items():
            path = current['active'] / 'bridge/originals' / (row['digest'] + '.pdf')
            retained = None
            if HASH.fullmatch(row['digest']) and path.is_file() and not path.is_symlink():
                with path.open('rb') as stream:
                    retained = hashlib.file_digest(stream, 'sha256').hexdigest() == row['digest']
            proofs.append({'baseline_matches': link.get('baseline') == row['digest'],
                           'uploaded': link.get('uploaded') is True, 'received_revision': bool(link.get('revision')),
                           'publication_complete': bool(publications.get(identity, {}).get('published')),
                           'available': not link.get('unavailable'), 'original_bytes_verified': retained})
        item = {'label': 'expected_pdf_' + str(number), 'matching_links': len(matches), 'proofs': proofs}
        public.append(item)
        details.append({**item, 'review_id': row['id'], 'kind': row['kind'], 'identity': row['identity'],
                        'source': source, 'title': row['payload'].get('title', ''),
                        'filename': row['approval'].get('filename', ''), 'links': list(matches)})
    old, new = baseline['documents'], current['documents']
    missing = sorted(set(old) - set(new))
    changed = sorted(key for key in set(old) & set(new) if old[key].get('baseline') != new[key].get('baseline'))
    comparison = {'expected_unlinked_approved_pdfs': len(expected), 'expected_pdf_results': public,
                  'new_mapping_identities': len(set(new) - set(old)), 'missing_prior_mapping_identities': len(missing),
                  'prior_mapping_baselines_changed': len(changed),
                  'previously_staged_now_uploaded': sum(r.get('uploaded') is False and new.get(key, {}).get('uploaded') is True for key, r in old.items()),
                  'previously_staged_still_not_uploaded': sum(r.get('uploaded') is False and new.get(key, {}).get('uploaded') is not True for key, r in old.items()),
                  'same_connection_roots': all(baseline['config'].get(k) == current['config'].get(k) for k in ('server_id', 'zotero_root', 'tablet_root'))}
    private = {'expected_pdfs': details, 'missing_prior_mapping_ids': missing, 'changed_baseline_mapping_ids': changed,
               'duplicate_source_groups': duplicate_groups(new, 'source_key'), 'duplicate_view_groups': duplicate_groups(new, 'view_key')}
    return comparison, private


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--baseline-sources-excluded', action='store_true',
                        help='Do not treat intentionally excluded source files in a custom baseline backup as missing.')
    parser.add_argument('--current-state', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--summary', type=Path, default=AUDIT / 'post-sync-verification.json')
    parser.add_argument('--details', type=Path, default=REPO / '.test-tmp/full-audit-20261025/post-sync-private-details.json')
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error('timeout must be between zero and 60 seconds')
    for output in (args.summary, args.details):
        if not any(output.resolve().is_relative_to(root.resolve()) for root in (AUDIT, REPO / '.test-tmp')):
            parser.error('outputs must stay in the audit or .test-tmp directories')
    baseline, current = capture(args.baseline, args.timeout), capture(args.current_state, args.timeout)
    comparison, details = compare(baseline, current)
    baseline_sources_expected = not (args.baseline_sources_excluded or args.baseline.resolve() == BASELINE.resolve())
    result = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'capture_method': 'mode=ro SQLite online backups into memory, finite per-database deadlines',
              'baseline': state_summary(baseline, source_files_expected=baseline_sources_expected),
              'current': state_summary(current), 'comparison': comparison,
              'limits': ['Run after sync is idle; separate databases are not one cross-database transaction.',
                         'Journal receipts do not independently prove current cloud/device or native Zotero state.',
                         'Only expected newly linked PDF originals are byte-hashed; other baseline/manifests use existence and metadata checks.',
                         'Repeated baseline digests may be intentional; duplicate source/view identity groups need review.',
                         'Unlinked approved PDFs and existing uploaded=False staged mappings are separate populations.',
                         'A mapping revision may advance after a tag write; a retained source revision mismatch alone does not prove source loss.',
                         'The default pre-update baseline backup intentionally excludes source files; those source checks are not evaluated.']}
    for path, value in ((args.summary, result), (args.details, details)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
