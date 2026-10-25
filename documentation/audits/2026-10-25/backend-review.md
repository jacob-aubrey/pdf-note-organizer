# Backend audit, October 25, 2026

`backend-command-results.md` is the concise index of commands, revision phases, results, logs, probes, and the final packaged-helper smoke.

The original audit reviewed 64 files / 17,955 lines (24 implementation files and 40 test files); this is a source audit, not a claim that live tablet/account behavior is proven. Every listed file was read in full. Truncated combined tool outputs were followed by targeted rereads of the omitted sections. Existing user changes were preserved. After the user authorized repairs and updated installation, B1-B3 were repaired as recorded below. `backend-ledger.json` retains the original audit hashes and records the current repair revision and additional test file.

## Confirmed findings

### B1 â€” P2: conflict recovery cannot recognize its own completed write

`note_organizer/zotero_worker.py:1350-1353` requires the original cloud hash and native record version before it examines or recovers an applying conflict. The action is journaled at line 1362, the cloud mutation occurs at lines 1364-1366, and completion is recorded at line 1377. If the cloud commits but its response is lost, both conflict choices subsequently fail the stale hash guard. A normal sync sees matching copies and advances the folder mapping, but never retires the existing applying conflict. Dismiss also refuses it (`zotero_review.py:145-146`). This leaves a persistent, unresumable review despite the chosen update having completed.

Evidence: `backend_repros.py::ConflictRecoveryRepro.test_lost_conflict_confirmation_leaves_an_unresumable_applying_review`. It executes the real cloud writer against `MemoryCloud`, injects a lost response after a successful commit, verifies the actual chosen remote name, retries, syncs, and checks that the applying review remains and cannot be dismissed. Recover by validating the recorded chosen target as an already-completed step before rejecting any changed revision; journal enough information to distinguish that from independent edits.

### B2 â€” P2: resumed cloud filing overwrites a newer tablet rename

`note_organizer/zotero_worker.py:954-958` exempts every applying cloud review from the reviewed cloud hash check. Later, lines 1054-1066 fetch the newest item and use that newest hash to apply the old filename and destination. If filing is interrupted after its tablet update but before `review.finish`, and the user subsequently renames that tablet document, Resume silently overwrites the user's newer name. This is an independent edit, rather than the helper recognizing its own completed mutation.

Evidence: `backend_repros.py::ConflictRecoveryRepro.test_interrupted_cloud_filing_overwrites_a_subsequent_tablet_rename` injects the completion interruption, makes a separate successful tablet rename, resumes the old review, and observes its old name replace the newer one. Recovery should accept only the original revision or a specifically recorded, already-applied target, and request fresh review for independent edits.

### B3 â€” P2: invalid Windows filename commits a partial collection move

`note_organizer/zotero_bridge.py:583-589` updates the parent's collection membership before validating its new filename. A tablet-side name such as `Invalid:WindowsName`, combined with a destination move, removes the old home and adds the new home before `validate_document_filename` raises. Sync reports a failed action even though Zotero membership was already changed. All affected filenames should be validated before committing collection changes; multi-attachment rename failures also need recoverable step tracking.

Evidence: `backend_repros.py::PartialDesktopMoveRepro.test_invalid_windows_name_is_validated_after_collection_membership_changes` verifies that the method raises `ValueError` but the parent's only collection is already the target.

## Verification

Three focused audit reproductions passed their observational assertions against the unmodified implementation. Passing here means the defects were reproduced; these are deliberately not fix-validation tests. Output is retained in `backend-repros.log`.

```powershell
New-Item -ItemType Directory -Force tmp/backend-audit-runtime | Out-Null
$env:TEMP=(Resolve-Path tmp/backend-audit-runtime).Path
$env:TMP=$env:TEMP
.venv/Scripts/python.exe -m unittest discover -s documentation/audits/2026-10-25 -p backend_repros.py -v
```

The first attempt used the sandbox's default temporary directory and could not create fixture subdirectories (WinError 5); it did not exercise product behavior. Redirecting temporary files to the permitted workspace resolved that environmental problem. No escalation or real data mutation was needed.

