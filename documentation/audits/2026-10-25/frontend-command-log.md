# Frontend native, UI, and package command inventory

These commands were run from `C:\Users\jdaub\OneDrive\Desktop\Documents\PhD\Bonitatibus Research\Python Code\PDF Note Organizer` in PowerShell. This inventory was written from the completed run records; no test was repeated to create it. Native fixture commands that needed localhost sockets ran with approved sandbox escalation. Each fixture uses synthetic data, a new explicit profile/data directory, and a separate port. No production profile, tablet account, or cloud credentials were used by this reviewer.

## Snapshot and evidence inventory

| Target | Fixture / port | Observed result | Durable evidence |
|---|---|---|---|
| Initial pre-repair source snapshot, nominal 0.8.4 | `frontend-source-elevated` / 23161 | 51 native checks; 30 UI checks | Fixture `results.json`, `ui-results.json`, PNGs |
| Initial exact 0.8.4 package | `frontend-packaged084` / 23162 | 27 native/package checks in final artifact; no separate 30-check UI run | Fixture `results.json`; `frontend-package-comparison.json` |
| Repaired exact 0.8.5 package | `packaged085` / 23165 | 53 native/package checks; 30 UI checks | Fixture `results.json`, `ui-results.json`, PNGs; `frontend-package085-comparison.json` |
| Exact 0.8.5 after harness F3 repair | `packaged085-ui-f3` / 23166 | 14 baseline native checks; 30 UI checks | Fixture `results.json`, `ui-results.json`, PNGs |
| First 0.8.6 build, safe sampler repair | `packaged086` / 23167 | 53 native/package checks with bundled OCR and diagnostics enabled; four safe stack snapshots; exit 0 | Fixture `results.json`; `frontend-package086-results.json`; `frontend-package086-comparison.json` |
| Final 0.8.6 rebuild, PDF-only status counter repair | Disposable `audit-status-package-smoke` state | Waiting 1 / linked 2 / received 1; exit 0; empty stderr | `packaged-status-smoke086-results.json`; `frontend-package086-final-comparison.json` |

Fixture names in the table are beneath `.test-tmp/full-audit-20261025/`. Comparison/result documents are beneath `documentation/audits/2026-10-25/`. There was **no separate post-repair source-native 0.8.5 run**: the source fixture above belongs to the initial pre-repair snapshot, and subsequent 0.8.5 tests used the exact release XPI.

Exact XPI SHA-256 values:

- 0.8.4: `3a6e7827a7d80b0cfb03bc851733a254a42da84235694bd47d63d054f6291edc`.
- 0.8.5: `7253269adeb1a6d6a3021736a59c17d3d61b6c8440e5d98cf0705e052e3a2c6d`.
- First 0.8.6: `bde735d23f0b0577aa71c2960c4da6b99c29f02d38a470165117168b5536ee77`.
- Final 0.8.6: `f7ec29a3f9c908f202436b3bc3b00dccc86b279ee58c720d22045643c3ea5e6d`.

The same `dist/reMarkable-Sync-for-Zotero-0.8.6.xpi` pathname was replaced by the final rebuild. Its first-build evidence remains separate and is identified by the first-build hash. The final build received a fresh full package/source comparison and targeted exact-helper status smoke; the 53-check OCR/native fixture was not repeated against the final status-only rebuild.

## Native fixture commands

The source/development helper and harness imports used the audit-only bootstrap below. It appends extracted runtime dependencies after normal stdlib/site-packages; the exact-package helper itself uses its bundled dependencies.

```powershell
$env:PYTHONPATH = (Resolve-Path 'documentation/audits/2026-10-25/runtime-bootstrap').Path
```

Initial source-native run:

```powershell
.\.venv\Scripts\python.exe tools/test_zotero_plugin_live.py --work-dir .test-tmp/full-audit-20261025/frontend-source-elevated --zotero-exe 'C:\Program Files\Zotero\zotero.exe' --port 23161 --bulk-count 30 --skip-ocr --connection-checks --activity-checks --tagging-checks --keep-open
```

Repaired exact 0.8.5 full native/package run:

