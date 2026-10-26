# Diagnostic-path verification

Final source regression: 287 passing tests (`required-regression-094-final.log`). All six JS controller suites passed (`javascript-final.log`). These controlled cases establish behavior under the stated fixtures; the separate live-run summaries establish production observations.

| Required path | Evidence and limit |
| --- | --- |
| Normal completion | `tests/test_zotero_sync_diagnostics.py:61`, `tools/test_zotero_sync_diagnostics.cjs:35`; actual configured run in `live-run-094-first.json`. |
| Zotero timeout | `tests/test_zotero_sync_diagnostics.py:46`: started/failed pair, same request ID, no private body. Controlled HTTP timeout; not a deliberately disrupted production request. |
| Stalled operation and inactivity timeout | `tools/test_zotero_sync_diagnostics.cjs:50`; actual 0.9.1 native-save starvation, parent timeout and exit in `first-sync-stopping-timeline.json`. |
| Malformed response | `tools/test_zotero_sync_diagnostics.cjs:58`: protocol failure, safe UI error, parent cleanup, private line omitted. |
| Native PDF output separated from JSON stdout | Final frozen 0.9.4 actual malformed PDF, following valid JSON status and unchanged synthetic bytes: `packaged094-pdf-command.log`, `packaged-pdf-diagnostics-results.json`. |
| Python exception and traceback | `tests/test_zotero_sync_diagnostics.py:141`: exception class and frame capture; private dynamic error text absent. |
| Cancellation | `tests/test_zotero_worker.py:167`, `:342` and bridge recovery suites: stop at safe boundary, unfinished work retained. No cancellation injected into the final production acceptance runs. |
| Pause | `tests/test_zotero_sync_diagnostics.py:164`: saved pause and control record; JS pause fixture at `tools/test_zotero_sync_diagnostics.cjs:76`. Existing production per-link pauses preserved. |
| Parent termination | JS timeout fixture and actual 0.9.1 failure distinguish parent kill reason, EOF and exit -9. |
| EOF and unexpected helper exit | `tools/test_zotero_sync_diagnostics.cjs:65`: synthetic Windows access-violation exit preserved, no parent kill falsely claimed. Python stdin EOF in diagnostics test at line 141. This does not reproduce the earlier Python native crash. |
| Retry | `tests/test_zotero_sync_diagnostics.py:175`: cloud retry timing/count with no URL/body; `tests/test_zotero_transport.py:130`: bounded three-attempt communication failure and pause. Interrupted production 0.9.1 work resumed on the repaired build. |
| Packaging parity | `package-094-verification.json`: all 36 Python modules, entrypoint, 31 frontend/assets, runtime bytes/manifest and required/optional frozen imports. Actual installation: `installed-094-verification.json`, `loaded-094-*.json`. |
| Optional handwriting environment absent during ordinary Sync | `tests/test_zotero_sync_diagnostics.py:72`, `:93`: actual normal worker path independent of optional imports; required-runtime health remains separate. |
| Explicit OCR/reindex | Diagnostics test at line 84 requests OCR and reports its unavailability; final frozen package actually reindexes a disposable PDF in `packaged-pdf-diagnostics-results.json`. No research document was reindexed for this fixture. |
| Bounded logs, redaction, logging failure | Diagnostics tests at lines 18, 37, 111; JS rotation/privacy/failing-write cases. Actual native IOUtils rotation in `native-logging-verification.json`. No raw stderr, cloud payload or annotation text is published. |
| Large-PDF preservation and speed | Exact 541-page immutable copy: all-page pixel/text/geometry and link/bookmark checks in `pdf-save-copy-verification.json`; actual repaired save in `live-093-former-stall-document.json`. Shared resources, repeated pages, cancellation and unresolved/escaped destinations in `tests/test_remarkable_pdf_save.py`. |

The 53-check native and 30-check rendered-UI broader suites ran on earlier candidates; the final 0.9.4 native baseline has 14 passing checks plus the actual OCR/malformed-PDF cases. Counts overlap and must not be summed or represented as a fresh complete audit. Physical tablet pen-stroke comparison and second-computer attachment delivery remain outside this evidence.