Reviewed positive mechanisms include SQLite-bound connection namespaces and separate process leases; pre-write source digests; immutable original/source preservation; cloud generation and item-hash checks; approval-bound first publication; independent upload receipt recovery; source and managed-view distinction; explicit trash decisions; stable page UUID tags; deferred retry of incomplete OCR; Windows DPAPI grants and localhost-pinned transport; guarded source cleanup with two verified file handles; and serialized desktop service writes.

## Authorized repairs and regression verification

**B1 repaired:** `zotero_worker.py:1403` now records the selected native target, attachment filenames/digests, original native record, original cloud hash, and intended cloud target before side effects. It recognizes an already-completed native step or the exact cloud target with unchanged non-name content after a lost response; a saved post-commit hash provides a stronger receipt when available. Repeated recovery does not replay completed cloud mutations. A partial two-attachment rename resumes only remaining filenames. Independent changes are retained, and an applying decision cannot change sides. `zotero_review.py:229-258` preserves consent and adds durable journal checkpoints within the existing SQLite journal.

**B2 repaired:** `zotero_worker.py:1012-1040,1122-1127` saves and checks an intended cloud rename/move before native filing writes and before cloud changes. Resume uses the original compare-and-swap hash and recognizes its own completed target; it does not apply the old filename to the latest independently changed revision. A fresh Sync reopens a changed unlinked paper with current metadata and fresh consent (`684-722`) while retaining the previously created reference identity. A fully registered matched paper completes only its remaining bookkeeping (`731-748`), leaving subsequent tablet changes to ordinary sync.

**B3 repaired:** `zotero_bridge.py:573-611` constructs and validates the complete target membership/filename plan, all affected live attachments, and source digests before changing membership. Windows-invalid names and missing secondary attachments now leave membership untouched. Recovery verifies already-renamed attachment bytes and skips their native rename.

`tests/test_zotero_audit_repairs.py` adds twelve regressions using temporary Zotero fixtures and the actual cloud compare-and-swap writer against an in-memory transport. They cover lost cloud/native responses, restart, subsequent rename/tag edits, immutable saved choices, partial attachment rename, fresh review without duplicate references, matched-paper bookkeeping, invalid Windows filenames, and unavailable attachments. They do not establish live account/device behavior.

Validation evidence:

- The complete `test_zotero*.py` discovery passed **231 tests in 142.909 seconds** before the final catalog recovery refinements (`backend-repairs-zotero.log`).
- After the catalog refinements, the affected worker/review/bridge/recovery/connection suite passed **138 tests in 79.259 seconds** (`backend-repairs-affected.log`).
- The new regression and bridge suites passed **55 tests in 34.328 seconds**, including all twelve initial repair regressions (`backend-repairs-final-focused.log`). That repair handoff contained 65 files / 18,380 lines; the subsequent diagnostic repair below updates the same ledger to 18,474 lines and fifteen added regression tests.
- `py_compile` passed for the three changed modules and new regression file. `git diff --check` passed for those paths; Git emitted only its existing LF-to-CRLF notice.

Commands, after setting `TEMP` and `TMP` to the workspace fixture directory shown above:

```powershell
# Full Zotero discovery used extracted packaged dependencies because the main
# project venv does not contain every optional plugin dependency. unittest is
# imported first to avoid frozen dependencies shadowing stdlib unittest.
.venv/Scripts/python.exe -c "import unittest,sys,os; from pathlib import Path; runtime=str(Path('.test-tmp/scheduled-repair-20261024/runtime-dependencies').resolve()); sys.path.append(runtime); os.environ['PYTHONPATH']=runtime; result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('tests',pattern='test_zotero*.py')); sys.exit(not result.wasSuccessful())"
.venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_worker tests.test_zotero_recovery_regressions tests.test_zotero_review tests.test_zotero_connections tests.test_zotero_bridge tests.test_zotero_bridge_recovery -q
.venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_bridge tests.test_zotero_bridge_recovery -q
.venv/Scripts/python.exe -m py_compile note_organizer/zotero_worker.py note_organizer/zotero_bridge.py note_organizer/zotero_review.py tests/test_zotero_audit_repairs.py
git diff --check -- note_organizer/zotero_worker.py note_organizer/zotero_bridge.py note_organizer/zotero_review.py tests/test_zotero_audit_repairs.py
```