```powershell
.\.venv\Scripts\python.exe tools/test_zotero_plugin_live.py --work-dir .test-tmp/full-audit-20261025/packaged085 --zotero-exe 'C:\Program Files\Zotero\zotero.exe' --port 23165 --xpi dist/reMarkable-Sync-for-Zotero-0.8.5.xpi --bulk-count 30 --connection-checks --activity-checks --tagging-checks --keep-open
```

Fresh exact 0.8.5 baseline/UI fixture after repairing the transient JSON-response harness race:

```powershell
.\.venv\Scripts\python.exe tools/test_zotero_plugin_live.py --work-dir .test-tmp/full-audit-20261025/packaged085-ui-f3 --zotero-exe 'C:\Program Files\Zotero\zotero.exe' --port 23166 --xpi dist/reMarkable-Sync-for-Zotero-0.8.5.xpi --skip-ocr --keep-open
```

First exact 0.8.6 full native/package run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'documentation/audits/2026-10-25/runtime-bootstrap').Path
.\.venv\Scripts\python.exe tools/test_zotero_plugin_live.py --work-dir .test-tmp/full-audit-20261025/packaged086 --zotero-exe 'C:\Program Files\Zotero\zotero.exe' --port 23167 --xpi dist/reMarkable-Sync-for-Zotero-0.8.6.xpi --bulk-count 30 --connection-checks --activity-checks --tagging-checks
```

`--skip-ocr` was deliberately absent from the full 0.8.5 and 0.8.6 commands. The 0.8.6 harness writes `user_pref("notable.testDiagnostics", true);` in its new profile; the plugin therefore starts the exact packaged worker with `--debug-stacks`. There is no separate diagnostics switch on this harness command. Its safe stack log is `packaged086/profile/notable/test-worker-stack.log`.

The older 0.8.4 fixture used the exact 0.8.4 XPI, tagging checks, bundled OCR, and port 23162, without bulk/connection/activity checks. Its original complete shell line was not retained in this reviewer’s compacted record, so this inventory does not present a guessed shell line as exact. Its final `results.json` contains **27** passes; the earlier narrative count of 26 omitted the final render check and has been corrected.

The three `--keep-open` fixtures remained available for their UI checker, then were closed by touching their own `close-test` marker. Their harness `finally` blocks wrote `done`, closed their client, and waited for the scoped Zotero process. All have `done` markers. The first 0.8.6 command omitted `--keep-open` and closed automatically after its checks, with harness exit 0. The 0.8.4 fixture also has a `done` marker.

## Rendered UI commands

```powershell
.\.venv\Scripts\python.exe tools/test_zotero_plugin_ui.py --work-dir .test-tmp/full-audit-20261025/frontend-source-elevated
.\.venv\Scripts\python.exe tools/test_zotero_plugin_ui.py --work-dir .test-tmp/full-audit-20261025/packaged085
.\.venv\Scripts\python.exe tools/test_zotero_plugin_ui.py --work-dir .test-tmp/full-audit-20261025/packaged085-ui-f3
```

Each successful invocation produced 30 passing checks in its fixture’s `ui-results.json` and PNGs spanning all five sections, working states, folder/disconnect previews, native pickers, light/dark themes, and 1040/640 widths. The first `packaged085` invocation hit the pre-repair harness JSON polling race before a layout assertion; the same command passed unchanged on retry. The separate `packaged085-ui-f3` run subsequently passed with repaired polling. No 30-check UI repeat was run for 0.8.6 because frontend source was unchanged apart from manifest version.

## Package/source comparison commands

The comparison reads each XPI with `zipfile`, reads the exact helper with PyInstaller’s `CArchiveReader`, and checks every shipped first-party `note_organizer` module in `PYZ.pyz`. Source and frozen code objects are compared recursively after normalizing **only** `co_filename`; optimization level is 0. Raw `marshal.dumps` byte equality is not used because interning representation can differ for equal code objects. The entrypoint is unmarshaled and compared separately. All 31 frontend files/assets and the packaged component notice are compared byte for byte. Runtime MD5 is checked against the XPI runtime member/manifest; SHA-256 identifies each artifact.

The following is the comparison portion of the first 0.8.6 PowerShell stdin script actually executed. It used the prior comparison’s explicit 36-module and 31-asset inventory; its output is preserved without replacement by final-build results.

```powershell
@'
from pathlib import Path
import json, hashlib, marshal, types, zipfile
from PyInstaller.archive.readers import CArchiveReader
out=Path('documentation/audits/2026-10-25')
old=json.loads((out/'frontend-package085-comparison.json').read_text())
xpi=Path('dist/reMarkable-Sync-for-Zotero-0.8.6.xpi'); worker=Path('.test-tmp/zotero-plugin-086-dist/notable-worker.exe')
def sha(b): return hashlib.sha256(b).hexdigest()
def norm(c):
 return c.replace(co_filename='<source>',co_consts=tuple(norm(k) if isinstance(k,types.CodeType) else k for k in c.co_consts))
