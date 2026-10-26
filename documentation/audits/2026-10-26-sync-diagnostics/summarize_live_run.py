"""Produce a structural, content-free summary from this audit's private capture."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / '.test-tmp/sync-diagnostics-20261026'


def timestamp(row):
    return datetime.fromisoformat(row['time'].replace('Z', '+00:00')).timestamp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('operation')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]{1,48}', args.label) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.operation):
        parser.error('Use audit identifiers')
    rows = {}
    for path in PRIVATE.glob('*live-timeline.jsonl*'):
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rows[json.dumps(row, sort_keys=True)] = row
    worker = sorted((row for row in rows.values() if row.get('operation') == args.operation),
                    key=lambda row: row.get('elapsed_ms', 0))
    start = next(row for row in worker if row['event'] == 'operation_started')
    end = next(row for row in reversed(worker) if row['event'] == 'operation_finished')
    helper = args.operation.rsplit('-', 1)[0]
    transport = sorted((row for row in rows.values() if row.get('helper_id') == helper
                        and timestamp(start) <= timestamp(row) <= timestamp(end) + 2), key=timestamp)
    own_transport = [row for row in transport if row.get('trace_id') == args.operation]
    counts = Counter(row['event'] for row in worker)
    paper_numbers = [int(match.group(1)) for row in worker if row['event'] == 'progress'
                     and (match := re.fullmatch(r'Syncing linked paper (\d+) of \d+', row.get('message', '')))]
    stages = [{key: row[key] for key in ('time', 'elapsed_ms', 'name')} for row in worker if row['event'] == 'stage']
    writes = Counter()
    for row in worker:
        if row['event'] == 'zotero_request_started' and row.get('verb') not in {'GET', 'HEAD', 'OPTIONS'}:
            route = re.sub(r'/[A-Z0-9]{8}(?=/|$)', '/<key>', row.get('route', ''))
            writes[(row.get('verb'), route)] += 1
    excluded = {'progress', 'heartbeat_sent', 'request_received'}
    exceptional = [{key: row[key] for key in ('time', 'elapsed_ms', 'event', 'type', 'attempt', 'duration_ms', 'delay_s') if key in row}
                   for row in worker if row['event'] not in excluded
                   and any(word in row['event'] for word in ('failed', 'timeout', 'error', 'retry'))]
    result = {
        'scope': 'Captured live configured Sync; structural fields only, no document text or request payloads',
        'operation': args.operation, 'start_utc': start['time'], 'finish_utc': end['time'],
        'duration_ms': end['elapsed_ms'], 'completion_state': end.get('state'),
        'sync_result': next(({key: row[key] for key in ('actions', 'reviews', 'partial_indexes')}
                             for row in worker if row['event'] == 'sync_result'), None),
        'stages': stages, 'linked_paper_progress_maximum': max(paper_numbers, default=0),
        'worker_event_counts': dict(counts),
        'zotero_http_methods': dict(Counter(row['verb'] for row in worker if row['event'] == 'zotero_request_started')),
        'zotero_http_writes': [{'verb': verb, 'route': route, 'count': count} for (verb, route), count in sorted(writes.items())],
        'cloud_http_methods': dict(Counter(row['verb'] for row in worker if row['event'] == 'cloud_request_started')),
        'transport_heartbeat_receipts': sum(row['event'] == 'heartbeat_received' for row in transport),
        'rpc_boundaries': own_transport, 'exceptional_events': exceptional,
        'helper_failure_events': [row for row in transport if row['event'] in
                                  {'rpc_timeout', 'parent_termination_requested', 'parent_kill', 'helper_exit', 'stdout_eof', 'invalid_response'}],
        'limits': ['Successful database spans were excluded from this supplemental capture; bounded profile logs contain them.',
                   'Action counts include unchanged publications and are not counts of new files.'],
    }
    target = Path(__file__).with_name('live-run-' + args.label + '.json')
    if target.exists():
        raise RuntimeError('Evidence label already exists')
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