The historical observational repro file intentionally expects the original defects; it is retained as historical evidence and is not a current passing regression suite. Packaging, installation, final repository-wide testing, and live sync are performed separately by the parent audit task after this handoff.

## R1: live-sync crash from unsafe optional native diagnostic watchdog repaired

The parent task's authorized live sync of 0.8.5 crashed with Windows exception `0xc0000005` in `python313.dll` version `3.13.1150.1013`, offset `0x2af768`. The profile had enabled the optional `--debug-stacks` diagnostic option. Its last timed stack dump ended midway through writing `File `, while the main Python thread was doing local Zotero HTTP work. This subtask did not retry that production sync or change production preferences.

The parent/frontend forensic investigation mapped that address to PE function range `0x2af734â€“0x2af883`, with faulting instruction `mov rax,[rsi+0x70]` immediately after writing `File `. Matching official CPython 3.13.1 AMD64 symbols, extracted as data without installation and loaded with `SYMOPT_EXACT_SYMBOLS`, confirm `dump_frame + 0x34`, `Python/traceback.c:898`, line displacement zero. The exact DLL/PDB hashes, bytes, source links, and limits are retained in `python313-crash-address-evidence.json`. The crash is in the diagnostic stack walker; the interrupted Python stack's HTTP location alone is not evidence that HTTP corrupted memory. The invalid/freed object mechanism remains an inference without a native crash dump and registers. The inspected DPAPI pointer declarations use the correct 64-bit pointer/result signatures, and no ctypes memory-corruption evidence was found.

