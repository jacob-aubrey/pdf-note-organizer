"""Read-only, finite local audit capture; no API calls or document reads.

Copies structural records from rotating production diagnostics into a bounded
private timeline. Exact duplicate records are coalesced. Stop with stop-capture.
"""
from collections import deque
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default/notable'
DEST = ROOT / '.test-tmp/sync-diagnostics-20261026'
DEST.mkdir(parents=True, exist_ok=True)
TARGET = DEST / 'live-timeline.jsonl'
LIMIT = 16 * 1024 * 1024
parser = argparse.ArgumentParser()
parser.add_argument('--since', default='2026-10-26T05:06:30')
args = parser.parse_args()
seen, order = set(), deque()
deadline = time.monotonic() + 3600
while time.monotonic() < deadline and not (DEST / 'stop-capture').exists():
    for prefix in ('sync-trace.jsonl', 'sync-transport.jsonl'):
        for suffix in ('.2', '.1', ''):
            path = SOURCE / (prefix + suffix)
            try:
                lines = path.read_text(encoding='utf-8').splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('time', '') < args.since:
                    continue
                if row.get('event') in {'database_started', 'database_finished'}:
                    continue  # Complete current/rotated DB records stay in profile.
                identity = hashlib.sha256(line.encode()).digest()
                if identity in seen:
                    continue
                seen.add(identity)
                order.append(identity)
                if len(order) > 100000:
                    seen.discard(order.popleft())
                data = (json.dumps({'log': prefix, **row}, ensure_ascii=True) + '\n').encode()
                if TARGET.exists() and TARGET.stat().st_size + len(data) > LIMIT:
                    previous = TARGET.with_suffix('.jsonl.1')
                    if previous.exists():
                        previous.replace(TARGET.with_suffix('.jsonl.2'))
                    TARGET.replace(previous)
                with TARGET.open('ab') as stream:
                    stream.write(data)
                    stream.flush()
    time.sleep(3)
