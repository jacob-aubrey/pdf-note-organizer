# Audit command and evidence index

Commands below run from the project root. Component reports retain their precise focused invocations, source references, intermediate failures, and observations. Disposable fixtures use `.test-tmp`; never substitute the production profile for their temporary profile/data directories. Logs and private account/library snapshots remain local and ignored by Git.

## Complete regression suite

The complete suite was run through the existing Windows inactive-desktop wrapper and resource-bounded batch runner:

```powershell
$env:PYTHONPATH = (Resolve-Path documentation/audits/2026-10-25/runtime-bootstrap).Path
.venv/Scripts/python.exe tools/run_ui_tests.py tools/run_test_batches.py
```

The bootstrap appends the existing private runtime dependencies after normal Python paths. The initial attempt placing the extracted frozen runtime first in `PYTHONPATH` shadowed `unittest` and executed zero tests; it is excluded from counts.

| Run | Result | Evidence |
| --- | --- | --- |
| Initial full suite | 1,443 tests / 118 modules; one obsolete tombstone assertion failed | `.test-tmp/suite-20261025-003248/`, `.test-tmp/ui-tests-25328.log` |
| Full suite after initial repairs | 1,459 tests / 119 modules; all 15 batches passed | `.test-tmp/suite-20261025-082736/`, `.test-tmp/ui-tests-14392.log` |
| Later test-harness repair | Three response-polling regressions passed | `frontend-review.md`, `tests/test_zotero_live_transport.py` |
| Later diagnostic repair | 45 diagnostic/transport/recovery tests passed | `backend-review.md`, `crash-diagnostics-final.log` |
| Final PDF counter repair | 13 counter/diagnostic/transport tests passed | `backend-review.md`, `waiting-transfer-status-tests.log` |

These overlapping focused runs are not added together as a new complete-suite total. All 120 final test modules were exercised; the final small changes received the affected regression suites.

## Build and packaging

The worker was rebuilt from source in the existing complete pinned build environment:

```powershell
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath .test-tmp/zotero-plugin-086-dist --workpath .test-tmp/zotero-plugin-086-build 'Notable Zotero Worker.spec'
.venv/Scripts/python.exe tools/build_zotero_support.py --runtime .test-tmp/zotero-plugin-086-dist/notable-worker.exe --output dist/reMarkable-Sync-for-Zotero-0.8.6.xpi
Get-FileHash dist/reMarkable-Sync-for-Zotero-0.8.6.xpi -Algorithm SHA256
```

`build-086-final.log` records success. Final XPI SHA-256: `f7ec29a3f9c908f202436b3bc3b00dccc86b279ee58c720d22045643c3ea5e6d`. Final helper SHA-256: `5a1fdddcc86c12b0da09449c83c13ef4c6237a665a660ba22d439367931033ee`.

Fresh byte/code-object comparison matched all 31 frontend assets, 36 shipped Python modules, worker entrypoint, and notices (`frontend-package086-final-comparison.json`). Final exact helper smoke:

```powershell
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/packaged_status_smoke.py --helper .test-tmp/zotero-plugin-086-dist/notable-worker.exe
```

Result: exit 0, empty stderr, expected/actual waiting=1, linked=2, received=1, diagnostics enabled. `packaged-status-smoke-results.json`.

## Other checks and live actions

- `git diff --check`: passed after repairs and final build; Git emitted only existing LF/CRLF normalization warnings.
- Python compilation and build-environment `pip check`: passed; component reports identify focused compilation commands. All first-party Python was compiled during the broad static check.
- `node --check` on each of the four frontend JS files and all five `tools/test_zotero_*.cjs` suites: passed. See frontend report for exact native/UI fixture commands and result paths.
- `shared_repro.py`, `backend_repros.py`, and repaired focused suites: see `shared-review.md` and `backend-review.md`. Original observational reproductions are evidence of old failures, not current regression passes.
- Native reader environment: existing reader environment harness on an inactive desktop, WebView2/PDF.js ready without bootstrap error (`reader-environment.log`).
- Read-only cloud probe: 716 catalog entries, 134 folders, 470 active PDFs (`.test-tmp/full-audit-20261025/cloud-readonly-elevated.json`). Twelve saved-source samples rendered with unchanged database bytes (`saved-sources.json`).
- Differential diagnostic stress probe: OFF and Python sampler completed 9,734 and 9,694 loopback requests respectively; old native watchdog crashed with `0xc0000005`. Exact-symbol verification and probe methodology/limits: `python313-crash-address-evidence.json`, `watchdog-probe-approved-results.json`, backend/frontend reports. Early probe teardown failures are explicitly inconclusive.
- Production snapshot: Zotero closed normally, database files and recovery companions copied into disposable backup, copied databases recovered/snapshotted and checked. Sixteen files, eight database integrity checks passed (`pre-085-backup-complete` under private `.test-tmp`). `backup_plugin.py` documents the finite-time snapshot procedure. No live original database was opened for recovery.
- Native Plugins Manager installed final 0.8.6 from the exact XPI using Install Plugin From File. `extensions.json` reports active/enabled 0.8.6 and the installed package/hash matches. Extracted runtime hash also matches (`installed-plugin-086.json`).
- Production Sync now started at 2026-10-25 17:29:55 UTC with existing diagnostics enabled. The final report and production-sync evidence record completion or any remaining failure separately from synthetic tests. The prior 0.8.5 crash evidence remains historical in `live-sync-verification.json`.

Inventory/review used `git status --porcelain`, `git diff`, `rg --files`, targeted `rg -n` searches, bounded full-file reads, SHA-256 hashes, and line-range comparisons. `initial-status.txt` and `initial-diff.patch` preserve the starting local state; ledgers identify every reviewed file and full range. Generated files, vendor assets, and binary dependencies are classified separately.
