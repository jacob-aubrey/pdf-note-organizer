"""Audit-only source snapshots; run only after Zotero and its helper close."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import sys

root = Path(__file__).resolve().parents[3]
profile = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default'
state = profile / 'notable'
output = root / '.test-tmp/full-audit-20261025' / (sys.argv[1] if len(sys.argv) > 1 else 'pre-085-backup')
output.mkdir(parents=True, exist_ok=False)
records = []


def snapshot_database(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    # A stopped helper can leave a hot rollback journal. Preserve DB and its
    # sidecars together, then let SQLite recover only this disposable copy.
    copied = output / 'database-copies' / target.relative_to(output)
    copied.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, copied)
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = Path(str(source) + suffix)
        if sidecar.exists():
            shutil.copyfile(sidecar, Path(str(copied) + suffix))
    deadline = time.monotonic() + 30
    def progress(*_):
        if time.monotonic() > deadline:
            raise TimeoutError('The source database stayed busy; close Zotero before retrying the snapshot')
    with sqlite3.connect(copied, timeout=15) as original:
        with sqlite3.connect(target) as destination:
            original.backup(destination, pages=256, progress=progress, sleep=.1)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup database verification failed')
    records.append({'path': str(target.relative_to(output)), 'sqlite_integrity': 'ok'})


snapshot_database(Path('C:/Users/jdaub/Zotero/zotero.sqlite'), output / 'zotero.sqlite')
excluded = {'blobs', 'printed-cache', 'handwriting-cache', 'sources', 'baselines', 'layers', 'versions', 'runtime'}
for source in state.rglob('*'):
    relative = source.relative_to(state)
    if not source.is_file() or set(relative.parts) & excluded:
        continue
    target = output / 'notable' / relative
    if source.suffix == '.sqlite3' and source.stat().st_size:
        snapshot_database(source, target)
    elif source.suffix in {'.json', '.dpapi'}:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append({'path': str(target.relative_to(output)), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
source = profile / 'extensions/notable-companion@local.invalid.xpi'
target = output / 'previous-plugin.xpi'
shutil.copy2(source, target)
records.append({'path': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
(output / 'backup-manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps({'status': 'PASS', 'backed_up_files': len(records), 'databases': sum('sqlite_integrity' in row for row in records), 'directory': str(output)}))
