# Backend audit command/result index â€” October 25, 2026

Run commands from the repository root in PowerShell. This index records distinct phases; earlier passing runs are not represented as checks of later source changes. `backend-ledger.json` retains original and each repair-phase SHA-256 value. The final backend ledger covers 65 files / 18,598 lines; every included range was inspected.

Fixture setup used throughout:

```powershell
New-Item -ItemType Directory -Force tmp/backend-audit-runtime | Out-Null
$env:TEMP=(Resolve-Path tmp/backend-audit-runtime).Path
$env:TMP=$env:TEMP
```

The initial attempt using the sandbox's default temporary directory failed with WinError 5 before exercising behavior. The permitted workspace fixture directory resolved it.

| ID | Scope / revision phase | Result | Durable output |
| --- | --- | --- | --- |
| A1 | Original B1/B2/B3 observational repros | 3 assertions passed / 5.190 s, confirming defects | `backend-repros.log`, `backend_repros.py` |
| B1 | Complete Zotero discovery before final catalog recovery refinements | 231 passed / 142.909 s | `backend-repairs-zotero.log` |
| B2 | Catalog recovery refinements | 11 passed / 5.691 s | `backend-repairs-focused.log` |
| B3 | Affected worker/review/bridge/recovery/connection suites after catalog refinements | 138 passed / 79.259 s | `backend-repairs-affected.log` |
| B4 | Final initial repairs, including partial two-attachment rename | 55 passed / 34.328 s | `backend-repairs-final-focused.log` |
| R1a | New diagnostic lifecycle tests plus existing transport | 10 passed / 2.672 s | `crash-diagnostics-focused.log` |
| R1b | All repair regressions, transport, recovery after diagnostic repair | 45 passed / 53.553 s | `crash-diagnostics-final.log` |
| R2 | Final PDF status tests plus existing summary/lifecycle/transport | 13 passed / 5.111 s | `waiting-transfer-status-tests.log` |
| R3 | Staged/source union, pause/deletion/unavailable exclusions plus prior summary/lifecycle/transport | 15 passed / 7.045 s | `staged-transfer-status-tests.log` |
| R4a | Real malformed-PDF and cached-log subprocess protocol check before routing repair | Expected failure: JSONDecodeError, child itself exited 0 | `pdf-diagnostic-protocol-before.log` |
| R4b | Repaired protocol plus status, lifecycle, transport and prior summary checks | 16 passed / 8.383 s | `pdf-diagnostic-protocol-after.log` |
| P1 | Approved synthetic localhost comparison, exact CPython 3.13.1 | Off: 9,734 requests, exit 0; old native watchdog: 0xc0000005; replacement: 9,694 requests, exit 0 | `watchdog-probe-approved-results.json`, `watchdog-native-crash-trace.log` |
| P2 | Final exact 0.8.6 helper, disposable mixed Office/PDF/linked/paused state, debug flag enabled | Expected/actual waiting 1, linked 2, received 1; exit 0; empty stderr | `packaged-status-smoke086-results.json` |
| S1 | Changed backend modules and regression file | `py_compile` and scoped `git diff --check` passed | Commands below; no diagnostic errors |
| C1 | Third-party origin/version/license/manifest inspection | Evidence and limits recorded, no full vendor-code review claimed | `dependency-provenance.md`, `dependency-provenance.json` |
| V1 | Read-only closed-backup verifier self-check; additional changes to Python dictionaries only | Three expected source matches and 45 upload transitions detected; no missing identities/changed baselines | `verifier-self-check-results.json` |
| V2 | Read-only native API/file diagnosis of the three unmatched approved sources after parent confirmed idle | 3 live unchanged PDFs, each with exactly one existing matching tablet baseline; no source mutations | `unlinked-pdf-diagnosis.json` |

Reproduction commands:

