# Full plugin audit — October 25, 2026

Status: source review and broad regression tests complete. The first installed live sync exposed a native diagnostic crash; the installed 0.8.6 run transferred43staged PDFs but stopped during linked-paper processing. Transport diagnosis and the final0.8.7 update are in progress.

The initial audit did not support a clean bill of health. Three reproducible recovery defects affected the plugin, two frontend issues needed correction, and the wider shared-code review found two additional metadata/extraction problems. The existing full regression run also found one obsolete test assertion. Repairs reuse the existing journals, native adapters, extractor, and runtime packaging; no runtime dependency or replacement subsystem was added.

## Exact target and coverage

The audit started at commit `d84f9516f4ed8b0623e37c3ecdf254cd386687c0` and included the user's existing modified and untracked files. `initial-status.txt`, `initial-diff.patch`, and `inventory.json` preserve that starting state. Those edits were retained. Nothing has been pushed or merged.

Every line of the **263 initial first-party code files / 66,989 lines** was reviewed, including the plugin, helper/backend, shared components, standalone application, scripts, tests, configuration code, and archived implementation. The merged `coverage-ledger.json` records hashes, ranges, classifications, and evidence; `coverage-summary.json` checks completeness. With the added repair tests and final changes, the current ledger covers **265 first-party code files / 67,725 lines**, with no uncovered file or range. This is source-review coverage; it is not a claim of 100% executed-line or branch coverage. Added repair tests are recorded in the individual ledgers. The initial tree contains 749 tracked or relevant untracked files overall.

Vendored PDF.js, compiled native libraries, model weights, fonts, and other binary assets were inventoried and checked for version/provenance/license evidence. They are not claimed as manually reviewed upstream source. Ignored environments, build outputs, private library data, caches, old scratch trials, and generated reports are separate from authored project source. The archived v1 implementation was inspected but was not launched against its relative `notes_watcher.db`; it is not the installed plugin.

## Findings and repairs

| ID | Finding | Disposition |
| --- | --- | --- |
| B1, P2 | A lost conflict-resolution response left a permanently applying review. | Durable intent/checkpoints recognize completed cloud/native actions without replay; attachment-level recovery resumes remaining work. |
| B2, P2 | Resuming interrupted filing could overwrite a newer tablet rename. | Compare the original revision and recorded target/receipt; preserve independent edits and require fresh review when needed. |
| B3, P2 | Invalid Windows filenames could change collection membership before failing. | Validate the complete membership/attachment filename plan before native writes. |
| F1, P2 | UI and setup documentation promised native PDF recognition fallback that was deliberately disabled. | Copy now describes title-verified DOI metadata and manual citation review accurately. |
| F2, P3 | Directory-style helper health checked the EXE but could overlook missing/corrupt DLLs or models. | Validate every runtime-manifest member before reuse; existing extractor performs repair. The prior one-file 0.8.4 package was unaffected by this conditional gap. |
| SH-1, P2 | Standalone Inbox Smart metadata could accept a bibliography-only DOI for a very similar cited paper. | Require document-level DOI evidence; retain local metadata for bibliography-only candidates. This was outside the current plugin's separate DOI verification path. |
| SH-2, P3 | A partly unreadable PPTX could retain a clean review status. | Omitted/unreadable slides now require review, including the actual plugin proposal path. Original files remain retained. |
| SH-3 | Renderer test expected a generic unsupported-item error for an invalid tombstone. | Corrected the obsolete fixture expectation; renderer safeguards and valid deletion behavior remain intact. |
| F3 | Native/UI test harness could read an empty/partial response during a write. | Repaired bounded polling; three transport regressions passed. This harness is not shipped. |
| R1, live sync | Periodic native traceback diagnostics crashed the Python 3.13.1 helper during catalog checks. | Exact official symbols locate the fault in `dump_frame`; the old watchdog reproduces the crash in an isolated loopback test. Replaced it with retained Python frame snapshots on an ordinary thread. OFF and replacement runs completed 9,734 and 9,694 requests; the old watchdog crashed. The native watchdog no longer runs; the later0.8.6 stop has no corresponding observed Windows crash event and is investigated separately. |
| R3, P3 | Staged approved mappings with `uploaded=False` were omitted from the broad waiting-for-sync count. | Final0.8.7 includes eligible staged sources, deduplicates sources, excludes paused/deletion-suspended/unavailable links, and preserves global-pause semantics. Fifteen affected status/transport/lifecycle tests passed. |
| R2, live status | Forty stored Office files were included in the 43-paper tablet-transfer waiting count, although Office-to-PDF conversion is outside scope. | Count only PDF-eligible approvals, retain legacy filename support, and preserve source deduplication. Two mixed-format/link/pause regressions passed. |