a=CArchiveReader(str(worker)); pyz=a.open_embedded_archive('PYZ.pyz')
r={'package':str(xpi),'package_sha256':sha(xpi.read_bytes()),'runtime':str(worker),'runtime_sha256':sha(worker.read_bytes()),'runtime_md5':hashlib.md5(worker.read_bytes()).hexdigest(),'comparison':'Recursive Python code object equality after normalizing only co_filename; optimization level 0','python_modules':[],'frontend_files':[]}
for item in old['python_modules']:
 f=Path(item['file']); source=f.read_bytes(); equal=norm(pyz.extract(item['module']))==norm(compile(source,str(f),'exec',optimize=0))
 r['python_modules'].append({'file':item['file'],'module':item['module'],'code_object_equal':equal,'sha256':sha(source)})
with zipfile.ZipFile(xpi) as z:
 r['runtime_manifest']=json.loads(z.read('runtime-manifest.json')); r['packaged_runtime_md5']=hashlib.md5(z.read('runtime/notable-worker.exe')).hexdigest()
 for item in old['frontend_files']:
  f=Path(item['file']); source=f.read_bytes(); r['frontend_files'].append({'file':item['file'],'packaged_bytes_equal':source==z.read(f.relative_to('zotero-support').as_posix()),'sha256':sha(source)})