```powershell
# A1 is historical: it expects the original bugs and is not a current regression suite.
.venv/Scripts/python.exe -m unittest discover -s documentation/audits/2026-10-25 -p backend_repros.py -v

# B1: import unittest first to avoid frozen dependency files shadowing stdlib.
# The project venv lacked some optional plugin dependencies. Child transports
# also receive the extracted runtime directory through PYTHONPATH.
.venv/Scripts/python.exe -c "import unittest,sys,os; from pathlib import Path; runtime=str(Path('.test-tmp/scheduled-repair-20261024/runtime-dependencies').resolve()); sys.path.append(runtime); os.environ['PYTHONPATH']=runtime; result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('tests',pattern='test_zotero*.py')); sys.exit(not result.wasSuccessful())"

# B2, B3, B4: the named suite grew as regressions were added.
.venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs -v
.venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_worker tests.test_zotero_recovery_regressions tests.test_zotero_review tests.test_zotero_connections tests.test_zotero_bridge tests.test_zotero_bridge_recovery -q
.venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_bridge tests.test_zotero_bridge_recovery -q

# R1a and R1b: complete existing pinned build venv, no runtime bootstrap needed.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs.DiagnosticSafetyTests tests.test_zotero_transport -q
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_transport tests.test_zotero_recovery_regressions -q

# R2: final status repair, plus lifecycle/transport and established summary check.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs.WaitingTransferStatusTests tests.test_zotero_worker.WorkerTests.test_filing_summary_separates_approved_linked_and_received tests.test_zotero_audit_repairs.DiagnosticSafetyTests tests.test_zotero_transport -q
# R3 reran the same command after adding two staged-upload regressions.

# R4a: historical expected failure before supported PyMuPDF stderr routing.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs.PdfDiagnosticTransportTests -q
# R4b: final affected checks after routing repair.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs.PdfDiagnosticTransportTests tests.test_zotero_audit_repairs.WaitingTransferStatusTests tests.test_zotero_worker.WorkerTests.test_filing_summary_separates_approved_linked_and_received tests.test_zotero_audit_repairs.DiagnosticSafetyTests tests.test_zotero_transport -q

# P1: disposable localhost fixture only; executed with approved socket access.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/run_watchdog_probe.py

# P2: executed by the package reviewer after the final rebuild.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/packaged_status_smoke.py --helper .test-tmp/zotero-plugin-086-dist/notable-worker.exe
# Historical P2 used the earlier fixture (expected1/2/1). The current runner
# includes staged rows and expects2/4/1; run it against the rebuilt0.8.7 helper.

# Closed-backup-only verifier self-check; did not open live state.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/verify_sync_state.py --current-state .test-tmp/full-audit-20261025/pre-085-backup-complete/notable --summary .test-tmp/full-audit-20261025/verifier-baseline-self-check.json --details .test-tmp/full-audit-20261025/verifier-baseline-self-check-private.json

# V2: only after parent confirmed stopped/idle; read-only API outside sandbox.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/diagnose_unlinked_pdfs.py --state "$env:APPDATA/Zotero/Zotero/Profiles/9v5afvrs.default/notable"

# S1: repeated after each final source change; all passed.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m py_compile note_organizer/zotero_worker.py note_organizer/zotero_bridge.py note_organizer/zotero_review.py tests/test_zotero_audit_repairs.py
git diff --check -- note_organizer/zotero_worker.py note_organizer/zotero_bridge.py note_organizer/zotero_review.py tests/test_zotero_audit_repairs.py
```

Probe attempts that did not establish network correctness are retained explicitly: `watchdog-probe-results.json` records the first harness's unrelated buffered-stdin finalization failure after both churn workloads completed; `watchdog-probe-final-results.json` records sandbox WinError 10013 for off/safe modes and a native watchdog crash. An intervening live-stdin driver was interrupted after waiting for a failed child and produced no usable comparison. The corrected approved driver bounds each child to 18 seconds and accesses no real Zotero/account/device data.

Historical 0.8.6 helper SHA-256: `5a1fdddcc86c12b0da09449c83c13ef4c6237a665a660ba22d439367931033ee`. Historical 0.8.6 XPI SHA-256, supplied by the parent packaging task: `f7ec29a3f9c908f202436b3bc3b00dccc86b279ee58c720d22045643c3ea5e6d`. R1 current source: `note_organizer/zotero_worker.py:1515-1572`. R2 current source: `note_organizer/zotero_worker.py:157-162`. Live installation/sync evidence belongs to the parent report; no source/fixture result here substitutes for that outcome.

The staged-counter repair for 0.8.7 is at `note_organizer/zotero_worker.py:163-167`; final worker SHA-256 is `2bfef9cd8d7112b8122f19c8b69f9a5367f403eed7e9c1e76b40f441f52d9571`. Its current exact-helper fixture expects waiting 2, linked 4, received 1. Final 0.8.7 package hash/smoke and post-sync execution are recorded by the parent/package reviewer when available.

The subsequent PDF-diagnostic repair is at `note_organizer/zotero_worker.py:1576-1580`. The final combined backend worker SHA-256 is `dcb67d8caa48eb57d7c356231ff83de9c2d3045a7c994f6cefb038f1ad9c2424`; the earlier staged-counter hash above records its prior phase. Frontend import-time environment routing and generic protocol error are covered by the frontend owner's ledger and controller tests.
