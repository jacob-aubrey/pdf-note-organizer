"""Bounded probe driver, localhost synthetic data only; see sibling probe."""
import json
from pathlib import Path
import subprocess
import sys


directory = Path(__file__).resolve().parent
root = directory.parents[2]
results = []
for variant in ('off', 'native', 'safe'):
    output = root / '.test-tmp' / 'audit-watchdog-probe' / ('httpx-approved-' + variant + '.log')
    args = [sys.executable, str(directory / 'forensic_watchdog_probe.py'), 'httpx',
            '--seconds', '6', '--interval', '.01', '--output', str(output)]
    if variant == 'native':
        args.append('--watchdog')
    if variant == 'safe':
        args.append('--safe')
    try:
        child = subprocess.run(args, input=b'', capture_output=True, timeout=18, cwd=root)
        record = {'mode': 'httpx', 'variant': variant, 'code': child.returncode,
                  'stdout': child.stdout.decode(errors='replace'), 'stderr': child.stderr.decode(errors='replace')}
    except subprocess.TimeoutExpired as error:
        record = {'mode': 'httpx', 'variant': variant, 'timeout_seconds': 18,
                  'stdout': (error.stdout or b'').decode(errors='replace'),
                  'stderr': (error.stderr or b'').decode(errors='replace')}
    record['stack_bytes'] = output.stat().st_size if output.exists() else 0
    results.append(record)
    print(json.dumps({key: value for key, value in record.items() if key != 'stderr'}), flush=True)
(directory / 'watchdog-probe-approved-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