The official [CPython issue 140815](https://github.com/python/cpython/issues/140815) and merged [3.13 fix 140985](https://github.com/python/cpython/pull/140985) describe invalid/freed frame and code-object access by `faulthandler.dump_traceback_later`. The fix merged November 5, 2025, after this packaged interpreter's December 3, 2024 build. This upstream defect matches the native crash location and incomplete dump. A newer [code-metadata race report](https://github.com/python/cpython/issues/158200) further cautions against treating the native asynchronous dumper as risk-free; that report concerns different tested versions and is not used as proof of this exact crash.

`zotero_worker.py:1515-1572` replaces the optional native timed watchdog with an ordinary Python diagnostic thread. `sys._current_frames()` retains Python frame objects, `traceback.print_stack` formats them under normal Python synchronization, and no locals are printed. The existing 20-second diagnostic interval and file are retained. An Event wakes shutdown immediately; joining is bounded to two seconds. The diagnostic thread owns and closes its stream, including after worker startup failure, and optional emission errors cannot interrupt sync. `_serve` contains the existing transport unchanged. This is a small adaptation of existing diagnostics using the standard library, with no dependency or subsystem addition.

Independent isolated comparison, using the exact installed build environment's CPython 3.13.1 and disposable localhost HTTP data, reproduced the native watchdog failure:

| Diagnostic mode | Result | Completed HTTP requests | Elapsed |
| --- | --- | ---: | ---: |
| Disabled | Exit 0 | 9,734 | 6.391 s |
| Previous native timed watchdog | Access violation `0xc0000005` | No completion record | Crashed |
| Replacement Python sampler | Exit 0 | 9,694 | 6.015 s |

This accelerated probe sampled every 0.01 seconds to expose the race; it does not claim the production failure is deterministic at the normal 20-second interval. It contacted only its own synthetic server on an ephemeral `127.0.0.1` port, with no Zotero/account/device access. `watchdog-probe-approved-results.json`, the retained native trace, and the scripts contain the reproducible evidence. The successful comparison ran with approved localhost socket access because the default sandbox denied these sockets with WinError 10013. The earlier sandbox comparison therefore proves no successful network workload. Its old native watchdog still crashed, while the disabled and safe modes returned ordinary connection errors (`watchdog-probe-final-results.json`).

The very first churn probe completed both 12-second workloads but its harness left a daemon buffered-stdin reader active during interpreter shutdown. Both modes then failed with `_enter_buffered_busy`; those results (`watchdog-probe-results.json`) are explicitly inconclusive for the live sync fault. The corrected driver supplies EOF, bounds each subprocess to 18 seconds, and captures its outputs. One intervening driver attempt waited on a live stdin pipe after a failed workload and was interrupted; it produced no usable comparison evidence.

Three additional regression tests verify emission without calling the native watchdog, clean thread/stream exit on startup failure, and clean JSON transport through debug-enabled EOF. Together with all initial repair tests, existing transport tests, and recovery regressions, **45 tests passed in 53.553 seconds** (`crash-diagnostics-final.log`). The earlier diagnostic/transport check passed 10 tests in 2.672 seconds. Compilation and `git diff --check` passed. The final ledger records 65 files / 18,474 lines, preserving original audit and pre-watchdog-repair hashes.

```powershell
$env:TEMP=(Resolve-Path tmp/backend-audit-runtime).Path
$env:TMP=$env:TEMP
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs tests.test_zotero_transport tests.test_zotero_recovery_regressions -q
# Read-only synthetic localhost comparison; needs socket access outside sandbox.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/run_watchdog_probe.py
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m py_compile note_organizer/zotero_worker.py tests/test_zotero_audit_repairs.py
git diff --check -- note_organizer/zotero_worker.py tests/test_zotero_audit_repairs.py
```

Source was frozen for the parent's 0.8.6 packaging/install/live-sync verification. The isolated source probe verifies the diagnostic repair; a successful production sync and packaged-helper behavior remain separate acceptance checks owned by the parent task.

## R2: waiting-transfer status corrected before final 0.8.6 installation

Read-only examination of the pre-0.8.5 backup found 43 approved Zotero rows reported as waiting for sync: 34 DOCX, six PPTX, and three PDFs. Office documents are filed locally by design, so that count incorrectly promised tablet transfers. `zotero_worker.py:157-162` now counts only approved PDF-eligible rows. Known cloud PDF rows remain eligible, and older rows without an original path fall back to their saved/proposed filename. An explicit Office source path takes precedence over filename fallback. The change does not alter approval, transfer, pause, or link behavior.

Two focused regressions exercise mixed PDF/Office rows, uppercase extensions and legacy filenames, cloud PDF eligibility, inbox/native counterpart deduplication, pending rows, linked/paused documents, and global sync pause. Together with the existing transfer-summary, diagnostic lifecycle, and transport tests, **13 tests passed in 5.111 seconds** (`waiting-transfer-status-tests.log`). Compilation and `git diff --check` passed. The rebuilt exact packaged helper passed its disposable debug-enabled status smoke: waiting = 1, linked = 2, received = 1, exit 0, empty stderr. Its SHA-256 is `5a1fdddcc86c12b0da09449c83c13ef4c6237a665a660ba22d439367931033ee`; reproducible commands and results are in `packaged_status_smoke.py` and `packaged-status-smoke086-results.json`. The ledger at this repair phase covered 65 files / 18,513 lines and seventeen new regression tests, retaining the prior repair hashes.

```powershell
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs.WaitingTransferStatusTests tests.test_zotero_worker.WorkerTests.test_filing_summary_separates_approved_linked_and_received tests.test_zotero_audit_repairs.DiagnosticSafetyTests tests.test_zotero_transport -q
```

## R3: P3 staged-upload status undercount repaired for 0.8.7

The closed pre-0.8.5 backup contains 456 registered link identities: 411 with `uploaded=True` and 45 with `uploaded=False`, plus three approved eligible PDFs without mappings. Registration is durable intent and can precede transfer (`zotero_bridge.py:384-405`); actual upload and acknowledgement occur at `435-449`. The UI label `approved, waiting for sync` (`zotero-support/ui.js:293-294`) therefore undercounted the queue when it showed only the three unlinked approvals. The closed backup's pause/deletion controls leave 43 of the 45 staged mappings eligible, making the combined waiting count 46 at that snapshot. A registered or linked count is not evidence that every PDF was already transferred.

`zotero_worker.py:163-167` now unions eligible staged Zotero-source identities into the existing PDF-only waiting set, deduplicates by source, and excludes unavailable and individually paused/deletion-suspended links through the existing review policy. Global sync pause retains the waiting count. The linked identity count is unchanged. Two additional regressions cover staged/source deduplication, uploaded transitions, individual pause, confirmed deletion, unavailable rows, non-upload origins, and missing sources. The affected status, diagnostic lifecycle, transport, and existing summary checks passed **15 tests in 7.045 seconds** (`staged-transfer-status-tests.log`). Compilation and `git diff --check` passed.

The final product source is frozen for 0.8.7. `backend-ledger.json` records 65 files / 18,549 lines and nineteen added regression tests; worker SHA-256 is `2bfef9cd8d7112b8122f19c8b69f9a5367f403eed7e9c1e76b40f441f52d9571`. The updated disposable packaged-helper smoke expects waiting = 2, linked = 4, received = 1, including active, individually paused, and unavailable staged mappings. Its execution after the rebuild is owned by the package reviewer and is separate from the completed 0.8.6 fixture evidence.

## Read-only post-sync verifier

`verify_sync_state.py` is an audit-only standard-library script for the parent to run after the helper becomes idle. It opens SQLite with `mode=ro`, snapshots each database into memory under a finite deadline, runs integrity checks, and detects database/config/WAL changes during capture. It compares the three previously unlinked eligible approvals to current source identities, baseline digests, uploaded flags, annotation/publication receipts, and retained original bytes. It reports pre/post staged and uploaded mappings separately, duplicate source/view identities, unchanged baseline identities, pending/applying/error indicators, upload receipts, cleanup/deletion queues, retained source manifest integrity/reference statistics, and bulk/recovery state. It does not load product classes or credentials or call any API. The public report contains counts/booleans; the three-paper titles/identifiers remain in `.test-tmp`.

Only the closed backup has been inspected for this verifier's self-check. Comparing that backup with itself passed and identified exactly three unlinked PDFs, 411 acknowledged uploads, 45 staged mappings, and 43 eligible staged uploads. All present database `quick_check` results were `ok`, with no capture-time changes. No live database was opened by this subtask while sync was running. Journal receipts remain distinct from independent cloud/device/native-state verification.

An additional in-memory-only difference check added three synthetic matching source mappings and marked all 45 staged records uploaded, without writing either database. The verifier correctly reported three matches with matching baselines/upload flags, 45 staged-to-uploaded transitions, no missing prior identities, and no changed prior baseline hashes. `verifier-self-check-results.json` records these checks.

```powershell
# Parent: execute only after sync is idle, or point to a closed post-sync snapshot.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/verify_sync_state.py --current-state "$env:APPDATA/Zotero/Zotero/Profiles/9v5afvrs.default/notable"
```

Default outputs are `documentation/audits/2026-10-25/post-sync-verification.json` and `.test-tmp/full-audit-20261025/post-sync-private-details.json`. Each database has a ten-second read deadline; separate database snapshots are not one cross-database transaction. Production outcome belongs to the parent report.

## R4: confirmed PyMuPDF diagnostic leak into the JSON transport repaired

The long 0.8.6 production run stopped without a matching recent Windows crash event. Its last safe stack snapshot showed ordinary tag HTTP work. Because the offending stdout/stderr was not retained for that run, its exact exit trigger is unproven. A separate concrete protocol defect was reproduced with the pinned dependency and real helper dispatch: PyMuPDF caches its stdout message and development-log streams at import, so `redirect_stdout(sys.stderr)` around dispatch does not catch those cached writes. A recoverable malformed PDF can consequently emit non-JSON text into the helper's JSON channel; the frontend then deliberately stops the process on invalid framing. The frontend owner's real-controller fixture confirmed that response, even with a valid JSON packet following the diagnostic.

[PyMuPDF's official diagnostic documentation](https://pymupdf.readthedocs.io/en/latest/app3.html#diagnostics) describes its stdout default and supported routing. The frontend now supplies `PYMUPDF_MESSAGE=fd:2` before import and uses a fixed, non-content protocol error message. The backend additionally routes both supported message/log streams to `sys.stderr` at `zotero_worker.py:1576-1580`, before worker construction, protecting direct JSON-helper entry points during PDF work. Strict malformed-JSON handling remains in place; no PDF-diagnostic text is accepted as a protocol packet.

The new subprocess regression imports PyMuPDF before `main`, creates a disposable in-memory PDF containing `q garbage Q`, reopens it for text extraction and rendering, and emits a cached development log. It exercises the actual `_serve` loop with no launch routing environment variables. Before the backend repair it failed JSON decoding (`pdf-diagnostic-protocol-before.log`); afterward stdout contains exactly the expected JSON response and both PDF/development diagnostics go to stderr. **16 affected protocol, status, lifecycle, transport, and existing summary tests passed in 8.383 seconds** (`pdf-diagnostic-protocol-after.log`). Compilation and scoped `git diff --check` passed.

The final backend ledger now records 65 files / 18,598 lines and twenty added regression tests. Frozen worker SHA-256 is `dcb67d8caa48eb57d7c356231ff83de9c2d3045a7c994f6cefb038f1ad9c2424`. Packaging and the next live run remain the parent's acceptance checks.

## Three unlinked approved PDFs: read-only native diagnosis

After the parent declared the helper stopped and ran the verifier, `diagnose_unlinked_pdfs.py` used the existing encrypted grant with `interactive=False` for read-only Zotero GETs and local file hashes. All three sources and parents are live; content type and extension are PDF, and source bytes still match their approvals. They are in the current connected scope, have no previous-connection exclusions or managed-view markers, and each has exactly one existing available tablet mapping with the same original-PDF digest.

`zotero_bridge.py:355-360` intentionally prevents another upload of that exact PDF and requests reference reconciliation. These three approvals therefore do not represent three missing tablet originals. Their parent memberships also differ from the formerly approved tablet-home collections, so reference/home selection needs a current decision. The duplicate guard runs before automatic source registration; this explains the absent new source mappings. The parent should surface those reconciliation exceptions rather than create redundant uploads or assume a completed transfer from the generic waiting count.

Public checks and limits are retained in `unlinked-pdf-diagnosis.json`. Titles, source keys, local paths, and counterpart mapping IDs are confined to `.test-tmp/full-audit-20261025/unlinked-pdf-diagnosis-private.json`. No authorization dialog, library change, file rename/move, cloud write, or reapproval occurred.

```powershell
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe -m unittest tests.test_zotero_audit_repairs.PdfDiagnosticTransportTests tests.test_zotero_audit_repairs.WaitingTransferStatusTests tests.test_zotero_worker.WorkerTests.test_filing_summary_separates_approved_linked_and_received tests.test_zotero_audit_repairs.DiagnosticSafetyTests tests.test_zotero_transport -q
# Read-only localhost permission is required outside the socket-restricted sandbox.
.test-tmp/handwriting-rapidocr/venv/Scripts/python.exe documentation/audits/2026-10-25/diagnose_unlinked_pdfs.py --state "$env:APPDATA/Zotero/Zotero/Profiles/9v5afvrs.default/notable"
```

## Limits

Synthetic cloud and Zotero adapters establish application behavior under controlled failures. They do not establish live tablet firmware behavior, genuine multi-device account synchronization, concurrent Zotero account sync, account conflict resolution, or production data correctness. This subtask changed only its three assigned modules, new test file, and audit documentation; it did not mutate a real account/library/device. The repository-wide report records broader suite/build/native UI and explicitly authorized live-sync results separately. Exact-target recovery intentionally rejects independently changed cloud content when no commit receipt proves the old operation; those cases require current review rather than replaying stale intent.

No new capability or subsystem replacement was implemented or proposed. The repairs described above are small adaptations to existing state journals and validation and do not require new dependencies. Installed Zotero/native API compatibility and component provenance are reviewed by the frontend/shared audit owners.
