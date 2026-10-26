# Evening frontend command inventory

Commands ran from `C:\Users\jdaub\OneDrive\Desktop\Documents\PhD\Bonitatibus Research\Python Code\PDF Note Organizer` in PowerShell. Native localhost operations used approved escalation and explicit synthetic profiles. No production profile or cloud account was used by these commands.

The initial source/package inspection used `git status --short`, `git rev-parse HEAD`, the existing frontend ledger, prior package comparisons, installation records, build log, and existing status-smoke result. Installation JSON in the earlier directory still described 0.8.5, so it was not accepted as final 0.8.7 installation proof. The parent independently supplied the active installed 0.8.7 identity. The 0.8.7 mismatch comparison used `git show 7bdb3a63bf198692883286749693fca9cabcb78d:<path>` for an immutable source target while the parent changed metadata to 0.8.8; CRLF-only differences were recorded separately.

## Final package comparison

The following Python stdin script was executed for the final 0.8.8 artifact; it asserts every comparison instead of merely printing booleans. The final two statements preserve the existing status-smoke script verbatim under the evening directory before its new execution.

```powershell
@'
from pathlib import Path
import hashlib,json,marshal,types,zipfile
from PyInstaller.archive.readers import CArchiveReader
out=Path('documentation/audits/2026-10-25-evening');prior=json.loads(Path('documentation/audits/2026-10-25/frontend-package087-initial-comparison.json').read_text(encoding='utf-8'))
xpi=Path('dist/reMarkable-Sync-for-Zotero-0.8.8.xpi');helper=Path('.test-tmp/zotero-plugin-088-dist/notable-worker.exe')
def sha(b):return hashlib.sha256(b).hexdigest()
def norm(c):return c.replace(co_filename='<source>',co_consts=tuple(norm(v) if isinstance(v,types.CodeType) else v for v in c.co_consts))
assert sha(xpi.read_bytes())=='44354eb0bc530e47e5b1b52021b0e0e711c2c238ea80959f93c657f69520e19c'
a=CArchiveReader(str(helper));pyz=a.open_embedded_archive('PYZ.pyz');assert {n for n in pyz.toc if n=='note_organizer' or n.startswith('note_organizer.')}=={r['module'] for r in prior['python_modules']}
r={'package':str(xpi),'package_sha256':sha(xpi.read_bytes()),'runtime':str(helper),'runtime_sha256':sha(helper.read_bytes()),'runtime_md5':hashlib.md5(helper.read_bytes()).hexdigest(),'comparison':'Recursive Python code equality after normalizing only co_filename; optimize=0','python_modules':[],'frontend_files':[]}
for item in prior['python_modules']:
 p=Path(item['file']);b=p.read_bytes();equal=norm(pyz.extract(item['module']))==norm(compile(b,str(p),'exec',optimize=0));assert equal,item['file']
 r['python_modules'].append({'file':item['file'],'module':item['module'],'code_object_equal':equal,'sha256':sha(b)})
with zipfile.ZipFile(xpi) as z:
 r['runtime_manifest']=json.loads(z.read('runtime-manifest.json'));assert z.read('runtime/notable-worker.exe')==helper.read_bytes()
 for item in prior['frontend_files']:
  p=Path(item['file']);b=p.read_bytes();equal=z.read(p.relative_to('zotero-support').as_posix())==b;assert equal,item['file']
  r['frontend_files'].append({'file':item['file'],'packaged_bytes_equal':equal,'sha256':sha(b)})
 for item in r['runtime_manifest']['files']:assert hashlib.md5(z.read('runtime/'+item['path'])).hexdigest()==item['md5']
p=Path('tools/notable_worker.py');b=p.read_bytes();equal=norm(marshal.loads(a.extract('notable_worker')))==norm(compile(b,str(p),'exec',optimize=0));assert equal;r['entrypoint']={'file':str(p),'sha256':sha(b),'code_object_equal':equal}
p=Path('documentation/ZOTERO_PLUGIN_NOTICES.md');b=p.read_bytes();equal=a.extract('licenses\\ZOTERO_PLUGIN_NOTICES.md')==b;assert equal;r['component_notice']={'entry':'licenses\\ZOTERO_PLUGIN_NOTICES.md','packaged_bytes_equal':equal,'sha256':sha(b)}
(out/'frontend-package088-comparison.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
source=Path('documentation/audits/2026-10-25/packaged_status_smoke.py');target=out/source.name;target.write_bytes(source.read_bytes());(out/'status-smoke-command-provenance.json').write_text(json.dumps({'source':str(source),'script_sha256':sha(source.read_bytes()),'copied_verbatim_for_distinct_evening_output':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'package_sha256':r['package_sha256'],'runtime_sha256':r['runtime_sha256'],'runtime_md5':r['runtime_md5'],'modules':len(r['python_modules']),'frontend':len(r['frontend_files']),'all_equal':True}))
'@ | .\.venv\Scripts\python.exe -
```

