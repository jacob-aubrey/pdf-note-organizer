"""Record reviewed change ranges and generated-evidence provenance for this run.

Does not read secrets, mutate Git or infer that generated evidence was manually
line reviewed. Run after completing review; it records the review, not performs it.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
AUDIT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(['git', '-c', 'core.quotepath=false', *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode('utf-8')


def metadata(path):
    data = path.read_bytes()
    return {'file': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(data).hexdigest(),
            'lines': len(data.splitlines())}


def main():
    tracked = set(git('ls-files').splitlines())
    modified = set(git('diff', '--name-only', '2f06ac2bed28a569bed56a64f8ceccb47f2e886e').splitlines())
    # Include staged paths if the ledger is refreshed immediately before commit.
    modified.update(git('diff', '--cached', '--name-only').splitlines())
    untracked = set(git('ls-files', '--others', '--exclude-standard').splitlines())
    generated, reviewed = [], []
    for name in sorted(modified | untracked):
        path = ROOT / name
        if not path.is_file() or path.name == 'change-review-ledger.json':
            continue
        entry = metadata(path)
        if path.suffix.lower() not in {'.py', '.js', '.cjs', '.md', '.spec'} and name != 'zotero-support/manifest.json':
            continue  # Generated audit evidence is classified in the separate pass.
        if name not in tracked:
            entry.update(reviewed_ranges=[[1, entry['lines']]], scope='New authored file reviewed in full')
        else:
            # Compare against the original audited revision, including staging.
            diff = git('diff', '--unified=0', '2f06ac2bed28a569bed56a64f8ceccb47f2e886e', '--', name)
            ranges, deleted = [], []
            for old_start, old_count, new_start, new_count in re.findall(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', diff, re.M):
                old_n, new_n = int(old_count or 1), int(new_count or 1)
                if new_n:
                    ranges.append([int(new_start), int(new_start) + new_n - 1])
                if old_n:
                    deleted.append([int(old_start), int(old_start) + old_n - 1])
            entry.update(reviewed_ranges=ranges, replaced_or_removed_old_ranges=deleted,
                         scope='Changed ranges reviewed; unchanged code reuses October 25 audits')
        reviewed.append(entry)
    for path in sorted(AUDIT.iterdir()):
        if path.is_file() and path.suffix.lower() in {'.json', '.log', '.txt', '.patch'} and path.name != 'change-review-ledger.json':
            generated.append({**metadata(path), 'scope': 'Generated diagnostic/test/build evidence; not claimed as manual code review'})
    result = {
        'scope': 'Diagnostics and demonstrated repairs only; not a repeated full-tree audit',
        'starting_revision': '2f06ac2bed28a569bed56a64f8ceccb47f2e886e', 'branch': git('branch', '--show-current').strip(),
        'revision_at_ledger_write': git('rev-parse', 'HEAD').strip(), 'files': reviewed,
        'generated_evidence': generated,
        'excluded_private_evidence': '.test-tmp/sync-diagnostics-20261026 and supported package/state backups remain ignored',
        'external_components': 'Versions/licenses and native import/source-package parity are recorded in AUDIT_REPORT.md and package-094-verification.json; no manual binary/vendor review claimed',
        'ledger_self_hash_excluded': True,
    }
    (AUDIT / 'change-review-ledger.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'authored_files': len(reviewed), 'generated_evidence_files': len(generated), 'branch': result['branch']}))


if __name__ == '__main__':
    main()