Precise source references, reproductions, and repair validation are in `backend-review.md`, `frontend-review.md`, and `shared-review.md`. Original observational repros deliberately assert the old defects and remain historical evidence; current repair regressions are separate.

## Verification

| Check | Result/evidence |
| --- | --- |
| Initial complete regression suite | 1,443 tests / 118 modules; one stale tombstone assertion failed. `.test-tmp/suite-20261025-003248/` and `.test-tmp/ui-tests-25328.log`. |
| Backend repairs | 12 new recovery/path regressions; final new+bridge run 55 passed, affected run 138 passed. See backend report/logs. |
| Shared repairs | 41 tests passed; real ZIP/XML and actual plugin proposal probes verify incomplete-PPTX review. |
| JavaScript | Four frontend syntax checks and five controller/native adapter suites passed after repairs. |
| Exact 0.8.5 package | 53 native Zotero checks passed, including bundled OCR, 30-document bulk import/reuse, tags, native annotations, connections, cancellation controls, and source preservation. All 30 rendered UI checks passed; a second isolated rerun after the harness repair also passed. |
| Final packaging | Fresh full PyInstaller 0.8.6 build completed using the existing pinned Python 3.13 environment. All 31 frontend files and all 36 bundled application modules plus the worker entry point match final source. `frontend-package086-final-comparison.json`. |
| Existing saved tablet sources | 12/12 sampled saved sources rendered; database bytes unchanged. `.test-tmp/full-audit-20261025/saved-sources.json`. This is a sample, not a full-library rendering claim. |
| Read-only real cloud connection | Passed: 716 catalog items, 134 folders, 470 active PDFs. `.test-tmp/full-audit-20261025/cloud-readonly-elevated.json`. |
| Update recovery snapshot | Zotero closed normally; 16 configuration/plugin/database snapshots, eight databases passed integrity checks. Private evidence: `.test-tmp/full-audit-20261025/pre-085-backup-complete/`. Database recovery journals were retained with their stopped databases; only disposable copies were opened for snapshot recovery. |
| Final full suite | **1,459 tests / 119 modules passed**, plus three late-added transport regressions passed separately. All 120 current test modules were exercised. `.test-tmp/suite-20261025-082736/` and `.test-tmp/ui-tests-14392.log`. |
| Installed version | Native plugin manager installed **0.8.6**, active/enabled; installed XPI SHA-256 matches the final verified package. `installed-plugin-086.json` (17:29:13 UTC), `installed-plugin-086-status.json` (live endpoint confirms 0.8.6). Historical 0.8.5 installation evidence remains separate. |
| Crash/status repair tests | 45 diagnostic/transport/recovery tests passed; 13 final counter/diagnostic/transport tests passed. The first 0.8.6 build passed 53 native/OCR checks with diagnostics enabled. After the final status-only rebuild, full package/source comparison and exact frozen-helper status smoke passed. These overlapping runs are not summed into a new whole-suite test count. |
| Reader runtime | WebView2/PDF.js ready, no bootstrap error; `reader-environment.log`. |
| Real sync | First installed 0.8.5 attempt crashed before the transfer stage. Version0.8.6 uploaded43eligible staged PDFs, then stopped during linked-paper processing; final diagnosis/retry is pending. See `live-sync-086-verification.json` and `post-086-stopped-verification.json`. The prior failure is preserved in `live-sync-verification.json`. |

