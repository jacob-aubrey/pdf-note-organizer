# Evening frontend and exact-package verification

The final **0.8.8** package matches the current reviewed source and passes its targeted native diagnostic/transport check. This reviewer made no product-code changes during the evening run. Production installation, real cloud sync, and repeat-sync verification belong to the parent audit.

## Confirmed 0.8.7 packaging drift

The previously installed/current 0.8.7 XPI had SHA-256 `77166feb45d73ba972d8c35a884bac03c70b3871119d87a682df2779b4184aa1`; its exact worker had SHA-256 `c46095c97d64bf1ea383b26d96d4d48632eb29f828ecf831764c66b7b701c68a`. The parent independently established that installed package identity; this reviewer verified the XPI's worker bytes against the matching build helper.

Its frozen `note_organizer.zotero_worker` did **not** match source at immutable HEAD `7bdb3a63bf198692883286749693fca9cabcb78d` (source SHA-256 `f3598373452fdb609a1f248160409027d4af092b9f3246523a5513c6376db83c`). The frozen `_serve` had the PyMuPDF stderr routing repair, but lacked the source's serialized `send()`/packet lock, 15-second `keep_alive()` transport heartbeat, and NumPy `ModuleNotFoundError` fallback. These are executable differences, not filenames or line-table metadata. The parent observed an inactivity timeout with the older loaded helper and rebuilt as 0.8.8.

Evidence: `frontend-package087-mismatch.json` records every module comparison and the frozen/current `_serve` field, name, and nested-function differences. Its immutable Git-blob frontend comparison also detects five CRLF/LF byte differences; every one normalizes identically and is explicitly classified as line endings. This does not indicate frontend controller logic drift. The previous exact 0.8.7 status smoke still passed 2/4/1, but did not exercise its missing heartbeat; its preserved result and provenance are in `packaged-status-smoke087-results.json` and `status087-evidence-provenance.json`.

## Final 0.8.8 artifact

- XPI: `dist/reMarkable-Sync-for-Zotero-0.8.8.xpi`, SHA-256 `44354eb0bc530e47e5b1b52021b0e0e711c2c238ea80959f93c657f69520e19c`.
- Worker: `.test-tmp/zotero-plugin-088-dist/notable-worker.exe`, SHA-256 `01f687ed553f1a4999e159705fb4abb435bd16921e4485714cfa55e4df4ab22a`; manifest MD5 `6d1ddae07e26f34e32bea66087f91766`.
- All **36 shipped first-party Python modules**, worker entrypoint, **31 frontend files/assets**, and component notice match current source. Runtime manifest hashes and the XPI/helper byte identity also pass. Python comparison recursively normalizes only `co_filename`, with optimization level 0; all other code-object fields remain significant. The complete first-party module inventory is checked against `PYZ.pyz`, preventing an unexamined extra module from being omitted.
- Evidence: `frontend-package088-comparison.json`. This comparison was executed after the final build, against actual Windows working-tree bytes; it does not substitute Git-normalized text for packaged files.

## Executed checks

The exact final worker passed the synthetic status smoke with `--debug-stacks`: approved waiting **2**, linked **4**, received **1**; exit **0**, empty stderr. Its fixture includes an approved PDF, Office documents, existing links, staged uploads, individually paused and unavailable staged cases, and global pause. Evidence: `packaged-status-smoke-results.json`. The script was copied verbatim into this evening directory so its output would not replace historical evidence; `status-smoke-command-provenance.json` records the original path and identical script hash.

The final disposable native fixture `.test-tmp/full-audit-20261025-evening/packaged088-managed-diagnostic` on port **23168** passed **14 baseline checks** against the exact XPI in Zotero **10.0.6**. Its managed helper had diagnostics enabled. These checks cover setup/permission, native catalog, review/rename/reparent, repeated sync, bidirectional simulated-cloud moves, deletion guards, PDF/Office intake, and actual review rendering.

The additional exact-helper check generated a PDF containing valid searchable text plus malformed content operator `q garbage Q`, published it using the existing `publish`/`Ledger`/`Paper` adapter, and used the adapter's **returned attachment key**. It first verified the managed annotation read, then indexed through the actual bundled helper and requested another status. The helper was launched **without** `PYMUPDF_MESSAGE`, specifically testing its direct-worker `set_messages`/`set_log` fallback, with `--debug-stacks` enabled.

The actual MuPDF syntax diagnostic appeared on **stderr**; every stdout line remained a valid JSON packet. Reindex succeeded, the following status succeeded, the helper exited **0**, and both original and native stored PDF bytes were unchanged. Evidence: `packaged-pdf-diagnostics-results.json`; the complete audit-only runner is `verify_packaged_pdf_diagnostics.py` (110 lines, SHA-256 `37b96fe5f885cfe6156fd99a3858619f902813fd7121b45e71bce7f39e847f16`). The fixture's `close-test` and `done` markers are present, and its harness exited **0**. No scoped fixture remains open.

Two earlier attempts are retained in `packaged-pdf-diagnostics-initial-empty-results.json` and `packaged-pdf-diagnostics-unmanaged-results.json`. They already demonstrated native stderr routing, valid error/status packets, exit 0, and unchanged bytes, but their raw-created attachments lacked the required managed note. The annotation adapter intentionally rejects such reads; the generic HTTPStatusError therefore did not establish an indexing defect. Changing empty text to valid text alone did not resolve that authorization precondition. The final fixture corrected its setup by reusing the real publication adapter; no product code was changed, and the successful-index/status assertions were retained. All three synthetic profiles closed normally; only the final successful fixture is counted as final acceptance evidence.

## Frontend coverage delta

At evening resumption, all **107** entries in the prior frontend ledger still matched current files. The parent then changed only the manifest version to 0.8.8 and added five guide lines explaining the packaged heartbeat/serialized transport and separated diagnostics. Those changes were read and incorporated into the evening `frontend-ledger.json`: **20,597 reviewed lines**, with preserved prior hashes and exact ranges. `frontend-ledger-drift.json` records the two-file metadata delta. No frontend controller logic changed after the previously reviewed PyMuPDF launch routing and strict invalid-response handling.

## Boundaries

This reviewer used synthetic Zotero profiles and local generated PDFs only. The native fixture's cloud side is in memory; no real cloud credentials, production database, physical tablet, or pen sample was accessed. The 53-check bundled-OCR/bulk suite from the earlier package remains historical evidence; it was not repeated for this transport-only rebuild. The 0.8.8 checks establish package/source parity, the targeted status cases, native diagnostic separation, and subsequent JSON transport continuity. They do not replace the parent's real-library sync and repeat-sync acceptance checks.

Exact commands and failed-attempt distinctions are in `frontend-command-log.md`.