Result: 36 modules, 31 frontend/assets, entrypoint, notice, and runtime manifest pass; worker SHA-256 `01f687ed553f1a4999e159705fb4abb435bd16921e4485714cfa55e4df4ab22a`. Evidence: `frontend-package088-comparison.json`.

## Exact-helper status smoke

```powershell
$statusTemp = Join-Path (Get-Location).Path '.test-tmp/full-audit-20261025-evening/status-temp'
New-Item -ItemType Directory -Path $statusTemp -Force | Out-Null
$env:TEMP = $statusTemp
$env:TMP = $statusTemp
& '.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe' 'documentation/audits/2026-10-25-evening/packaged_status_smoke.py' --helper '.test-tmp/zotero-plugin-088-dist/notable-worker.exe'
```

Result: waiting 2 / linked 4 / received 1, exit 0, empty stderr; evidence `packaged-status-smoke-results.json`. The copied script starts the helper with `--debug-stacks`.

## Native fixture and targeted malformed-PDF check

```powershell
$env:PYTHONPATH = (Resolve-Path 'documentation/audits/2026-10-25/runtime-bootstrap').Path
.\.venv\Scripts\python.exe tools/test_zotero_plugin_live.py --work-dir .test-tmp/full-audit-20261025-evening/packaged088-managed-diagnostic --zotero-exe 'C:\Program Files\Zotero\zotero.exe' --port 23168 --xpi dist/reMarkable-Sync-for-Zotero-0.8.8.xpi --skip-ocr --keep-open
```

After the harness reported `ready_for_visual_inspection` with 14 baseline passes:

```powershell
$env:PYTHONPATH = (Resolve-Path 'documentation/audits/2026-10-25/runtime-bootstrap').Path
.\.venv\Scripts\python.exe documentation/audits/2026-10-25-evening/verify_packaged_pdf_diagnostics.py --fixture .test-tmp/full-audit-20261025-evening/packaged088-managed-diagnostic --helper .test-tmp/zotero-plugin-088-dist/notable-worker.exe --helper-sha256 01f687ed553f1a4999e159705fb4abb435bd16921e4485714cfa55e4df4ab22a --port 23168
```

The runner uses the existing managed publication adapter and its returned key, verifies the annotation read, launches the exact helper without `PYMUPDF_MESSAGE` and with `--debug-stacks`, then sends reindex, status, and shutdown packets. Native MuPDF diagnostics go to stderr; reindex and subsequent status succeed; source/stored bytes remain unchanged; exit 0. It touches only the scoped fixture's `close-test` marker in `finally`; the original harness then writes `done` and exits 0. Evidence: `packaged-pdf-diagnostics-results.json` and the fixture's `results.json`.

Two earlier executions used the same native/runner commands with fixture suffixes `packaged088-malformed` and `packaged088-malformed-text` respectively. Both native baselines passed 14 checks and closed normally, but the initial versions of the runner raw-created an unmanaged attachment, causing the annotation-read guard to reject it. Those failed targeted attempts are retained in `packaged-pdf-diagnostics-initial-empty-results.json` and `packaged-pdf-diagnostics-unmanaged-results.json`. They are not counted as successful indexing evidence. The valid-text change alone did not fix the guard; the final managed-publication correction did. No product code changed for these fixture corrections.