The final deployment XPI is `dist/reMarkable-Sync-for-Zotero-0.8.6.xpi`, SHA-256 `f7ec29a3f9c908f202436b3bc3b00dccc86b279ee58c720d22045643c3ea5e6d`. Its worker SHA-256 is `5a1fdddcc86c12b0da09449c83c13ef4c6237a665a660ba22d439367931033ee`. Earlier 0.8.5 and first-build 0.8.6 artifacts are historical verification snapshots with their own hashes in the frontend report.

The first suite needed the existing audit-only `runtime-bootstrap/sitecustomize.py` to append extracted private dependencies after the real standard library. Placing the frozen dependency directory first had shadowed `unittest`; that failed setup attempt ran zero tests and is not counted as a product failure. Private desktop/socket checks required approved sandbox escalation. No automatic safety approval was rejected. The initial unattended run was interrupted by an account usage limit; work resumed after the user's explicit continuation.

Commands and result paths are indexed in `COMMANDS.md`, `frontend-command-log.md`, `backend-command-results.md`, and the component reports. All commands were run from the project root unless stated otherwise; raw private runtime/library evidence remains under ignored `.test-tmp`.

## Components and workflow coverage

`dependency-provenance.md` and JSON record the selected versions, Windows/Python metadata, model hashes, all 285 PDF.js manifest files, and actual license evidence. The Pillow notice was corrected from HPND to MIT-CMU; its actual license was already bundled. No exhaustive transitive vulnerability clearance or independent authentication of every upstream vendor byte is asserted.

Feature traces cover setup/authorization, folder connections and reconnects, native bulk imports and SI, review/filing queues, original preservation, upload receipts, bidirectional folder/PDF work, annotations and OCR/search, paper/page tags, explicit trash/restore decisions, cancellation, process lifecycle, helper integrity, packaging, and upgrades. The component reports distinguish reviewed code from executed native, mocked, or unavailable device/account behavior.

## Remaining boundaries

A source review and passing tests cannot prove every possible execution. Fresh physical pen-stroke/device firmware behavior, another-computer Zotero account round trips, and concurrent account conflict scenarios are not established by these local fixtures. Existing restrictions on unsupported scene formats and rotated/cropped margin expansion remain explicit. Ambiguous paper identities and deletion decisions still require user review; a successful sync does not authorize guessing those decisions.

The private preview has no published automatic-update feed. No public release hosting, signing, remote publishing, permanent trash cleanup, or mass approval of pending papers was performed.

Zotero’s separate account-sync warning reports its **file-storage quota is full**: some PDFs cannot upload to zotero.org, while metadata can continue syncing. This is an account capacity constraint, not repaired by plugin code. No storage purchase, account-plan change, or deletion was authorized or performed.

Primary references checked alongside actual installed implementations: [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api), [PyMuPDF Document API](https://pymupdf.readthedocs.io/en/latest/document.html), [PDF.js 6.4.299](https://github.com/mozilla/pdf.js/releases/tag/v6.4.299), and [SQLite backup/journal handling](https://sqlite.org/howtocorrupt.html#backup_or_restore_while_a_transaction_is_active).

Additional crash references: [CPython issue 140815](https://github.com/python/cpython/issues/140815), [3.13 backport 140985](https://github.com/python/cpython/pull/140985). Exact-symbol and isolated-probe evidence are in `python313-crash-address-evidence.json` and `watchdog-probe-approved-results.json`. Initial probe results that failed during the probe’s own daemon-stdin shutdown were inconclusive and are not treated as evidence of the production fault.