f=Path('tools/notable_worker.py'); source=f.read_bytes()
r['entrypoint']={'file':str(f),'sha256':sha(source),'code_object_equal':norm(marshal.loads(a.extract('notable_worker')))==norm(compile(source,str(f),'exec',optimize=0))}
f=Path('documentation/ZOTERO_PLUGIN_NOTICES.md'); source=f.read_bytes()
r['component_notice']={'entry':'licenses\\ZOTERO_PLUGIN_NOTICES.md','packaged_bytes_equal':a.extract('licenses\\ZOTERO_PLUGIN_NOTICES.md')==source,'sha256':sha(source),'pillow_label':'MIT-CMU'}
r['diagnostics']={'safe_python_sampler_in_frozen_source':b'dump_traceback_later' not in Path('note_organizer/zotero_worker.py').read_bytes(),'worker_module_source_sha256':sha(Path('note_organizer/zotero_worker.py').read_bytes())}
(out/'frontend-package086-comparison.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'sha256':r['package_sha256'],'frontend':len(r['frontend_files']),'frontend_equal':all(x['packaged_bytes_equal'] for x in r['frontend_files']),'modules':len(r['python_modules']),'modules_equal':all(x['code_object_equal'] for x in r['python_modules']),'entry_equal':r['entrypoint']['code_object_equal'],'notice_equal':r['component_notice']['packaged_bytes_equal'],'worker':r['runtime_sha256'],'manifest_md5':r['packaged_runtime_md5']}))
'@ | .\.venv\Scripts\python.exe -
```

The final 0.8.6 comparison was a separate executed stdin script:

```powershell
@'
from pathlib import Path
import json, hashlib, marshal, types, zipfile
from PyInstaller.archive.readers import CArchiveReader
out=Path('documentation/audits/2026-10-25'); prior=json.loads((out/'frontend-package086-comparison.json').read_text(encoding='utf-8'))
xpi=Path('dist/reMarkable-Sync-for-Zotero-0.8.6.xpi'); worker=Path('.test-tmp/zotero-plugin-086-dist/notable-worker.exe')
def sha(b): return hashlib.sha256(b).hexdigest()
def norm(c): return c.replace(co_filename='<source>',co_consts=tuple(norm(k) if isinstance(k,types.CodeType) else k for k in c.co_consts))
a=CArchiveReader(str(worker)); pyz=a.open_embedded_archive('PYZ.pyz')
r={'package':str(xpi),'package_sha256':sha(xpi.read_bytes()),'runtime':str(worker),'runtime_sha256':sha(worker.read_bytes()),'runtime_md5':hashlib.md5(worker.read_bytes()).hexdigest(),'comparison':'Recursive Python code object equality after normalizing only co_filename; optimization level 0','python_modules':[],'frontend_files':[]}
for item in prior['python_modules']:
 f=Path(item['file']); source=f.read_bytes(); r['python_modules'].append({'file':item['file'],'module':item['module'],'code_object_equal':norm(pyz.extract(item['module']))==norm(compile(source,str(f),'exec',optimize=0)),'sha256':sha(source)})
with zipfile.ZipFile(xpi) as z:
 r['runtime_manifest']=json.loads(z.read('runtime-manifest.json')); r['packaged_runtime_md5']=hashlib.md5(z.read('runtime/notable-worker.exe')).hexdigest()
 for item in prior['frontend_files']:
  f=Path(item['file']); source=f.read_bytes();r['frontend_files'].append({'file':item['file'],'packaged_bytes_equal':source==z.read(f.relative_to('zotero-support').as_posix()),'sha256':sha(source)})
f=Path('tools/notable_worker.py'); source=f.read_bytes(); r['entrypoint']={'file':str(f),'sha256':sha(source),'code_object_equal':norm(marshal.loads(a.extract('notable_worker')))==norm(compile(source,str(f),'exec',optimize=0))}
f=Path('documentation/ZOTERO_PLUGIN_NOTICES.md'); source=f.read_bytes(); r['component_notice']={'entry':'licenses\\ZOTERO_PLUGIN_NOTICES.md','packaged_bytes_equal':a.extract('licenses\\ZOTERO_PLUGIN_NOTICES.md')==source,'sha256':sha(source),'pillow_label':'MIT-CMU'}
r['changes_since_first086build']=[x['file'] for x,y in zip(r['python_modules'],prior['python_modules']) if x['sha256']!=y['sha256']]
(out/'frontend-package086-final-comparison.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sha256':r['package_sha256'],'worker':r['runtime_sha256'],'manifest_md5':r['packaged_runtime_md5'],'frontend_equal':all(x['packaged_bytes_equal'] for x in r['frontend_files']),'modules_equal':all(x['code_object_equal'] for x in r['python_modules']),'entry_equal':r['entrypoint']['code_object_equal'],'notice_equal':r['component_notice']['packaged_bytes_equal'],'changed':r['changes_since_first086build']}))
'@ | .\.venv\Scripts\python.exe -
```

The earlier 0.8.4 and 0.8.5 comparisons used the same byte/code-object method against their then-current snapshots and exact helpers. Their JSON inventories, source hashes, results, and artifact hashes remain preserved. Their full original stdin shell text is not retained here, so the two complete scripts above document the exact 0.8.6 invocations rather than claiming a reconstructed historical command is verbatim.

## Final exact-helper status smoke command

Backend supplied `packaged_status_smoke.py`; this reviewer read it and executed it after the final helper rebuild. It seeds only a temporary synthetic state: one waiting PDF, DOCX/PPTX approvals, and two linked PDFs, one individually paused, under global sync pause. It starts the exact helper with `--debug-stacks`, sends `status` and `shutdown` JSON packets, checks the expected count, and removes its temporary state.

```powershell
$statusTemp = Join-Path (Get-Location).Path '.test-tmp/audit-status-package-smoke/temp'
New-Item -ItemType Directory -Path $statusTemp -Force | Out-Null
$env:TEMP = $statusTemp
$env:TMP = $statusTemp
& '.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe' 'documentation/audits/2026-10-25/packaged_status_smoke.py' --helper '.test-tmp/zotero-plugin-086-dist/notable-worker.exe'
```

Observed output: exact helper SHA-256 `5a1fdddcc86c12b0da09449c83c13ef4c6237a665a660ba22d439367931033ee`, `approved_waiting_sync: 1`, `linked: 2`, `pdfs_received: 1`, return code 0, empty stderr. Output is saved in `packaged-status-smoke086-results.json`.

The original generic status-smoke output was preserved as `packaged-status-smoke086-results.json` before the later 0.8.7 harness extension/run, so the 0.8.6 evidence retains its original helper hash. The command originally wrote the generic filename.
